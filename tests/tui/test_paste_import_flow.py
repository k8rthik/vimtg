"""Normal-mode paste with card data: names normalise to the card's
official name and merge by card, and a headerless Commander list puts
its commander in the command zone."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from textual import events

from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen


@pytest.fixture
def synced_db(real_shape_cards: list[dict[str, Any]]) -> None:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(path)
    db.initialize()
    CardRepository(db).replace_all([Card.from_scryfall(d) for d in real_shape_cards])
    db.close()


def _deck(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "t.deck"
    path.write_text(text, encoding="utf-8")
    return path


def _screen(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


@pytest.mark.asyncio
@pytest.mark.usefixtures("synced_db")
async def test_paste_merges_other_spellings_into_existing_lines(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(
        tmp_path, "// Deck: Izzet\n\n4 Delver of Secrets\n2 Fire // Ice\n"
    ))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = _screen(app)
        screen.post_message(events.Paste("2 Insectile Aberration\n2 Fire/Ice\n"))
        await pilot.pause()
        lines = screen._state.buffer.to_text().splitlines()
        assert "6 Delver of Secrets" in lines
        assert "4 Fire // Ice" in lines
        assert not any("Insectile" in line or "Fire/Ice" in line for line in lines)


@pytest.mark.asyncio
async def test_paste_headerless_commander_list(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path, "// Deck: K\n// Format: commander\n"))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = _screen(app)
        screen.post_message(events.Paste(
            "1 Kenrith, the Returned King\n\n1 Sol Ring\n49 Island\n49 Plains\n"
        ))
        await pilot.pause()
        text = screen._state.buffer.to_text()
        assert "CMD:\n    1 Kenrith, the Returned King" in text
        assert "SB:" not in text
