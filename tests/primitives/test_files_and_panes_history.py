"""Deck history primitives: :commit, :checkpoint, :history and gh.

From docs/commands.md (Version control) and the history-overlay table in
docs/keybindings.md. The Snapshots panel is read as the text it shows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeClipboard
from tests.primitives.files_and_panes_helpers import (
    in_editor,
    overlay_title,
    shown,
)
from tests.primitives.harness import DECK, Ed, editor

pytestmark = pytest.mark.asyncio

EDITED = DECK.replace("    4 Goblin Guide\n", "")
DELETE_GUIDE = "8Gdd"


async def _snapshots(ed: Ed) -> str:
    """Open the history overlay and return what its Snapshots panel shows."""
    ed.ex("history")
    await ed.settle()
    return shown(ed, "#snapshots-panel")


async def _unnamed_deck(ed: Ed, clipboard: FakeClipboard) -> None:
    """Replace the deck with an unnamed buffer that has never been written."""
    clipboard.text = "4 Lightning Bolt\n"
    ed.ex("import")
    await ed.settle()
    assert in_editor(ed)


# ── :commit ─────────────────────────────────────────────────────────


@pytest.mark.primitive(":commit", ":history")
async def test_commit_adds_a_snapshot_the_history_overlay_lists(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex('commit "first cut"')
        assert ed.is_error is False
        panel = await _snapshots(ed)
        assert "History  (1)" in panel
        assert "first cut" in panel


@pytest.mark.primitive(":commit")
async def test_commit_of_a_changed_deck_adds_another_snapshot(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("commit one").press(DELETE_GUIDE).ex("commit two")
        panel = await _snapshots(ed)
        assert "History  (2)" in panel
        assert panel.index("two") < panel.index("one")  # newest first


@pytest.mark.primitive(":commit", ":w")
async def test_commit_right_after_w_names_the_save_snapshot(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE).ex("w").ex("commit named")
        panel = await _snapshots(ed)
        assert "History  (1)" in panel
        assert "named" in panel


@pytest.mark.primitive(":commit")
async def test_commit_without_a_message_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("commit")
        assert ed.is_error is True
        assert ed.text == DECK
        assert "History  (0)" in await _snapshots(ed)


@pytest.mark.primitive(":commit")
async def test_commit_on_a_deck_never_written_says_e32(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        await _unnamed_deck(ed, clipboard)
        before = ed.text
        ed.ex("commit msg")
        assert ed.is_error is True
        assert ed.message.startswith("E32")
        assert ed.text == before


# ── :checkpoint ─────────────────────────────────────────────────────


@pytest.mark.primitive(":checkpoint", ":history")
async def test_checkpoint_commits_and_tags_the_snapshot(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("checkpoint v1")
        assert ed.is_error is False
        panel = await _snapshots(ed)
        assert "History  (1)" in panel
        assert "(v1)" in panel


@pytest.mark.primitive(":checkpoint")
async def test_checkpoint_without_a_name_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("checkpoint")
        assert ed.is_error is True
        assert "History  (0)" in await _snapshots(ed)


@pytest.mark.primitive(":checkpoint")
async def test_checkpoint_on_a_deck_never_written_says_e32(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        await _unnamed_deck(ed, clipboard)
        ed.ex("checkpoint v1")
        assert ed.message.startswith("E32")


# ── :history and gh ─────────────────────────────────────────────────


@pytest.mark.primitive(":history")
@pytest.mark.parametrize("close", ["q", pytest.param("<Esc>", id="escape")])
async def test_history_opens_the_overlay_and_closes_back_to_the_deck(
    tmp_path: Path, close: str
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE).ex("history")
        await ed.settle()
        assert overlay_title(ed) == "History — burn.deck"
        await ed.type(close)
        assert in_editor(ed)
        assert ed.text == EDITED


@pytest.mark.primitive("gh")
async def test_gh_toggles_the_history_overlay(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("gh")
        await ed.settle()
        assert overlay_title(ed) == "History — burn.deck"
        await ed.type("gh")
        assert in_editor(ed)
        assert ed.text == DECK


@pytest.mark.primitive(":history", "gh")
@pytest.mark.parametrize("opener", [":history<CR>", "gh"])
async def test_history_of_a_deck_never_written_says_e32(
    tmp_path: Path, clipboard: FakeClipboard, opener: str
) -> None:
    async with editor(tmp_path) as ed:
        await _unnamed_deck(ed, clipboard)
        ed.press(opener)
        await ed.settle()
        assert in_editor(ed)
        assert ed.message.startswith("E32")


async def _restore_original(ed: Ed) -> None:
    """Commit the deck, commit an edit, then restore the first snapshot."""
    ed.ex("commit original").press(DELETE_GUIDE).ex("commit trimmed").press("gh")
    await ed.settle()
    # Snapshots panel: newest first, so j selects "original"
    await ed.type("jRy<CR>")


@pytest.mark.primitive("gh", ":commit")
async def test_restoring_a_snapshot_loads_it_into_the_editor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await _restore_original(ed)
        assert in_editor(ed)
        assert ed.text == DECK


@pytest.mark.primitive("gh", ":history")
async def test_restoring_a_snapshot_records_the_restore_in_the_history(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        await _restore_original(ed)
        assert "History  (3)" in await _snapshots(ed)
