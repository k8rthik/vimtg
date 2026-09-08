"""Adding a card lands in the zone under the cursor (Textual pilot)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card
from vimtg.editor.buffer import LineType
from vimtg.editor.cursor import Cursor
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "scryfall_sample.json"


@pytest.fixture
def seeded_db(db_factory):  # type: ignore[no-untyped-def]
    db_file = db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    repo = CardRepository(db_factory(db_file))
    repo.bulk_insert(
        [Card.from_scryfall(d) for d in json.loads(_FIXTURES.read_text())]
    )
    return repo


def _screen(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


def _row_of(screen: MainScreen, text: str) -> int:
    buf = screen._state.buffer
    for i in range(buf.line_count()):
        if buf.get_line(i).text.strip() == text:
            return i
    raise AssertionError(f"line not found: {text}")


async def _add_card(pilot, query: str) -> None:
    await pilot.press("o")
    for ch in query:
        await pilot.press(ch)
    await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_o_inside_cmd_block_adds_commander(seeded_db, tmp_path: Path) -> None:
    deck = tmp_path / "edh.deck"
    deck.write_text(
        "// Format: commander\n\nCMD:\n    1 Serra Angel\n\nDCK:\n    30 Forest\n"
    )
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _screen(app)
        screen._state.cursor = Cursor(row=_row_of(screen, "1 Serra Angel"))
        await _add_card(pilot, "goblin gu")
        buf = screen._state.buffer
        row = _row_of(screen, "1 Goblin Guide")
        assert buf.get_line(row).line_type is LineType.COMMANDER_ENTRY
        assert buf.get_line(row).text == "    1 Goblin Guide"
        cl = screen.query_one("#command-line", CommandLine)
        assert "to commander" in cl.message


@pytest.mark.asyncio
async def test_o_on_sb_prefix_line_adds_sideboard(seeded_db, tmp_path: Path) -> None:
    deck = tmp_path / "modern.deck"
    deck.write_text("// Format: modern\n\n4 Goblin Guide\n\nSB: 2 Duress\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _screen(app)
        screen._state.cursor = Cursor(row=_row_of(screen, "SB: 2 Duress"))
        await _add_card(pilot, "lightning bo")
        buf = screen._state.buffer
        row = _row_of(screen, "SB: 1 Lightning Bolt")
        assert buf.get_line(row).line_type is LineType.SIDEBOARD_ENTRY


@pytest.mark.asyncio
async def test_duplicate_increments_within_cursor_zone_only(
    seeded_db, tmp_path: Path,
) -> None:
    deck = tmp_path / "modern.deck"
    deck.write_text(
        "// Format: modern\n\n4 Goblin Guide\n\nSB: 2 Lightning Bolt\n"
    )
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _screen(app)
        screen._state.cursor = Cursor(
            row=_row_of(screen, "SB: 2 Lightning Bolt")
        )
        await _add_card(pilot, "lightning bo")
        text = screen._state.buffer.to_text()
        assert "SB: 3 Lightning Bolt" in text
        # No stray mainboard copy was created
        assert "1 Lightning Bolt\n" not in text


@pytest.mark.asyncio
async def test_mainboard_insert_still_uses_type_sections(
    seeded_db, tmp_path: Path,
) -> None:
    deck = tmp_path / "modern.deck"
    deck.write_text("// Format: modern\n\n// Creature\n4 Goblin Guide\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _screen(app)
        screen._state.cursor = Cursor(row=_row_of(screen, "4 Goblin Guide"))
        await _add_card(pilot, "lightning bo")
        lines = screen._state.buffer.to_text().splitlines()
        assert "// Instants" in lines  # auto-sorted into its type section
        assert "1 Lightning Bolt" in lines
