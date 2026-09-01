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
from textual.app import App

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

    def test_section_with_comment_before_cards_is_kept(self) -> None:
        # A comment between a header and its cards does not make the
        # section empty (dropping the header here destroyed real decks)
        result = self._cleaned("// Creatures\n// just a note\n4 Goblin Guide\n")
        assert "// Creatures" in result

    def test_section_with_comment_and_no_cards_is_dropped(self) -> None:
        result = self._cleaned(
            "// Creatures\n// just a note\n\n// Lands\n20 Mountain\n"
        )
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




def _open_below(scr: MainScreen, row: int) -> None:
    """Simulate pressing 'o' on `row` through the real handler, so the
    scratch blank line carries its pending-insert state."""
    from vimtg.editor.keymap import ParsedAction
    from vimtg.editor.session import handle_mode_switch

    scr._state.cursor = Cursor(row=row)
    handle_mode_switch(scr._state, ParsedAction("mode_switch", "o"))


# ── Search / insert / confirm flow (wired card repo) ───────────────


class _Host(App[None]):
    """Hosts a fully-wired MainScreen for search/insert flow tests."""

    def __init__(self, screen: MainScreen) -> None:
        super().__init__()
        self._target = screen

    def on_mount(self) -> None:
        self.push_screen(self._target)

    def _launch_editor(self, file_path: Path | None = None) -> None:  # pragma: no cover
        pass


@pytest.fixture
def wired_repo(db_factory):  # type: ignore[no-untyped-def]
    import json

    from vimtg.data.card_repository import CardRepository
    from vimtg.domain.card import Card

    fixtures = Path(__file__).parent.parent / "fixtures" / "scryfall_sample.json"
    repo = CardRepository(db_factory())
    repo.bulk_insert([Card.from_scryfall(d) for d in json.loads(fixtures.read_text())])
    return repo


def _wired_screen(repo) -> MainScreen:  # type: ignore[no-untyped-def]
    from vimtg.editor.commands import CommandRegistry
    from vimtg.services.search_service import SearchService

    return MainScreen(
        buffer=Buffer.from_text("// Creatures\n4 Goblin Guide\n"),
        registry=CommandRegistry(),
        search_service=SearchService(card_repo=repo),
        card_repo=repo,
    )


@pytest.mark.asyncio
async def test_update_search_results_shows_panel(wired_repo) -> None:  # type: ignore[no-untyped-def]
    scr = _wired_screen(wired_repo)
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        bolt = wired_repo.get_by_name("Lightning Bolt")
        scr._update_search_results([bolt])
        from vimtg.tui.widgets.search_results import SearchResults

        sr = scr.query_one("#search-results", SearchResults)
        assert sr.display is True
        assert sr.results == [bolt]


@pytest.mark.asyncio
async def test_confirm_insert_adds_card_to_section(wired_repo) -> None:  # type: ignore[no-untyped-def]
    scr = _wired_screen(wired_repo)
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Open a blank line (simulate 'o') then confirm an Instant insert.
        _open_below(scr, 1)
        bolt = wired_repo.get_by_name("Lightning Bolt")
        scr._update_search_results([bolt])
        scr._confirm_insert()
        assert scr._find_card_line("Lightning Bolt") is not None


@pytest.mark.asyncio
async def test_confirm_insert_duplicate_increments(wired_repo) -> None:  # type: ignore[no-untyped-def]
    scr = _wired_screen(wired_repo)
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        _open_below(scr, 1)
        guide = wired_repo.get_by_name("Goblin Guide")
        scr._update_search_results([guide])
        scr._confirm_insert()
        line = scr._find_card_line("Goblin Guide")
        assert line is not None
        assert scr._state.buffer.quantity_at(line) == 5  # 4 -> 5


@pytest.mark.asyncio
async def test_confirm_insert_duplicate_preserves_prefix_and_tags(wired_repo) -> None:  # type: ignore[no-untyped-def]
    from vimtg.editor.commands import CommandRegistry
    from vimtg.services.search_service import SearchService

    scr = MainScreen(
        buffer=Buffer.from_text("// Sideboard\nSB: 2 Goblin Guide  #aggro\n"),
        registry=CommandRegistry(),
        search_service=SearchService(card_repo=wired_repo),
        card_repo=wired_repo,
    )
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        _open_below(scr, 1)
        guide = wired_repo.get_by_name("Goblin Guide")
        scr._update_search_results([guide])
        scr._confirm_insert()
        # The cursor sits in the sideboard, so the add targets the
        # sideboard: the existing SB copy increments (prefix and tags
        # preserved) and no mainboard copy appears
        text = scr._state.buffer.to_text()
        assert "SB: 3 Goblin Guide  #aggro" in text
        assert scr._find_card_line("Goblin Guide") is None  # no mainboard copy


@pytest.mark.asyncio
async def test_confirm_insert_new_section_cursor_stays_on_card(wired_repo) -> None:  # type: ignore[no-untyped-def]
    """Adding a card that creates a new type section must leave the
    cursor on the card, not on the '// Instant' header — even after the
    normalize pass that pads a blank line before the new header."""
    scr = _wired_screen(wired_repo)  # "// Creatures\n4 Goblin Guide\n"
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        _open_below(scr, 1)  # 'o'
        bolt = wired_repo.get_by_name("Lightning Bolt")
        scr._update_search_results([bolt])
        scr._confirm_insert()
        scr._cleanup_empty_sections()  # what _sync_widgets runs next
        row = scr._state.cursor.row
        assert "Lightning Bolt" in scr._state.buffer.get_line(row).text


@pytest.mark.asyncio
async def test_confirm_insert_new_section_cursor_in_dck_block(wired_repo) -> None:  # type: ignore[no-untyped-def]
    from vimtg.editor.commands import CommandRegistry
    from vimtg.services.search_service import SearchService

    scr = MainScreen(
        buffer=Buffer.from_text(
            "DCK:\n\n    // Creature\n    4 Goblin Guide\n\nSB: 2 Rest in Peace\n"
        ),
        registry=CommandRegistry(),
        search_service=SearchService(card_repo=wired_repo),
        card_repo=wired_repo,
    )
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        _open_below(scr, 3)  # 'o' on last card
        bolt = wired_repo.get_by_name("Lightning Bolt")
        scr._update_search_results([bolt])
        scr._confirm_insert()
        scr._cleanup_empty_sections()
        row = scr._state.cursor.row
        assert "Lightning Bolt" in scr._state.buffer.get_line(row).text
        # The new section landed inside the block, indented
        assert scr._state.buffer.get_line(row).text.startswith("    ")


@pytest.mark.asyncio
async def test_confirm_insert_duplicate_below_blank_keeps_cursor(wired_repo) -> None:  # type: ignore[no-untyped-def]
    """Incrementing a duplicate that sits BELOW the 'o' blank line must
    land the cursor on that card, not one line past it."""
    from vimtg.editor.commands import CommandRegistry
    from vimtg.services.search_service import SearchService

    scr = MainScreen(
        buffer=Buffer.from_text(
            "// Creatures\n\n4 Goblin Guide\n4 Lightning Bolt\n"
        ),
        registry=CommandRegistry(),
        search_service=SearchService(card_repo=wired_repo),
        card_repo=wired_repo,
    )
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        scr._state.cursor = Cursor(row=1)  # the blank, above the duplicate
        guide = wired_repo.get_by_name("Goblin Guide")
        scr._update_search_results([guide])
        scr._confirm_insert()
        row = scr._state.cursor.row
        assert "Goblin Guide" in scr._state.buffer.get_line(row).text
        assert scr._state.buffer.quantity_at(row) == 5


@pytest.mark.asyncio
async def test_confirm_insert_counted_quantity(wired_repo) -> None:  # type: ignore[no-untyped-def]
    """4o then a confirmed card writes '4 <card>', and the quantity is
    consumed — the next plain insert is back to 1 copy."""
    scr = _wired_screen(wired_repo)
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        _open_below(scr, 1)
        scr._state.insert_quantity = 4
        bolt = wired_repo.get_by_name("Lightning Bolt")
        scr._update_search_results([bolt])
        scr._confirm_insert()
        line = scr._find_card_line("Lightning Bolt")
        assert line is not None
        assert scr._state.buffer.quantity_at(line) == 4
        assert scr._state.insert_quantity == 1


@pytest.mark.asyncio
async def test_confirm_insert_counted_duplicate_adds_quantity(wired_repo) -> None:  # type: ignore[no-untyped-def]
    scr = _wired_screen(wired_repo)  # holds "4 Goblin Guide"
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        _open_below(scr, 1)
        scr._state.insert_quantity = 4
        guide = wired_repo.get_by_name("Goblin Guide")
        scr._update_search_results([guide])
        scr._confirm_insert()
        line = scr._find_card_line("Goblin Guide")
        assert line is not None
        assert scr._state.buffer.quantity_at(line) == 8  # 4 -> 8


@pytest.mark.asyncio
async def test_confirm_insert_no_selection_cleans_blank(wired_repo) -> None:  # type: ignore[no-untyped-def]
    scr = _wired_screen(wired_repo)
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        _open_below(scr, 1)
        scr._update_search_results([])  # nothing selected
        before = scr._state.buffer.line_count()
        scr._confirm_insert()
        assert scr._state.buffer.line_count() == before - 1


@pytest.mark.asyncio
async def test_cleanup_is_noop_on_clean_buffer(wired_repo) -> None:  # type: ignore[no-untyped-def]
    scr = _wired_screen(wired_repo)
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        before = scr._state.buffer
        scr._cleanup_empty_sections()
        assert scr._state.buffer is before
        assert scr._state.modified is False


@pytest.mark.asyncio
async def test_cleanup_after_edit_is_single_undo_step(wired_repo) -> None:  # type: ignore[no-untyped-def]
    from vimtg.editor.commands import CommandRegistry
    from vimtg.services.search_service import SearchService

    scr = MainScreen(
        buffer=Buffer.from_text("// Creatures\n4 Goblin Guide\n\n// Lands\n20 Mountain\n"),
        registry=CommandRegistry(),
        search_service=SearchService(card_repo=wired_repo),
        card_repo=wired_repo,
    )
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        s = scr._state
        s.history.initialize(s.buffer)
        # Simulate dd on the last card of // Lands
        s.buffer, _ = s.buffer.delete_lines(4, 4)
        s.history.record(s.buffer, "delete card")
        scr._cleanup_empty_sections()
        assert "// Lands" not in s.buffer.to_text()
        assert s.modified is True
        restored = s.history.undo()
        assert restored is not None
        assert "20 Mountain" in restored.to_text()


@pytest.mark.asyncio
async def test_handle_search_next_prev(wired_repo) -> None:  # type: ignore[no-untyped-def]
    scr = _wired_screen(wired_repo)
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        cards = [wired_repo.get_by_name("Lightning Bolt"), wired_repo.get_by_name("Lava Spike")]
        scr._update_search_results(cards)
        from vimtg.tui.widgets.search_results import SearchResults

        sr = scr.query_one("#search-results", SearchResults)
        scr._handle_search_action("__next__")
        assert sr.selected == 1
        scr._handle_search_action("__prev__")
        assert sr.selected == 0


@pytest.mark.asyncio
async def test_handle_search_short_query_hides(wired_repo) -> None:  # type: ignore[no-untyped-def]
    scr = _wired_screen(wired_repo)
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        from vimtg.tui.widgets.search_results import SearchResults

        sr = scr.query_one("#search-results", SearchResults)
        sr.display = True
        scr._handle_search_action("b")  # < 2 chars
        assert sr.display is False


# ── Live lint + comment flow (pilot) ───────────────────────────────


@pytest.mark.asyncio
async def test_live_lint_flags_copy_limit(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        row = scr._state.buffer.next_card_line(0)
        assert row is not None
        scr._state.cursor = Cursor(row=row)
        await pilot.press("plus")  # 5th copy in a modern deck
        dv = scr.query_one("#deck-view")
        err = dv.line_errors.get(row)
        assert err is not None and err.level == "error"
        assert "copies" in err.message


@pytest.mark.asyncio
async def test_cursor_on_flagged_row_shows_reason(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        row = scr._state.buffer.next_card_line(0)
        scr._state.cursor = Cursor(row=row)
        await pilot.press("plus")
        sl = scr.query_one("#status-line")
        assert "copies" in sl.cursor_lint
        assert sl.cursor_lint_level == "error"
        # Moving off the row clears the reason
        await pilot.press("j")
        assert sl.cursor_lint == ""


@pytest.mark.asyncio
async def test_comment_key_end_to_end(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        row = scr._state.buffer.next_card_line(0)
        scr._state.cursor = Cursor(row=row)
        await pilot.press("A")
        for ch in "wincon":
            await pilot.press(ch)
        await pilot.press("enter")
        assert scr._state.buffer.comment_at(row) == "wincon"
        # A again prefills; escape leaves it untouched
        await pilot.press("A")
        await pilot.press("escape")
        assert scr._state.buffer.comment_at(row) == "wincon"


@pytest.mark.asyncio
async def test_scaffold_added_on_open_without_modified(tmp_path: Path) -> None:
    p = tmp_path / "bare.deck"
    p.write_text("4 Goblin Guide\n", encoding="utf-8")
    app = VimTGApp(deck_path=p)
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        text = scr._state.buffer.to_text()
        assert "// Deck:" in text
        assert "// Format:" in text
        assert "// Tags:" in text
        assert scr._state.modified is False


@pytest.mark.asyncio
async def test_macro_records_literal_q_in_command_mode(tmp_path: Path) -> None:
    """Literal 'q' characters typed in COMMAND/INSERT mode belong in the
    recording (regression: any bare 'q' was skipped as the stop key)."""
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        await pilot.press("q", "a")  # start recording into @a
        assert scr._state.macros.is_recording
        await pilot.press("colon")
        await pilot.press("q", "q")  # literal text containing q
        await pilot.press("escape")  # cancel the command line
        await pilot.press("q")  # stop recording (normal mode)
        assert not scr._state.macros.is_recording
        macro = scr._state.macros.get("a")
        assert macro is not None
        assert macro.keys == (":", "q", "q", "escape")


@pytest.mark.asyncio
async def test_search_filters_by_deck_declared_format(wired_repo) -> None:  # type: ignore[no-untyped-def]
    """Search legality filtering honors the deck's '// Format:' metadata
    over the global default (regression: default_format was used raw,
    hiding cards legal in the deck's actual format)."""
    from vimtg.config.settings import Settings
    from vimtg.editor.commands import CommandRegistry
    from vimtg.services.search_service import SearchService
    from vimtg.tui.widgets.search_results import SearchResults

    scr = MainScreen(
        buffer=Buffer.from_text("// Format: modern\n\n4 Goblin Guide\n"),
        registry=CommandRegistry(),
        search_service=SearchService(card_repo=wired_repo),
        card_repo=wired_repo,
        settings=Settings(default_format="standard"),
    )
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        scr._run_search("Lightning")
        await app.workers.wait_for_complete()
        await pilot.pause()
        sr = scr.query_one("#search-results", SearchResults)
        # Bolt is modern-legal but not standard-legal
        assert any(c.name == "Lightning Bolt" for c in sr.results)


@pytest.mark.asyncio
async def test_o_escape_leaves_buffer_unchanged(tmp_path: Path) -> None:
    """Escaping an o-opened card search must remove the scratch blank
    line and put the cursor back where it was."""
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        row = scr._state.buffer.next_card_line(0)
        scr._state.cursor = Cursor(row=row)
        before = scr._state.buffer.to_text()
        await pilot.press("o")
        await pilot.press("escape")
        await pilot.pause()
        assert scr._state.buffer.to_text() == before
        assert scr._state.cursor.row == row


@pytest.mark.asyncio
async def test_upper_o_escape_leaves_buffer_unchanged(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        row = scr._state.buffer.next_card_line(0)
        scr._state.cursor = Cursor(row=row)
        before = scr._state.buffer.to_text()
        await pilot.press("O")
        await pilot.press("escape")
        await pilot.pause()
        assert scr._state.buffer.to_text() == before
        assert scr._state.cursor.row == row


@pytest.mark.asyncio
async def test_visual_o_swaps_selection_no_newline(tmp_path: Path) -> None:
    """2o from visual mode crashed mid-way, leaving a stray newline and
    no insert mode. Visual o now swaps the selection ends, vim-style."""
    from vimtg.editor.modes import Mode

    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        s = scr._state
        row = s.buffer.next_card_line(0)
        s.cursor = Cursor(row=row)
        before = s.buffer.to_text()
        await pilot.press("v")
        await pilot.press("j")
        await pilot.press("2")
        await pilot.press("o")
        await pilot.pause()
        assert s.buffer.to_text() == before  # no stray newline
        assert s.mode_mgr.current == Mode.VISUAL
        assert s.cursor.row == row  # back at the anchor end
        assert s.visual_anchor == row + 1


@pytest.mark.asyncio
async def test_visual_change_enters_card_search(tmp_path: Path) -> None:
    from vimtg.editor.modes import Mode

    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        s = scr._state
        row = s.buffer.next_card_line(0)
        s.cursor = Cursor(row=row)
        before = s.buffer.line_count()
        await pilot.press("v")
        await pilot.press("j")
        await pilot.press("c")
        await pilot.pause()
        assert s.mode_mgr.current == Mode.INSERT  # crashed before the fix
        assert s.buffer.line_count() == before - 2


@pytest.mark.asyncio
async def test_cc_confirm_does_not_overwrite_next_line(wired_repo) -> None:  # type: ignore[no-untyped-def]
    """cc deletes its line and re-enters card search; the confirmed
    card must be INSERTED, never written over the following line."""
    from vimtg.editor.commands import CommandRegistry
    from vimtg.services.search_service import SearchService

    scr = MainScreen(
        buffer=Buffer.from_text(
            "4 Goblin Guide\nSB: 2 Duress\nSB: 2 Rest in Peace\n"
        ),
        registry=CommandRegistry(),
        search_service=SearchService(card_repo=wired_repo),
        card_repo=wired_repo,
    )
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        s = scr._state
        s.cursor = Cursor(row=1)  # "SB: 2 Duress"
        await pilot.press("c")
        await pilot.press("c")
        await pilot.pause()
        bolt = wired_repo.get_by_name("Lightning Bolt")
        scr._update_search_results([bolt])
        scr._confirm_insert()
        lines = [s.buffer.get_line(i).text for i in range(s.buffer.line_count())]
        assert "SB: 2 Rest in Peace" in lines  # survived
        assert any("Lightning Bolt" in ln for ln in lines)
        assert "SB: 2 Duress" not in lines  # the changed-away line


@pytest.mark.asyncio
async def test_confirm_insert_sideboard_is_alphabetical(wired_repo) -> None:  # type: ignore[no-untyped-def]
    """With auto-sort on, a card added to the sideboard keeps the zone
    alphabetical instead of landing wherever the line was opened."""
    from vimtg.editor.commands import CommandRegistry
    from vimtg.services.search_service import SearchService

    scr = MainScreen(
        buffer=Buffer.from_text(
            "4 Goblin Guide\n\nSB: 2 Duress\nSB: 2 Rest in Peace\n"
        ),
        registry=CommandRegistry(),
        search_service=SearchService(card_repo=wired_repo),
        card_repo=wired_repo,
    )
    app = _Host(scr)
    async with app.run_test() as pilot:
        await pilot.pause()
        s = scr._state
        s.cursor = Cursor(row=3)  # on "SB: 2 Rest in Peace"
        await pilot.press("o")    # open below the last SB line
        await pilot.pause()
        bolt = wired_repo.get_by_name("Lightning Bolt")
        scr._update_search_results([bolt])
        scr._confirm_insert()
        lines = [s.buffer.get_line(i).text for i in range(s.buffer.line_count())]
        assert lines.index("SB: 1 Lightning Bolt") == (
            lines.index("SB: 2 Duress") + 1
        )  # D < L < R
        assert s.cursor.row == lines.index("SB: 1 Lightning Bolt")
