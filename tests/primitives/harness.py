"""Drive one editor primitive at a time through the real key path.

`editor()` opens VimTGApp headlessly on a deck file with the sample card
data loaded, and yields an `Ed`. `Ed.press` feeds keys to
MainScreen._process_key, the same method a terminal keypress reaches, with
the crash net disabled so an exception fails the test instead of being
swallowed.

Key notation for `press`: characters are keys, spaces only separate, and
<Name> spells a named key, e.g. "3dd", "o lightning<CR>", ":w<CR>", "<C-r>".
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card
from vimtg.editor.modes import Mode
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine

FIXTURES = Path(__file__).parent.parent / "fixtures"

# The canonical deck every slice starts from unless a case needs another.
# Opening it changes nothing (test_harness pins that), so row numbers
# below are stable. Rows are 0-based, as Ed.row reports them; G counts
# 1-based, so row r is line r + 1.
#  0 // Deck: Burn              7 4 Goblin Guide          14 (blank)
#  1 // Format: modern          8 2 Eidolon of the Gr..   15 // Land
#  2 // Tags:                   9 3 Bonecrusher Giant..   16 4 Sacred Foundry
#  3 (blank)                   10 (blank)                 17 16 Mountain
#  4 DCK:                      11 // Instant              18 (blank)
#  5 (blank)                   12 4 Lightning Bolt        19 SB:
#  6 // Creature               13 1 Fire // Ice           20 2 Rest in Peace
DECK = (
    "// Deck: Burn\n// Format: modern\n// Tags:\n\n"
    "DCK:\n"
    "\n"
    "    // Creature\n"
    "    4 Goblin Guide\n"
    "    2 Eidolon of the Great Revel\n"
    "    3 Bonecrusher Giant // Stomp\n"
    "\n"
    "    // Instant\n"
    "    4 Lightning Bolt\n"
    "    1 Fire // Ice\n"
    "\n"
    "    // Land\n"
    "    4 Sacred Foundry\n"
    "    16 Mountain\n"
    "\n"
    "SB:\n"
    "    2 Rest in Peace\n"
)

NAMED_KEYS = {
    "<CR>": "enter", "<Esc>": "escape", "<BS>": "backspace", "<Tab>": "tab",
    "<S-Tab>": "shift_tab", "<Up>": "up", "<Down>": "down", "<Left>": "left",
    "<Right>": "right", "<Space>": " ", "<F1>": "f1",
    "<C-a>": "ctrl_a", "<C-b>": "ctrl_b", "<C-d>": "ctrl_d", "<C-e>": "ctrl_e",
    "<C-o>": "ctrl_o", "<C-r>": "ctrl_r", "<C-u>": "ctrl_u", "<C-w>": "ctrl_w",
    "<C-x>": "ctrl_x",
}


def keys(seq: str) -> list[str]:
    """'3dd' -> ['3', 'd', 'd']; '<C-r>' -> ['ctrl_r']; spaces separate."""
    out: list[str] = []
    i = 0
    while i < len(seq):
        if seq[i] == "<":
            end = seq.index(">", i)
            token = seq[i:end + 1]
            if token not in NAMED_KEYS:
                raise ValueError(f"unknown key name {token}")
            out.append(NAMED_KEYS[token])
            i = end + 1
            continue
        if seq[i] != " ":
            out.append(seq[i])
        i += 1
    return out


def seed_cards() -> None:
    """Load the sample cards into the database the app opens."""
    db = Database(db_path())
    try:
        db.initialize()
        raw = json.loads((FIXTURES / "scryfall_sample.json").read_text(encoding="utf-8"))
        CardRepository(db).replace_all(
            [Card.from_scryfall(d) for d in raw], synced_at="2026-10-01T00:00:00+00:00"
        )
    finally:
        db.close()


def _reraise(exc: Exception) -> None:
    raise exc


class Ed:
    """One open editor. Read state through the properties, act with press."""

    def __init__(self, app: VimTGApp, path: Path) -> None:
        self.app = app
        self.path = path

    @property
    def screen(self) -> MainScreen:
        screen = self.app.screen
        assert isinstance(screen, MainScreen), f"not in the editor: {type(screen).__name__}"
        return screen

    def press(self, seq: str) -> Ed:
        screen = self.screen
        screen.recover_from_crash = _reraise  # type: ignore[method-assign]
        for key in keys(seq):
            screen._process_key(key)
        return self

    @property
    def lines(self) -> list[str]:
        buf = self.screen._state.buffer
        return [buf.get_line(i).text for i in range(buf.line_count())]

    @property
    def text(self) -> str:
        return self.screen._state.buffer.to_text()

    @property
    def cards(self) -> list[str]:
        """Card lines, stripped of indentation, in buffer order."""
        buf = self.screen._state.buffer
        return [
            buf.get_line(i).text.strip()
            for i in range(buf.line_count())
            if buf.is_card_line(i)
        ]

    @property
    def row(self) -> int:
        return self.screen._state.cursor.row

    @property
    def line(self) -> str:
        return self.lines[self.row].strip()

    @property
    def mode(self) -> Mode:
        return self.screen._state.mode_mgr.current

    @property
    def message(self) -> str:
        return self.screen.query_one("#command-line", CommandLine).message

    @property
    def is_error(self) -> bool:
        return self.screen.query_one("#command-line", CommandLine).error

    @property
    def modified(self) -> bool:
        return self.screen._state.modified

    def register(self, name: str = '"') -> tuple[str, ...]:
        regs = self.screen._state.registers
        reg = regs.unnamed if name == '"' else regs.get(name)
        return tuple(reg.content)

    def saved(self) -> str:
        return self.path.read_text(encoding="utf-8")


@asynccontextmanager
async def editor(
    tmp_path: Path,
    text: str = DECK,
    *,
    name: str = "burn.deck",
    cards: bool = True,
    size: tuple[int, int] = (120, 40),
) -> AsyncIterator[Ed]:
    """Open `text` as tmp_path/name in a headless app and yield an Ed."""
    if cards:
        seed_cards()
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    app = VimTGApp(deck_path=path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        yield Ed(app, path)
