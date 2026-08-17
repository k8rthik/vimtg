"""Block-default layout through the real app: new deck → add cards → mc."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card
from vimtg.editor.buffer import LineType
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen

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


@pytest.mark.asyncio
async def test_new_deck_scaffolds_blocks_and_insert_lands_inside(
    seeded_db, tmp_path: Path,
) -> None:
    deck = tmp_path / "fresh.deck"
    deck.write_text("// Format: commander\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _screen(app)
        text = screen._state.buffer.to_text()
        assert "CMD:" in text.splitlines()
        assert "DCK:" in text.splitlines()

        # Add a card through search — it must land indented inside DCK:
        await pilot.press("o")
        for ch in "goblin gu":
            await pilot.press(ch)
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        buf = screen._state.buffer
        lines = buf.to_text().splitlines()
        assert "    // Creature" in lines
        assert "    1 Goblin Guide" in lines
        row = lines.index("    1 Goblin Guide")
        assert buf.get_line(row).line_type is LineType.CARD_ENTRY
        assert lines.index("DCK:") < lines.index("    // Creature")

        # mc moves it into the CMD: block, indented, and cleans the
        # now-empty type section
        from vimtg.editor.cursor import Cursor

        screen._state.cursor = Cursor(row=row)
        await pilot.press("m", "c")
        lines = screen._state.buffer.to_text().splitlines()
        assert "    1 Goblin Guide" in lines
        cmd_row = lines.index("CMD:")
        card_row = lines.index("    1 Goblin Guide")
        assert screen._state.buffer.get_line(card_row).line_type is (
            LineType.COMMANDER_ENTRY
        )
        assert cmd_row < card_row < lines.index("DCK:")
        assert "    // Creature" not in lines  # emptied section cleaned
