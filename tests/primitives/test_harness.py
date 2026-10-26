"""The harness opens the canonical deck unchanged and drives real keys."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeClipboard
from tests.primitives.harness import DECK, editor, keys
from vimtg.editor.modes import Mode


def test_keys_spells_named_keys_and_ignores_spaces() -> None:
    assert keys("3dd <C-r> :w<CR>") == ["3", "d", "d", "ctrl_r", ":", "w", "enter"]


def test_keys_rejects_an_unknown_name() -> None:
    with pytest.raises(ValueError, match="<C-q>"):
        keys("<C-q>")


@pytest.mark.asyncio
async def test_opening_the_canonical_deck_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        assert ed.text == DECK
        assert ed.modified is False
        assert ed.mode is Mode.NORMAL


@pytest.mark.asyncio
async def test_rows_match_the_map_in_the_harness(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        assert ed.lines[7].strip() == "4 Goblin Guide"
        assert ed.lines[13].strip() == "1 Fire // Ice"
        assert ed.lines[20].strip() == "2 Rest in Peace"
        ed.press("8G")
        assert ed.row == 7


@pytest.mark.asyncio
async def test_clipboard_register_yank_stays_in_the_fake_clipboard(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "+yy')
        assert ed.message == "Copied register + (1 line) to clipboard"
    assert clipboard.text == "    4 Goblin Guide\n"
