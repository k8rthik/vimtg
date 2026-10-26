"""Commands that take no argument refuse one and do nothing.

vim answers `:q junk` with E488 (trailing characters) and runs nothing;
vimtg's own :combos, :sync and :tips refuse a stray argument the same
way. A command handed one must leave the session as it was: same
screen, no pane, deck unchanged, an error on the command line.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.files_and_panes_helpers import (
    app_ended,
    ex,
    in_editor,
    keys,
)
from tests.primitives.harness import DECK, Ed, editor

pytestmark = pytest.mark.asyncio


def _bug(command: str, actual: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(
        strict=True,
        reason=f"BUG: :{command} junk should fail like E488 and do nothing; {actual}",
    )


async def _refused_untouched(ed: Ed, before: str) -> None:
    assert not await app_ended(ed), "the session ended"
    assert in_editor(ed), f"left the editor for {type(ed.app.screen).__name__}"
    assert ed.is_error is True
    assert ed.text == before


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            "q", marks=[pytest.mark.primitive(":q"), _bug("q", "it quits")]
        ),
        pytest.param(
            "tutor",
            marks=[pytest.mark.primitive(":tutor"), _bug("tutor", "it leaves for the tutor")],
        ),
        pytest.param(
            "home", marks=[pytest.mark.primitive(":home"), _bug("home", "it opens the greeter")]
        ),
        pytest.param(
            "enew", marks=[pytest.mark.primitive(":enew"), _bug("enew", "it opens a new deck")]
        ),
        pytest.param(
            "history",
            marks=[pytest.mark.primitive(":history"), _bug("history", "it opens the overlay")],
        ),
        pytest.param(
            "config",
            marks=[pytest.mark.primitive(":config"), _bug("config", "it opens the settings")],
        ),
        pytest.param(
            "validate",
            marks=[pytest.mark.primitive(":validate"), _bug("validate", "it validates, no error")],
        ),
    ],
)
async def test_command_that_takes_no_argument_refuses_one(tmp_path: Path, command: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex(f"{command} junk"))
        await _refused_untouched(ed, DECK)


@pytest.mark.primitive(":analytics")
@pytest.mark.xfail(
    strict=True,
    reason="BUG: :analytics junk should fail like E488 and do nothing; it opens the pane",
)
async def test_analytics_refuses_an_argument(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("analytics junk"))
        await _refused_untouched(ed, DECK)
        assert not ed.screen.query_one("#analytics-panel").display


@pytest.mark.primitive(":close")
@pytest.mark.xfail(
    strict=True,
    reason="BUG: :close junk should fail like E488 and do nothing; it closes the pane",
)
async def test_close_refuses_an_argument(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("analytics") + ex("close junk"))
        await _refused_untouched(ed, DECK)
        assert ed.screen.query_one("#analytics-panel").display


@pytest.mark.primitive(":recover")
@pytest.mark.xfail(
    strict=True,
    reason="BUG: :recover junk should fail like E488 and do nothing; it loads the copy",
)
async def test_recover_refuses_an_argument(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8Gdd")
        await keys(ed, "ctrl+q")  # leaves a recovery copy
    async with editor(tmp_path) as ed:
        ed.press(ex("recover junk"))
        await _refused_untouched(ed, DECK)
