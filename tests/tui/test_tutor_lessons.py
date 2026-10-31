"""Walk every tutor lesson's "Try it" steps through the real editor.

Each lesson runs in a fresh tutor sandbox and checks what the lesson text
promises, so a key change that breaks a lesson fails here instead of
leaving the tutor teaching keys that no longer work.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from textual.pilot import Pilot

from vimtg.tui.app import VimTGApp
from vimtg.tui.key_translator import _TEXTUAL_TO_SYMBOL
from vimtg.tui.screens.help_screen import HelpScreen
from vimtg.tui.screens.history_screen import HistoryScreen
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tutor import lesson_text, tutor_sandbox

_SYMBOL_TO_TEXTUAL = {v: k for k, v in _TEXTUAL_TO_SYMBOL.items()}
_NAMED = {"<CR>": "enter", "<Esc>": "escape", "<Space>": "space", "<F1>": "f1"}
_TOKEN = re.compile(r"<[^>]+>|.", re.S)


@dataclass(frozen=True)
class View:
    app: VimTGApp
    main: MainScreen

    @property
    def lines(self) -> list[str]:
        buf = self.main._state.buffer
        return [buf.get_line(i).text.strip() for i in range(buf.line_count())]

    @property
    def cursor_line(self) -> str:
        return self.lines[self.main._state.cursor.row]

    @property
    def message(self) -> str:
        return self.main.query_one("#command-line", CommandLine).message

    @property
    def shown(self) -> str:
        """The command line, plus the pager when a listing opened one."""
        pager = self.app.screen
        body = pager._body if isinstance(pager, HelpScreen) else None
        return f"{self.message}\n{body or ''}"


Check = Callable[[View], bool]


@dataclass(frozen=True)
class Step:
    keys: str
    check: Check


def _on(text: str) -> Check:
    return lambda v: v.cursor_line == text


def _pane(v: View) -> str | None:
    pane = v.main._split_pane
    return pane.kind if pane is not None else None


LESSONS: dict[int, tuple[Step, ...]] = {
    1: (Step("w", _on("4 Goblin Guide")),),
    2: (
        Step("/Lava Spike<CR>3+", _on("4 Lava Spike")),
        Step("<C-a>", _on("5 Lava Spike")),
        Step("<C-x>", _on("4 Lava Spike")),
        Step("/Rift Bolt<CR>-", _on("4 Rift Bolt")),
    ),
    3: (
        Step("/Ponder<CR>dd", lambda v: "4 Ponder" not in v.lines),
        Step("u", _on("4 Ponder")),
        Step("<C-r>", _on("4 Faithless Looting")),
        Step(".", lambda v: "4 Faithless Looting" not in v.lines),
    ),
    4: (
        Step("/Lightning Bolt<CR>4ohelix<CR>", _on("4 Lightning Helix")),
        Step("<C-o>", _on("4 Lightning Bolt")),
        Step("", lambda v: v.lines.index("4 Lightning Helix")
             > v.lines.index("// Instants")),
    ),
    5: (
        Step("/Skewer<CR>2zs", _on("SB: 2 Skewer the Critics")),
        Step("zd", lambda v: v.lines.count("4 Skewer the Critics") == 1
             and not any("SB: 2 Skewer" in line for line in v.lines)),
    ),
    6: (
        Step("/Eidolon<CR>Vjj+", lambda v: {
            "4 Eidolon of the Great Revel", "4 Light Up the Stage", "4 Play with Fire",
        } <= set(v.lines)),
    ),
    7: (
        Step("/mesa<CR>", _on("4 Arid Mesa")),
        Step("n", lambda v: v.cursor_line == "4 Arid Mesa" and "search hit" in v.message),
    ),
    8: (
        Step("/Shock<CR>:s/Shock/Lightning Bolt/<CR>", _on("4 Lightning Bolt")),
        Step("u", _on("4 Shock")),
    ),
    9: (
        Step(":validate<CR>", lambda v: "Ponder" in v.shown and "Rift Bolt" in v.shown),
    ),
    10: (
        Step("/Searing<CR>gcburn<CR>", _on("4 Searing Blaze  @burn")),
        Step("<Space>fburn<CR>", lambda v: v.main._state.category_filter is not None),
        Step("<Space>f<CR>", lambda v: v.main._state.category_filter is None),
    ),
    11: (
        Step(":plan Tron<CR>/Monastery<CR>zo",
             lambda v: "-4 Monastery Swiftspear" in v.lines),
    ),
    12: (
        Step("<Space>a", lambda v: _pane(v) == "analytics"),
        Step("<Space>a", lambda v: _pane(v) is None),
    ),
    13: (
        Step(":w<CR>:commit first try<CR>", lambda v: v.message == "Snapshot: first try"),
        Step("gh", lambda v: isinstance(v.app.screen, HistoryScreen)),
        Step("q", lambda v: v.app.screen is v.main),
    ),
    14: (
        Step("ZZ", lambda v: v.app.return_code == 0),
    ),
}


async def _press(pilot: Pilot[None], keys: str) -> None:
    for token in _TOKEN.findall(keys):
        if token in _NAMED:
            name = _NAMED[token]
        elif token.startswith("<C-"):
            name = f"ctrl+{token[3:-1].lower()}"
        else:
            name = _SYMBOL_TO_TEXTUAL.get(token, token)
        await pilot.press(name)
    await pilot.pause()


def test_every_lesson_is_walked() -> None:
    numbered = {int(n) for n in re.findall(r"^// Lesson (\d+):", lesson_text(), re.M)}
    assert numbered == set(LESSONS)


@pytest.mark.asyncio
@pytest.mark.parametrize("lesson", sorted(LESSONS))
async def test_lesson_does_what_it_says(lesson: int) -> None:
    with tutor_sandbox() as deck:
        app = VimTGApp(deck_path=deck)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            main = app.screen
            assert isinstance(main, MainScreen)
            for step in LESSONS[lesson]:
                await _press(pilot, step.keys)
                view = View(app, main)
                assert step.check(view), (
                    f"lesson {lesson} after {step.keys!r}: "
                    f"cursor on {view.cursor_line!r}, message {view.message!r}"
                )
