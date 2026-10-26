"""File and session primitives: write, quit, edit, new, home, recover, tutor.

Every expected file body and message comes from docs/commands.md (File)
and docs/keybindings.md (ZZ / ZQ). A session that ends is observed as
the app no longer running (`app_ended`); a session that goes on is the
editor still on top with its text unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.primitives.harness import DECK, editor
from tests.primitives.test_files_and_panes_helpers import (
    app_ended,
    ex,
    in_editor,
    keys,
    settle,
)
from vimtg.tui.screens.greeter import GreeterScreen

pytestmark = pytest.mark.asyncio

# The canonical deck after "8Gdd" (row 7, "4 Goblin Guide", deleted).
EDITED = DECK.replace("    4 Goblin Guide\n", "")
DELETE_GUIDE = "8Gdd"
OLD_MTIME = 1_000_000


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Relative names (:w copy, :e other) resolve against the cwd."""
    monkeypatch.chdir(tmp_path)


def _age(path: Path) -> None:
    os.utime(path, (OLD_MTIME, OLD_MTIME))


# ── :w ──────────────────────────────────────────────────────────────


@pytest.mark.primitive(":w")
async def test_w_writes_the_buffer_to_the_deck_file(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("w"))
        assert ed.saved() == EDITED
        assert ed.modified is False
        assert ed.is_error is False


@pytest.mark.primitive(":w")
async def test_w_file_writes_a_copy_and_keeps_editing_the_deck(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("w copy"))
        assert (tmp_path / "copy.deck").read_text(encoding="utf-8") == EDITED
        assert ed.message == '"copy.deck" written'
        assert ed.saved() == DECK
        assert ed.modified is True
        ed.press(ex("w"))
        assert ed.saved() == EDITED


@pytest.mark.primitive(":w")
async def test_w_refuses_to_overwrite_another_existing_file(tmp_path: Path) -> None:
    (tmp_path / "other.deck").write_text("keep me\n", encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("w other"))
        assert ed.is_error is True
        assert "E13" in ed.message
        assert (tmp_path / "other.deck").read_text(encoding="utf-8") == "keep me\n"
        assert ed.text == EDITED


@pytest.mark.primitive(":w")
async def test_w_bang_overwrites_another_existing_file(tmp_path: Path) -> None:
    (tmp_path / "other.deck").write_text("keep me\n", encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("w! other"))
        assert ed.is_error is False
        assert (tmp_path / "other.deck").read_text(encoding="utf-8") == EDITED


@pytest.mark.primitive(":w")
async def test_w_refuses_a_deck_file_changed_on_disk_until_bang(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        outside = "// changed by another tool\n" + DECK
        ed.path.write_text(outside, encoding="utf-8")
        _age(ed.path)
        ed.press(DELETE_GUIDE + ex("w"))
        assert ed.is_error is True
        assert ed.saved() == outside
        ed.press(ex("w!"))
        assert ed.saved() == EDITED


@pytest.mark.primitive(":w")
async def test_w_into_a_directory_is_refused(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("w sub/"))
        assert ed.is_error is True
        assert list((tmp_path / "sub").iterdir()) == []
        assert ed.saved() == DECK


@pytest.mark.primitive(":w", ":import")
async def test_w_names_an_unnamed_deck_after_its_deck_line(tmp_path: Path) -> None:
    (tmp_path / "in.deck").write_text(
        "// Deck: Mono-Red Burn\n// Format: modern\n\nDCK:\n    4 Lightning Bolt\n",
        encoding="utf-8",
    )
    async with editor(tmp_path) as ed:
        ed.press(ex("import in.deck"))
        await settle(ed)
        ed.press(ex("w"))
        written = tmp_path / "mono-red-burn.deck"
        assert written.exists()
        assert "4 Lightning Bolt" in written.read_text(encoding="utf-8")
        assert ed.saved() == DECK


@pytest.mark.primitive(":w", ":import")
async def test_w_numbers_the_name_when_the_slug_is_taken(tmp_path: Path) -> None:
    (tmp_path / "in.deck").write_text(
        "// Deck: Mono-Red Burn\n// Format: modern\n\nDCK:\n    4 Lightning Bolt\n",
        encoding="utf-8",
    )
    (tmp_path / "mono-red-burn.deck").write_text("taken\n", encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press(ex("import in.deck"))
        await settle(ed)
        ed.press(ex("w"))
        assert (tmp_path / "mono-red-burn.deck").read_text(encoding="utf-8") == "taken\n"
        second = tmp_path / "mono-red-burn-2.deck"
        assert "4 Lightning Bolt" in second.read_text(encoding="utf-8")


# ── :saveas ─────────────────────────────────────────────────────────


@pytest.mark.primitive(":saveas")
async def test_saveas_writes_the_new_file_and_edits_it_from_then_on(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("saveas new"))
        new = tmp_path / "new.deck"
        assert new.read_text(encoding="utf-8") == EDITED
        assert ed.modified is False
        ed.press("G dd" + ex("w"))
        assert "Rest in Peace" not in new.read_text(encoding="utf-8")
        assert ed.saved() == DECK


@pytest.mark.primitive(":saveas")
async def test_saveas_refuses_an_existing_file_until_bang(tmp_path: Path) -> None:
    taken = tmp_path / "taken.deck"
    taken.write_text("keep me\n", encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("saveas taken"))
        assert ed.is_error is True
        assert "E13" in ed.message
        assert taken.read_text(encoding="utf-8") == "keep me\n"
        ed.press(ex("saveas! taken"))
        assert taken.read_text(encoding="utf-8") == EDITED
        assert ed.modified is False


@pytest.mark.primitive(":saveas")
async def test_saveas_without_a_file_name_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("saveas"))
        assert ed.is_error is True
        assert ed.saved() == DECK
        assert sorted(p.name for p in tmp_path.iterdir()) == ["burn.deck"]


# ── :wq ─────────────────────────────────────────────────────────────


@pytest.mark.primitive(":wq")
async def test_wq_writes_the_deck_and_ends_the_session(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("wq"))
        assert ed.saved() == EDITED
        assert await app_ended(ed)


@pytest.mark.primitive(":wq")
async def test_wq_file_with_unsaved_changes_writes_the_copy_and_stays(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("wq copy"))
        assert (tmp_path / "copy.deck").read_text(encoding="utf-8") == EDITED
        assert "E37" in ed.message
        assert not await app_ended(ed)
        assert ed.saved() == DECK


@pytest.mark.primitive(":wq")
async def test_wq_bang_file_writes_the_copy_and_ends(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("wq! copy"))
        assert (tmp_path / "copy.deck").read_text(encoding="utf-8") == EDITED
        assert await app_ended(ed)
        assert ed.saved() == DECK


@pytest.mark.primitive(":wq", ":analytics")
async def test_wq_with_a_pane_open_saves_and_closes_the_pane(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("analytics") + DELETE_GUIDE + ex("wq"))
        assert ed.saved() == EDITED
        assert not await app_ended(ed)
        assert ed.screen.query_one("#analytics-panel").display is False


# ── :x and ZZ ───────────────────────────────────────────────────────


@pytest.mark.primitive(":x")
async def test_x_writes_a_modified_deck_and_ends(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("x"))
        assert ed.saved() == EDITED
        assert await app_ended(ed)


@pytest.mark.primitive(":x")
async def test_x_leaves_an_unmodified_deck_file_untouched(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        _age(ed.path)
        ed.press(ex("x"))
        assert await app_ended(ed)
        assert ed.path.stat().st_mtime == OLD_MTIME
        assert ed.saved() == DECK


@pytest.mark.primitive(":x", ":analytics")
async def test_x_with_a_pane_open_closes_the_pane(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("analytics") + ex("x"))
        assert not await app_ended(ed)
        assert ed.screen.query_one("#analytics-panel").display is False


@pytest.mark.primitive("ZZ")
async def test_zz_writes_a_modified_deck_and_ends(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + "ZZ")
        assert ed.saved() == EDITED
        assert await app_ended(ed)


@pytest.mark.primitive("ZZ")
async def test_zz_leaves_an_unmodified_deck_file_untouched(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        _age(ed.path)
        ed.press("ZZ")
        assert await app_ended(ed)
        assert ed.path.stat().st_mtime == OLD_MTIME


@pytest.mark.primitive("ZQ", ":recover")
async def test_zq_ends_discarding_changes_and_their_recovery_copy(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + "ZQ")
        assert await app_ended(ed)
        assert ed.saved() == DECK
    async with editor(tmp_path) as ed:
        ed.press(ex("recover"))
        assert ed.is_error is True
        assert ed.text == DECK


# ── :q ──────────────────────────────────────────────────────────────


@pytest.mark.primitive(":q")
async def test_q_ends_an_unmodified_session(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("q"))
        assert await app_ended(ed)
        assert ed.saved() == DECK


@pytest.mark.primitive(":q")
async def test_q_with_unsaved_changes_is_refused_with_e37(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("q"))
        assert ed.is_error is True
        assert ed.message.startswith("E37")
        assert not await app_ended(ed)
        assert ed.text == EDITED
        assert ed.saved() == DECK


@pytest.mark.primitive(":q", ":recover")
async def test_q_bang_ends_discarding_changes_and_their_recovery_copy(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("q!"))
        assert await app_ended(ed)
        assert ed.saved() == DECK
    async with editor(tmp_path) as ed:
        ed.press(ex("recover"))
        assert ed.is_error is True
        assert ed.text == DECK


@pytest.mark.primitive(":q", ":analytics")
async def test_q_with_a_pane_open_closes_the_pane_not_the_editor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("analytics") + ex("q"))
        assert not await app_ended(ed)
        assert ed.screen.query_one("#analytics-panel").display is False
        assert ed.text == EDITED


@pytest.mark.primitive(":q", ":recover")
async def test_q_without_confirm_quit_ends_and_keeps_the_changes_for_recover(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("set noconfirmquit") + DELETE_GUIDE + ex("q"))
        assert await app_ended(ed)
        assert ed.saved() == DECK
    async with editor(tmp_path) as ed:
        ed.press(ex("recover"))
        assert ed.text == EDITED


# ── :edit ───────────────────────────────────────────────────────────

OTHER = "// Deck: Other\n// Format: legacy\n\nDCK:\n    4 Lightning Bolt\n"


@pytest.mark.primitive(":edit")
async def test_edit_file_opens_that_deck_in_place_of_this_one(tmp_path: Path) -> None:
    (tmp_path / "other.deck").write_text(OTHER, encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press(ex("e other.deck"))
        await settle(ed)
        assert ed.cards == ["4 Lightning Bolt"]
        assert "// Deck: Other" in ed.text
        assert ed.saved() == DECK


@pytest.mark.primitive(":edit")
async def test_edit_tries_the_deck_suffix(tmp_path: Path) -> None:
    (tmp_path / "other.deck").write_text(OTHER, encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press(ex("e other"))
        await settle(ed)
        assert ed.cards == ["4 Lightning Bolt"]


@pytest.mark.primitive(":edit")
async def test_edit_with_unsaved_changes_is_refused_with_e37(tmp_path: Path) -> None:
    (tmp_path / "other.deck").write_text(OTHER, encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("e other.deck"))
        await settle(ed)
        assert ed.message.startswith("E37")
        assert ed.text == EDITED


@pytest.mark.primitive(":edit")
async def test_edit_bang_alone_reloads_the_deck_dropping_changes(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("e!"))
        await settle(ed)
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive(":edit")
async def test_edit_bang_file_drops_changes_and_opens_that_deck(tmp_path: Path) -> None:
    (tmp_path / "other.deck").write_text(OTHER, encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("e! other.deck"))
        await settle(ed)
        assert ed.cards == ["4 Lightning Bolt"]
        assert ed.saved() == DECK


@pytest.mark.primitive(":edit")
async def test_edit_alone_rereads_a_deck_changed_on_disk(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.path.write_text(EDITED, encoding="utf-8")
        ed.press(ex("e"))
        await settle(ed)
        assert ed.text == EDITED


@pytest.mark.primitive(":edit")
async def test_edit_a_missing_file_opens_a_new_deck_that_w_creates(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("e fresh.deck"))
        await keys(ed, "escape")  # skip the new-deck questions
        assert ed.cards == []
        ed.press(ex("w"))
        assert (tmp_path / "fresh.deck").exists()
        assert ed.saved() == DECK


@pytest.mark.primitive(":edit")
async def test_edit_a_directory_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    async with editor(tmp_path) as ed:
        ed.press(ex("e sub"))
        await settle(ed)
        assert ed.is_error is True
        assert ed.text == DECK


# ── :enew ───────────────────────────────────────────────────────────


@pytest.mark.primitive(":enew")
async def test_enew_asks_for_name_and_format_of_an_unnamed_deck(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("enew"))
        await keys(
            ed, "M", "o", "n", "o", "space", "R", "e", "d", "enter",
            "m", "o", "d", "e", "r", "n", "enter",
        )
        assert in_editor(ed)
        assert "// Deck: Mono Red" in ed.text
        assert "// Format: modern" in ed.text
        assert ed.cards == []
        ed.press(ex("w"))
        assert (tmp_path / "mono-red.deck").exists()
        assert ed.saved() == DECK


@pytest.mark.primitive(":enew")
async def test_enew_with_unsaved_changes_is_refused_with_e37(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("enew"))
        await settle(ed)
        assert in_editor(ed)
        assert ed.message.startswith("E37")
        assert ed.text == EDITED


@pytest.mark.primitive(":enew")
async def test_enew_bang_drops_changes_for_a_new_deck(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("enew!"))
        await keys(ed, "escape")
        assert ed.cards == []
        assert ed.saved() == DECK


# ── :home ───────────────────────────────────────────────────────────


@pytest.mark.primitive(":home")
async def test_home_returns_to_the_greeter(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("home"))
        await settle(ed)
        assert isinstance(ed.app.screen, GreeterScreen)
        assert ed.app.is_running
        assert ed.saved() == DECK


@pytest.mark.primitive(":home")
async def test_home_with_unsaved_changes_is_refused_with_e37(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("home"))
        await settle(ed)
        assert in_editor(ed)
        assert ed.message.startswith("E37")
        assert ed.text == EDITED


@pytest.mark.primitive(":home")
async def test_home_bang_drops_changes_and_goes_to_the_greeter(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("home!"))
        await settle(ed)
        assert isinstance(ed.app.screen, GreeterScreen)
        assert ed.saved() == DECK


# ── :recover ────────────────────────────────────────────────────────


@pytest.mark.primitive(":recover")
async def test_recover_without_a_copy_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("recover"))
        assert ed.is_error is True
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive(":recover")
async def test_recover_loads_changes_left_unsaved_by_ctrl_q(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE)
        await keys(ed, "ctrl+q")
        assert not ed.app.is_running
        assert ed.saved() == DECK
    async with editor(tmp_path) as ed:
        assert ":recover" in ed.message  # the copy is offered on open
        ed.press(ex("recover"))
        assert ed.text == EDITED
        assert ed.modified is True
        assert ed.saved() == DECK


@pytest.mark.primitive(":recover")
async def test_recover_bang_deletes_the_copy(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE)
        await keys(ed, "ctrl+q")
    async with editor(tmp_path) as ed:
        ed.press(ex("recover!"))
        assert ed.is_error is False
        ed.press(ex("recover"))
        assert ed.is_error is True
        assert ed.text == DECK


@pytest.mark.primitive(":recover", ":w")
async def test_w_after_recover_removes_the_copy(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE)
        await keys(ed, "ctrl+q")
    async with editor(tmp_path) as ed:
        ed.press(ex("recover") + ex("w"))
        assert ed.saved() == EDITED
    async with editor(tmp_path, EDITED) as ed:
        assert ":recover" not in ed.message
        ed.press(ex("recover"))
        assert ed.is_error is True


# ── :tutor ──────────────────────────────────────────────────────────


@pytest.mark.primitive(":tutor")
async def test_tutor_leaves_the_deck_for_the_lesson_deck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vimtg import cli
    from vimtg.tutor import lesson_text

    async with editor(tmp_path) as ed:
        ed.press(ex("tutor"))
        assert await app_ended(ed)
        result = ed.app.return_value
    opened: list[str] = []

    def fake_run_editor(deck_path: Path | None) -> object:
        assert deck_path is not None
        opened.append(deck_path.read_text(encoding="utf-8"))
        return None

    # What the CLI does with the app's result: open the lesson deck
    monkeypatch.setattr(cli, "_run_editor", fake_run_editor)
    cli._follow_into_tutor(result)
    assert opened == [lesson_text()]
    assert (tmp_path / "burn.deck").read_text(encoding="utf-8") == DECK


@pytest.mark.primitive(":tutor")
async def test_tutor_with_unsaved_changes_is_refused_with_e37(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("tutor"))
        assert ed.message.startswith("E37")
        assert not await app_ended(ed)
        assert ed.text == EDITED


@pytest.mark.primitive(":tutor")
async def test_tutor_bang_drops_changes_and_leaves(tmp_path: Path) -> None:
    from vimtg.tutor import LAUNCH_TUTOR

    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("Tutor!"))
        assert await app_ended(ed)
        assert ed.app.return_value == LAUNCH_TUTOR
        assert ed.saved() == DECK
