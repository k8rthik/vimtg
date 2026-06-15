"""Unit tests for MainScreen helper logic that needs no mounted widgets.

MainScreen.__init__ only builds editor state, so the buffer-manipulation
helpers (_cleanup_empty_sections, _find_type_section_row, _find_card_line)
and the module-level pure functions can be exercised directly. Section
cleanup is historically the source of section-corruption bugs, so it gets
thorough coverage here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.cursor import Cursor
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import (
    MainScreen,
    _card_type_section,
    _hint_for_cursor,
)


def _screen(text: str) -> MainScreen:
    return MainScreen(buffer=Buffer.from_text(text))


def _card(name: str, type_line: str) -> object:
    """Build a minimal Card-like stub (only .name/.type_line are used)."""

    class _C:
        pass

    c = _C()
    c.name = name  # type: ignore[attr-defined]
    c.type_line = type_line  # type: ignore[attr-defined]
    return c


# ── module-level pure functions ────────────────────────────────────


class TestCardTypeSection:
    def test_creature(self) -> None:
        assert _card_type_section("Legendary Creature — Goblin") == "Creature"

    def test_instant(self) -> None:
        assert _card_type_section("Instant") == "Instant"

    def test_land(self) -> None:
        assert _card_type_section("Basic Land — Mountain") == "Land"

    def test_unknown_is_other(self) -> None:
        assert _card_type_section("Conspiracy") == "Other"

    def test_creature_precedence_over_artifact(self) -> None:
        # Artifact Creature -> Creature wins (checked first).
        assert _card_type_section("Artifact Creature — Golem") == "Creature"


class TestHintForCursor:
    def test_card_line_hint(self) -> None:
        buf = Buffer.from_text("4 Goblin Guide\n")
        assert _hint_for_cursor(buf, 0) != _hint_for_cursor(Buffer.from_text("// x\n"), 0)

    def test_non_card_hint(self) -> None:
        buf = Buffer.from_text("// comment\n")
        # Should not raise and returns a non-empty string.
        assert _hint_for_cursor(buf, 0)


# ── _find_card_line ────────────────────────────────────────────────


class TestFindCardLine:
    def test_finds_existing(self) -> None:
        s = _screen("4 Goblin Guide\n4 Lightning Bolt\n")
        assert s._find_card_line("Lightning Bolt") == 1

    def test_missing_returns_none(self) -> None:
        s = _screen("4 Goblin Guide\n")
        assert s._find_card_line("Counterspell") is None


# ── _find_type_section_row ─────────────────────────────────────────


class TestFindTypeSectionRow:
    def test_inserts_into_existing_section(self) -> None:
        s = _screen("// Creatures\n4 Goblin Guide\n\n// Lands\n4 Mountain\n")
        card = _card("Monastery Swiftspear", "Creature")
        _buf, row = s._find_type_section_row(card, s._state.buffer)
        # Row should be just after the existing creatures block (line 2).
        assert row == 2

    def test_creates_new_section_at_end(self) -> None:
        s = _screen("// Creatures\n4 Goblin Guide\n")
        buf, row = s._find_type_section_row(_card("Lightning Bolt", "Instant"), s._state.buffer)
        assert row is not None
        assert "// Instant" in buf.get_line(row - 1).text

    def test_creates_section_before_sideboard(self) -> None:
        s = _screen("// Creatures\n4 Goblin Guide\nSB: 2 Rest in Peace\n")
        buf, row = s._find_type_section_row(_card("Lightning Bolt", "Instant"), s._state.buffer)
        # The new header must appear before the sideboard entry.
        header_idx = next(
            i for i in range(buf.line_count())
            if buf.get_line(i).line_type == LineType.SECTION_HEADER
            and "Instant" in buf.get_line(i).text
        )
        sb_idx = next(
            i for i in range(buf.line_count())
            if buf.get_line(i).line_type == LineType.SIDEBOARD_ENTRY
        )
        assert header_idx < sb_idx


# ── _cleanup_empty_sections ────────────────────────────────────────


class TestCleanupEmptySections:
    def _cleaned(self, text: str) -> str:
        s = _screen(text)
        s._cleanup_empty_sections()
        return s._state.buffer.to_text()

    def test_removes_empty_section_header(self) -> None:
        result = self._cleaned("// Creatures\n4 Goblin Guide\n\n// Lands\n")
        assert "// Lands" not in result
        assert "// Creatures" in result

    def test_keeps_populated_sections(self) -> None:
        result = self._cleaned("// Creatures\n4 Goblin Guide\n\n// Lands\n4 Mountain\n")
        assert "// Creatures" in result
        assert "// Lands" in result

    def test_collapses_consecutive_blanks(self) -> None:
        result = self._cleaned("4 Goblin Guide\n\n\n\n4 Lightning Bolt\n")
        assert "\n\n\n" not in result

    def test_pads_blank_before_section_header(self) -> None:
        # A section header directly after a card should get a blank separator.
        result = self._cleaned("4 Goblin Guide\n// Lands\n4 Mountain\n")
        lines = result.split("\n")
        lands_idx = lines.index("// Lands")
        assert lines[lands_idx - 1] == ""

    def test_no_double_blank_before_header(self) -> None:
        result = self._cleaned("4 Goblin Guide\n\n// Lands\n4 Mountain\n")
        lines = result.split("\n")
        lands_idx = lines.index("// Lands")
        # Exactly one blank, not two.
        assert lines[lands_idx - 1] == ""
        assert lines[lands_idx - 2] != ""

    def test_empty_section_at_end_removed(self) -> None:
        result = self._cleaned("4 Goblin Guide\n\n// Sideboard\n")
        assert "// Sideboard" not in result

    def test_cursor_clamped_after_cleanup(self) -> None:
        s = _screen("4 Goblin Guide\n\n// Lands\n")
        s._state.cursor = Cursor(row=2)
        s._cleanup_empty_sections()
        assert s._state.cursor.row < s._state.buffer.line_count()

    def test_section_followed_by_comment_is_empty(self) -> None:
        # A header whose next non-blank line is a comment counts as empty.
        result = self._cleaned("// Creatures\n// just a note\n4 Goblin Guide\n")
        assert "// Creatures" not in result

    def test_idempotent(self) -> None:
        once = self._cleaned("// Creatures\n4 Goblin Guide\n\n// Lands\n")
        s = _screen(once)
        s._cleanup_empty_sections()
        assert s._state.buffer.to_text() == once


# ── Pilot integration tests via VimTGApp ───────────────────────────


def _deck_file(tmp_path: Path) -> Path:
    p = tmp_path / "deck.deck"
    p.write_text(
        "// Deck: Test\n// Format: modern\n\n"
        "// Creatures\n4 Goblin Guide\n4 Monastery Swiftspear\n\n"
        "// Spells\n4 Lightning Bolt\n",
        encoding="utf-8",
    )
    return p


def _main_screen(app: VimTGApp) -> MainScreen:
    return app.screen  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_motion_updates_cursor(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        start = scr._state.cursor.row
        await pilot.press("j")
        assert scr._state.cursor.row == start + 1
        await pilot.press("k")
        assert scr._state.cursor.row == start


@pytest.mark.asyncio
async def test_increment_decrement_quantity(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        # Move to the first card line (4 Goblin Guide on row 4).
        row = scr._state.buffer.next_card_line(0)
        assert row is not None
        scr._state.cursor = Cursor(row=row)
        await pilot.press("plus")
        assert scr._state.buffer.quantity_at(row) == 5
        await pilot.press("minus")
        assert scr._state.buffer.quantity_at(row) == 4


@pytest.mark.asyncio
async def test_dd_deletes_card_line(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        row = scr._state.buffer.next_card_line(0)
        assert row is not None
        scr._state.cursor = Cursor(row=row)
        before = scr._state.buffer.line_count()
        await pilot.press("d", "d")
        assert scr._state.buffer.line_count() == before - 1


@pytest.mark.asyncio
async def test_command_mode_unknown_shows_message(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        await pilot.press("colon")
        for ch in "bogus":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        from vimtg.tui.widgets.command_line import CommandLine

        cl = scr.query_one("#command-line", CommandLine)
        assert "Unknown command" in cl.message


@pytest.mark.asyncio
async def test_escape_returns_to_normal(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        await pilot.press("colon")  # enter command mode
        await pilot.press("escape")
        await pilot.pause()
        assert scr._state.mode_mgr.is_normal()


@pytest.mark.asyncio
async def test_open_help_via_question_mark(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        from vimtg.tui.widgets.help_panel import HelpPanel

        await pilot.press("question_mark")
        await pilot.pause()
        hp = scr.query_one("#help-panel", HelpPanel)
        assert hp.display is True
