"""Side-pane primitives: :analytics and Space a, :edhrec and Space r,
:close, and Ctrl-W w.

From docs/commands.md (The side pane & EDHREC) and docs/keybindings.md
(Windows, The leader). Focus is observed through what the keys do: with
the pane focused, j moves the pane and not the editor cursor. EDHREC
lookups are off (VIMTG_NO_EDHREC), so the pane opens on that notice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.files_and_panes_helpers import (
    COMMANDER_DECK,
    shown,
)
from tests.primitives.harness import DECK, Ed, editor

pytestmark = pytest.mark.asyncio

ANALYTICS = "#analytics-panel"
EDHREC = "#edhrec-panel"


@pytest.fixture(autouse=True)
def _no_edhrec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIMTG_NO_EDHREC", "1")


def _visible(ed: Ed, pane: str) -> bool:
    return bool(ed.screen.query_one(pane).display)


def _editor_has_focus(ed: Ed) -> bool:
    """True when j moves the editor cursor (then puts it back)."""
    ed.press("gg")
    start = ed.row
    ed.press("j")
    moved = ed.row != start
    ed.press("k")
    return moved


# ── :analytics and Space a ──────────────────────────────────────────


@pytest.mark.primitive(":analytics")
async def test_analytics_opens_the_pane_and_keeps_focus_in_the_editor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("analytics")
        await ed.settle()
        assert _visible(ed, ANALYTICS)
        assert shown(ed, ANALYTICS).lstrip().startswith("ANALYTICS")
        assert "34 main" in shown(ed, ANALYTICS)
        assert _editor_has_focus(ed)
        assert ed.text == DECK


@pytest.mark.primitive(":analytics")
async def test_analytics_pane_follows_edits(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("analytics").press("8Gdd")
        await ed.settle()
        assert "30 main" in shown(ed, ANALYTICS)


@pytest.mark.primitive("space a")
async def test_space_a_toggles_the_analytics_pane(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("<Space>a")
        await ed.settle()
        assert _visible(ed, ANALYTICS)
        ed.press("<Space>a")
        await ed.settle()
        assert not _visible(ed, ANALYTICS)
        assert ed.text == DECK


@pytest.mark.primitive("space a", "space r")
async def test_space_a_replaces_the_edhrec_pane(tmp_path: Path) -> None:
    async with editor(tmp_path, COMMANDER_DECK) as ed:
        ed.press("<Space>r")
        await ed.settle()
        assert _visible(ed, EDHREC)
        ed.press("<Esc><Space>a")
        await ed.settle()
        assert _visible(ed, ANALYTICS)
        assert not _visible(ed, EDHREC)


# ── :edhrec and Space r ─────────────────────────────────────────────


@pytest.mark.primitive(":edhrec")
async def test_edhrec_opens_a_focused_pane_for_the_commander(tmp_path: Path) -> None:
    async with editor(tmp_path, COMMANDER_DECK) as ed:
        before = ed.text
        ed.ex("edhrec")
        await ed.settle()
        assert _visible(ed, EDHREC)
        assert shown(ed, EDHREC).lstrip().startswith("EDHREC")
        assert "VIMTG_NO_EDHREC" in shown(ed, EDHREC)
        assert not _editor_has_focus(ed)
        ed.press("<Esc>")  # back to the editor, the pane stays open
        assert _visible(ed, EDHREC)
        assert _editor_has_focus(ed)
        assert ed.text == before


@pytest.mark.primitive(":edhrec")
async def test_edhrec_accepts_a_card_type_tab(tmp_path: Path) -> None:
    async with editor(tmp_path, COMMANDER_DECK) as ed:
        ed.ex("edhrec creatures")
        await ed.settle()
        assert ed.is_error is False
        assert _visible(ed, EDHREC)


@pytest.mark.primitive(":edhrec")
async def test_edhrec_with_an_unknown_card_type_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path, COMMANDER_DECK) as ed:
        ed.ex("edhrec goblins")
        await ed.settle()
        assert ed.is_error is True
        assert not _visible(ed, EDHREC)


@pytest.mark.primitive(":edhrec")
async def test_edhrec_is_commander_only(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:  # // Format: modern
        ed.ex("edhrec")
        await ed.settle()
        assert ed.is_error is True
        assert not _visible(ed, EDHREC)
        assert ed.text == DECK


@pytest.mark.primitive(":edhrec")
async def test_edhrec_without_a_cmd_line_is_an_error(tmp_path: Path) -> None:
    deck = "// Deck: Headless\n// Format: commander\n\nDCK:\n    1 Mountain\n"
    async with editor(tmp_path, deck) as ed:
        ed.ex("edhrec")
        await ed.settle()
        assert ed.is_error is True
        assert not _visible(ed, EDHREC)


@pytest.mark.primitive("space r")
async def test_space_r_toggles_the_edhrec_pane(tmp_path: Path) -> None:
    async with editor(tmp_path, COMMANDER_DECK) as ed:
        ed.press("<Space>r")
        await ed.settle()
        assert _visible(ed, EDHREC)
        ed.press("<Space>r")  # Space passes through the focused pane
        await ed.settle()
        assert not _visible(ed, EDHREC)


@pytest.mark.primitive("space r")
async def test_space_r_on_a_non_commander_deck_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("<Space>r")
        await ed.settle()
        assert ed.is_error is True
        assert not _visible(ed, EDHREC)


# ── :close ──────────────────────────────────────────────────────────


@pytest.mark.primitive(":close")
@pytest.mark.parametrize("opener", [":analytics<CR>", "<Space>a"])
async def test_close_closes_the_pane(tmp_path: Path, opener: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(opener).ex("close")
        await ed.settle()
        assert not _visible(ed, ANALYTICS)
        assert ed.is_error is False
        assert ed.text == DECK


@pytest.mark.primitive(":close")
async def test_close_from_the_focused_edhrec_pane(tmp_path: Path) -> None:
    async with editor(tmp_path, COMMANDER_DECK) as ed:
        ed.ex("edhrec").ex("close")  # ':' passes through the pane
        await ed.settle()
        assert not _visible(ed, EDHREC)


@pytest.mark.primitive(":close")
async def test_close_with_no_pane_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("close")
        assert ed.is_error is True
        assert ed.text == DECK


# ── Ctrl-W w ────────────────────────────────────────────────────────


@pytest.mark.primitive("ctrl_w w")
async def test_ctrl_w_w_moves_focus_into_the_pane_and_back(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("analytics")
        await ed.settle()
        assert _editor_has_focus(ed)
        ed.press("<C-w>w")
        assert not _editor_has_focus(ed)
        ed.press("<C-w>w")
        assert _editor_has_focus(ed)
        assert _visible(ed, ANALYTICS)
        assert ed.text == DECK


@pytest.mark.primitive("ctrl_w w")
async def test_esc_in_the_focused_pane_returns_to_the_editor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("analytics").press("<C-w>w <Esc>")
        assert _editor_has_focus(ed)
        assert _visible(ed, ANALYTICS)


@pytest.mark.primitive("ctrl_w w")
async def test_q_in_the_focused_pane_closes_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("analytics").press("<C-w>w q")
        assert not _visible(ed, ANALYTICS)
        assert _editor_has_focus(ed)
        assert ed.text == DECK


@pytest.mark.primitive("ctrl_w w")
async def test_ctrl_w_w_with_no_pane_says_so(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("<C-w>w")
        assert ed.is_error is True
        assert _editor_has_focus(ed)


@pytest.mark.primitive("ctrl_w w", ":analytics")
async def test_a_narrow_terminal_hides_the_pane_until_there_is_room(tmp_path: Path) -> None:
    async with editor(tmp_path, size=(50, 30)) as ed:
        ed.ex("analytics")
        await ed.settle()
        assert not _visible(ed, ANALYTICS)
        ed.press("<C-w>w")
        assert ed.is_error is True
        assert _editor_has_focus(ed)
        await ed.settle()
        await ed.pilot.resize_terminal(120, 40)
        await ed.settle()
        assert _visible(ed, ANALYTICS)
