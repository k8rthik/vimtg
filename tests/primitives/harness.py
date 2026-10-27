"""Drive one editor primitive at a time through the real key path.

`editor()` opens VimTGApp headlessly on a deck file with the sample card
data loaded, and yields an `Ed`. `Ed.press` feeds keys to
MainScreen._process_key, the same method a terminal keypress reaches, with
the crash net disabled so an exception fails the test instead of being
swallowed.

Key notation: characters are keys, spaces only separate, and <Name> spells
a named key, e.g. "3dd", "o lightning<CR>", ":w<CR>", "<C-r>". <lt> is a
literal '<' and <Space> a literal space, as vim spells them. `Ed.ex` types
an ex command as written, spaces and '<' included.

Two ways to send keys:
- `Ed.press` (sync) reaches the editor's key path and nothing above it.
  Use it for editing, motions, ex commands: anything the editor handles.
- `Ed.type` (async) sends the same notation as terminal key events through
  Textual's Pilot, so MainScreen.on_key runs: it clears the last message,
  opens help on F1, closes the tips on Esc, and every key typed into a
  floating overlay or caught by an app binding goes this way too. It
  renders after every key, as a terminal does.
- `Ed.press_chunks` (async) is `press` with a render after each
  space-separated chunk, for cases that read the view between keys.

Card search and other workers run off the key path: `await ed.settle()`
before reading what they deliver, or `await ed.pick(query)` to type a
search and confirm its top result.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from textual.pilot import Pilot

from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card
from vimtg.editor.modes import Mode
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.search_results import SearchResults
from vimtg.tui.widgets.status_line import StatusLine

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
    "<Right>": "right", "<Space>": " ", "<lt>": "<", "<F1>": "f1",
    "<C-a>": "ctrl_a", "<C-b>": "ctrl_b", "<C-d>": "ctrl_d", "<C-e>": "ctrl_e",
    "<C-o>": "ctrl_o", "<C-r>": "ctrl_r", "<C-s>": "ctrl_s", "<C-u>": "ctrl_u",
    "<C-w>": "ctrl_w", "<C-x>": "ctrl_x",
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


def _textual_key(key: str) -> str:
    """A canonical key as Pilot.press spells it: 'ctrl_r' -> 'ctrl+r'."""
    if key == " ":
        return "space"
    if key.startswith(("ctrl_", "shift_")):
        return key.replace("_", "+", 1)
    return key


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

    def __init__(self, app: VimTGApp, path: Path, pilot: Pilot[object]) -> None:
        self.app = app
        self.path = path
        self.pilot = pilot

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

    def ex(self, command: str) -> Ed:
        """Type ':' + command + Enter, every character of command literally."""
        literal = command.replace("<", "<lt>").replace(" ", "<Space>")
        return self.press(":" + literal + "<CR>")

    async def press_chunks(self, seq: str) -> None:
        """Press each space-separated chunk of `seq`, rendering after each.
        Keys inside a chunk get no render between them, unlike `type`."""
        for chunk in seq.split():
            self.press(chunk)
            await self.pilot.pause()

    async def type(self, seq: str) -> None:
        """Send `seq` as terminal key events, rendering after each key."""
        await self.settle()
        for key in keys(seq):
            await self.pilot.press(_textual_key(key))
            await self.pilot.pause()
        await self.settle()

    async def settle(self) -> None:
        """Let posted messages run, workers finish, and the screen render."""
        await self.pilot.pause()
        await self.app.workers.wait_for_complete()
        await self.pilot.pause()

    async def pick(self, query: str) -> None:
        """Type `query` into the open card search, wait for its results,
        and confirm the top one with Enter."""
        self.press(query)
        results = self.screen.query_one("#search-results", SearchResults)
        for _ in range(500):
            await self.settle()
            if results.results:
                break
            await asyncio.sleep(0.01)
        assert results.results, f"card search for {query!r} found nothing"
        self.press("<CR>")

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
    def status(self) -> str:
        return self.screen.query_one("#status-line", StatusLine).render().plain

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
        yield Ed(app, path, pilot)
