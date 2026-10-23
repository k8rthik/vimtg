"""Editor data safety: crash copies keyed per deck, unsaved work kept on
every exit path, ex commands that change the deck are undoable and
dirty it, cc is one change, visual and mark ranges, count-then-register,
:saveas, and on-disk change detection.

Each test is a regression test for a repro that lost or misplaced data
on the 0.8 editor. Key sequences run with the crash net disabled.
"""

from __future__ import annotations

import os
import signal
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from textual.events import Paste

from tests.tui.test_editor_stability import CANONICAL, _cards, _deck, _feed, _keys, _screen
from vimtg.domain.card import Card
from vimtg.editor.modes import Mode
from vimtg.services.recovery import (
    list_recoveries,
    orphaned_recoveries,
    read_recovery,
    write_recovery,
)
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.greeter import GreeterMode, GreeterScreen, GreeterView
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.search_results import SearchResults

SIZE = (100, 30)


def _ex(scr: MainScreen, command: str) -> None:
    _feed(scr, [":", *command, "enter"])


def _message(scr: MainScreen) -> str:
    return scr.query_one("#command-line", CommandLine).message


def _text(scr: MainScreen) -> str:
    return scr._state.buffer.to_text()


def _card(name: str) -> Card:
    return Card.from_scryfall({
        "id": name, "name": name, "mana_cost": "{R}", "cmc": 1.0,
        "type_line": "Instant", "oracle_text": "",
    })


# ── (a) recovery copies belong to exactly one deck ─────────────────


class TestRecoveryIsPerDeck:
    @pytest.mark.asyncio
    async def test_same_name_other_directory_is_not_offered(self, tmp_path: Path) -> None:
        (tmp_path / "one").mkdir()
        (tmp_path / "two").mkdir()
        one, two = _deck(tmp_path / "one"), _deck(tmp_path / "two")
        write_recovery(one, "// Deck: Other\n\nDCK:\n4 Island\n")
        app = VimTGApp(deck_path=two)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            assert ":recover" not in _message(scr)
            _ex(scr, "recover")
            assert "No recovery file" in _message(scr)
            assert _text(scr) == CANONICAL
            # Saving two/burn.deck must leave one/burn.deck's copy alone
            _feed(scr, _keys("6G dd"))
            _ex(scr, "w")
            assert scr._state.modified is False
        assert read_recovery(one) == "// Deck: Other\n\nDCK:\n4 Island\n"
        assert two.read_text() != CANONICAL

    @pytest.mark.asyncio
    async def test_unnamed_buffer_copy_is_listed_and_reopened(self, tmp_path: Path) -> None:
        app = VimTGApp()
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            await pilot.press("escape")  # skip the new-deck prompt
            await pilot.pause()
            scr = _screen(app)
            assert scr.file_path is None
            _feed(scr, _keys("gg yy p"))
            assert scr._state.modified is True
            unsaved = _text(scr)
            app.exit()
            await pilot.pause()
        orphans = orphaned_recoveries()
        assert len(orphans) == 1 and orphans[0].original is None

        app2 = VimTGApp()
        async with app2.run_test(size=SIZE) as pilot:
            await pilot.pause()
            greeter = app2.screen
            assert isinstance(greeter, GreeterScreen)
            gv = greeter.query_one(GreeterView)
            assert "1 unsaved buffer" in str(gv.render())
            await pilot.press("R")
            await pilot.pause()
            assert gv._mode == GreeterMode.RECOVER
            assert "(unnamed buffer)" in str(gv.render())
            await pilot.press("enter")
            await pilot.pause()
            scr = _screen(app2)
            assert _text(scr) == unsaved
            assert scr._state.modified is True
            # Never offered back to itself
            assert ":recover" not in _message(scr)
            _ex(scr, "q!")
            await pilot.pause()
        assert list_recoveries() == []

    @pytest.mark.asyncio
    async def test_two_unnamed_buffers_keep_separate_copies(self, tmp_path: Path) -> None:
        for _ in range(2):
            app = VimTGApp()
            async with app.run_test(size=SIZE) as pilot:
                await pilot.pause()
                await pilot.press("n")
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                _feed(_screen(app), _keys("gg yy p"))
                app.exit()
                await pilot.pause()
        assert len(orphaned_recoveries()) == 2

    @pytest.mark.asyncio
    async def test_greeter_discards_a_copy_of_a_deleted_deck(self, tmp_path: Path) -> None:
        gone = tmp_path / "gone.deck"
        write_recovery(gone, "// Deck: Gone\n\nDCK:\n4 Island\n")
        app = VimTGApp()
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            gv = app.screen.query_one(GreeterView)
            await pilot.press("R")
            await pilot.pause()
            rendered = str(gv.render())
            assert "gone.deck" in rendered and "no longer exists" in rendered
            await pilot.press("d")
            await pilot.pause()
            assert "Discarded gone.deck" in str(gv.render())
            await pilot.press("escape")
            await pilot.pause()
            assert "unsaved buffer" not in str(gv.render())
        assert list_recoveries() == []

    @pytest.mark.asyncio
    async def test_reopened_copy_of_deleted_deck_saves_to_its_path(
        self, tmp_path: Path
    ) -> None:
        gone = tmp_path / "gone.deck"
        text = "// Deck: Gone\n// Format:\n// Tags:\n\nDCK:\n4 Island\n"
        write_recovery(gone, text)
        app = VimTGApp()
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await pilot.press("R", "enter")
            await pilot.pause()
            scr = _screen(app)
            assert scr.file_path == gone.resolve()
            _ex(scr, "w")
            assert "Written" in _message(scr)
        assert "4 Island" in gone.read_text()
        assert list_recoveries() == []

    @pytest.mark.asyncio
    async def test_menu_has_no_recovery_line_without_copies(self, tmp_path: Path) -> None:
        live = _deck(tmp_path)
        write_recovery(live, "x\n")  # its deck exists: offered on open instead
        app = VimTGApp()
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            gv = app.screen.query_one(GreeterView)
            assert "unsaved buffer" not in str(gv.render())
            await pilot.press("R")  # nothing to list: stays on the menu
            await pilot.pause()
            assert gv._mode == GreeterMode.MENU


# ── (b) every exit path keeps unsaved work ─────────────────────────


class TestExitKeepsUnsavedWork:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["ctrl+q"])
    async def test_quit_keys_leave_a_copy_the_next_open_offers(
        self, tmp_path: Path, key: str
    ) -> None:
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await pilot.press("6", "G", "d", "d")
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()
        assert path.read_text() == CANONICAL  # nothing written to the deck
        saved = read_recovery(path)
        assert saved is not None and "Goblin Guide" not in saved

        app2 = VimTGApp(deck_path=path)
        async with app2.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app2)
            assert ":recover" in _message(scr)
            _ex(scr, "recover")
            assert "Goblin Guide" not in _text(scr)

    @pytest.mark.asyncio
    async def test_clean_exit_writes_nothing(self, tmp_path: Path) -> None:
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+q")
            await pilot.pause()
        assert list_recoveries() == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("quit_keys", [["Z", "Q"], ["colon", "q", "!", "enter"]])
    async def test_deliberate_discard_deletes_the_copy(
        self, tmp_path: Path, quit_keys: list[str]
    ) -> None:
        path = _deck(tmp_path)
        write_recovery(path, "// Deck: Old crash\n")
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await pilot.press("6", "G", "d", "d", *quit_keys)
            await pilot.pause()
        assert app.return_code == 0
        assert list_recoveries() == []
        assert path.read_text() == CANONICAL

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sig", ["SIGHUP", "SIGTERM"])
    async def test_terminating_signal_saves_then_exits(
        self, tmp_path: Path, sig: str
    ) -> None:
        signum = getattr(signal, sig, None)
        if signum is None:
            pytest.skip(f"no {sig} on this platform")
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await pilot.press("6", "G", "d", "d")
            await pilot.pause()
            app.handle_terminate_signal(signum)
            await pilot.pause()
        assert app.return_code == 128 + signum
        saved = read_recovery(path)
        assert saved is not None and "Goblin Guide" not in saved

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
    async def test_real_sigterm_is_routed_to_the_handler(self, tmp_path: Path) -> None:
        before = signal.getsignal(signal.SIGTERM)
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            assert signal.SIGTERM in [sig for sig, _ in app._signals_installed]
            await pilot.press("6", "G", "d", "d")
            await pilot.pause()
            os.kill(os.getpid(), signal.SIGTERM)
            await pilot.pause()
            await pilot.pause()
        assert app.return_code == 128 + signal.SIGTERM
        assert read_recovery(path) is not None
        # Handlers are removed with the app: the test process is unaffected
        assert app._signals_installed == []
        assert signal.getsignal(signal.SIGTERM) == before

    @pytest.mark.asyncio
    async def test_home_with_unsaved_changes_keeps_a_copy(self, tmp_path: Path) -> None:
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        app._settings = replace(app.settings, confirm_quit=False)  # :home allowed
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("6G dd"))
            _ex(scr, "home")
            await pilot.pause()
            assert isinstance(app.screen, GreeterScreen)
        assert read_recovery(path) is not None

    @pytest.mark.asyncio
    async def test_edit_bang_discards_the_copy(self, tmp_path: Path) -> None:
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("6G dd"))
            scr.preserve_unsaved()
            assert read_recovery(path) is not None
            _ex(scr, "e!")
            await pilot.pause()
            assert _text(_screen(app)) == CANONICAL
        assert list_recoveries() == []

    @pytest.mark.asyncio
    async def test_save_as_removes_the_copy_written_for_the_old_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("6G dd"))
            scr.preserve_unsaved()
            _ex(scr, "saveas copy")
            assert scr.file_path == tmp_path / "copy.deck"
        assert list_recoveries() == []


# ── (c) ex commands that change the deck are undoable and dirty it ──


class TestSortIsAChange:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("setup", "command"),
        [
            ("10G", "sort!"),
            ("10G", "sort! name"),
            ("10G", "%sort!"),
            ("10G", "10,12sort!"),
            ("6G", "sort! cmc"),
        ],
    )
    async def test_sort_marks_modified_and_undoes_in_one_step(
        self, tmp_path: Path, setup: str, command: str
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys(setup))
            _ex(scr, command)
            assert _text(scr) != CANONICAL
            assert scr._state.modified is True
            # :q refuses instead of silently losing the sort
            _ex(scr, "q")
            assert app.is_running and "Unsaved changes" in _message(scr)
            _feed(scr, ["u"])
            assert _text(scr) == CANONICAL
            assert scr._state.modified is False

    @pytest.mark.asyncio
    async def test_visual_sort_sorts_the_selection(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("10G V j :"))
            cl = scr.query_one("#command-line", CommandLine)
            assert cl.text == "'<,'>"
            _feed(scr, [*"sort!", "enter"])
            cards = _cards(scr)
            assert cards[2:5] == ["4 Searing Blaze", "4 Lightning Bolt", "4 Skullcrack"]
            assert scr._state.modified is True
            _feed(scr, ["u"])
            assert _text(scr) == CANONICAL

    @pytest.mark.asyncio
    async def test_sort_already_in_order_is_not_a_change(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("10G"))
            _ex(scr, "sort name")
            assert scr._state.modified is False
            assert not scr._state.history.can_undo

    @pytest.mark.asyncio
    async def test_sort_by_card_field_without_data_says_why(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("10G"))
            _ex(scr, "sort cmc")
            assert "by name (no card data for cmc)" in _message(scr)

    @pytest.mark.asyncio
    async def test_duntag_of_a_missing_tag_is_not_a_change(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _ex(scr, "duntag aggro")
            assert scr._state.modified is False
            _ex(scr, "q")
        assert app.return_code == 0


# ── (d) cc + a card is one change ──────────────────────────────────


class TestChangeIsOneUndoStep:
    @pytest.mark.asyncio
    async def test_cc_then_card_undoes_in_one_step(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("10G cc"))
            assert scr._state.mode_mgr.current == Mode.INSERT
            scr.query_one("#search-results", SearchResults).results = [_card("Shock")]
            _feed(scr, ["enter"])
            assert "Shock" in _text(scr) and "Lightning Bolt" not in _text(scr)
            _feed(scr, ["u"])
            assert _text(scr) == CANONICAL
            assert scr._state.modified is False
            _feed(scr, ["ctrl_r"])
            assert "Shock" in _text(scr) and "Lightning Bolt" not in _text(scr)

    @pytest.mark.asyncio
    async def test_cancelled_cc_then_o_card_are_separate_changes(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("10G cc") + ["escape"])
            after_delete = _text(scr)
            _feed(scr, ["o"])
            scr.query_one("#search-results", SearchResults).results = [_card("Shock")]
            _feed(scr, ["enter"])
            _feed(scr, ["u"])
            assert _text(scr) == after_delete  # only the o card went


# ── (e) visual and mark ranges, E16 ────────────────────────────────


class TestRanges:
    @pytest.mark.asyncio
    async def test_visual_colon_d_deletes_the_selection(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("10G V j :") + ["d", "enter"])
            text = _text(scr)
            assert "Lightning Bolt" not in text and "Searing Blaze" not in text
            assert "Skullcrack" in text
            assert scr._state.mode_mgr.current == Mode.NORMAL
            assert scr._state.visual_anchor is None

    @pytest.mark.asyncio
    async def test_mark_range(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("6G ma 7G mb gg"))
            _ex(scr, "'a,'bd")
            assert "Goblin Guide" not in _text(scr)
            assert "Monastery Swiftspear" not in _text(scr)
            _ex(scr, "'z,'zd")
            assert "E20" in _message(scr)

    @pytest.mark.asyncio
    async def test_range_past_the_end_is_e16(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _ex(scr, "999d")
            assert "E16: Invalid range" in _message(scr)
            assert _text(scr) == CANONICAL
            assert scr._state.modified is False
            # A bare :999 still goes to the last line, as in vim
            _ex(scr, "999")
            assert scr._state.cursor.row == scr._state.buffer.line_count() - 1


# ── (f) count before a register ────────────────────────────────────


class TestCountThenRegister:
    @pytest.mark.asyncio
    async def test_count_register_put(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys('15G yy 3"0p'))
            assert _cards(scr).count("20 Mountain") == 4

    @pytest.mark.asyncio
    async def test_count_register_delete(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys('10G 2"add'))
            assert "Lightning Bolt" not in _text(scr)
            assert "Searing Blaze" not in _text(scr)
            assert scr._state.registers.get("a").content == (
                "4 Lightning Bolt", "4 Searing Blaze",
            )


# ── (g) :w name / :saveas ──────────────────────────────────────────


class TestSaveAs:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("command", ["w other", "saveas other", "sav other"])
    async def test_switching_file_is_announced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
    ) -> None:
        monkeypatch.chdir(tmp_path)
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("6G dd"))
            _ex(scr, command)
            msg = _message(scr)
            assert "now editing other.deck" in msg and "burn.deck" in msg
            assert scr.file_path == tmp_path / "other.deck"
        assert path.read_text() == CANONICAL

    @pytest.mark.asyncio
    async def test_saveas_needs_a_name(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _ex(scr, "saveas")
            assert "E471" in _message(scr)


# ── (h) pastes are recorded in macros ──────────────────────────────


class TestPasteInMacro:
    @pytest.mark.asyncio
    async def test_macro_replays_a_paste(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("qa"))
            scr.on_paste(Paste("2 Shock\n"))
            _feed(scr, ["q"])
            assert "2 Shock" in _text(scr)
            _feed(scr, ["u"])
            assert _text(scr) == CANONICAL
            _feed(scr, _keys("@a"))
            assert "2 Shock" in _text(scr)


# ── (i) on-disk changes and :x ─────────────────────────────────────


class TestDiskChanges:
    @pytest.mark.asyncio
    async def test_deleted_file_has_its_own_message(self, tmp_path: Path) -> None:
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            path.unlink()
            _feed(scr, _keys("6G dd"))
            _ex(scr, "w")
            msg = _message(scr)
            assert "no longer exists" in msg and "changed on disk" not in msg
            assert not path.exists()
            _ex(scr, "w!")
        assert path.exists()

    @pytest.mark.asyncio
    async def test_same_size_same_mtime_rewrite_is_caught(self, tmp_path: Path) -> None:
        path = _deck(tmp_path)
        before = path.stat()
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            outside = CANONICAL.replace("Skullcrack", "Skullcrapz")
            assert len(outside) == len(CANONICAL)
            path.write_text(outside)
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            _feed(scr, _keys("6G dd"))
            _ex(scr, "w")
            assert "changed on disk" in _message(scr)
        assert path.read_text() == outside

    @pytest.mark.asyncio
    async def test_touch_without_change_is_not_a_conflict(self, tmp_path: Path) -> None:
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            st = path.stat()
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
            _feed(scr, _keys("6G dd"))
            _ex(scr, "w")
            assert "Written" in _message(scr)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("keys", [["colon", "x", "enter"], ["Z", "Z"]])
    async def test_x_does_not_rewrite_an_unmodified_deck(
        self, tmp_path: Path, keys: list[str]
    ) -> None:
        path = _deck(tmp_path)
        old = path.stat().st_mtime_ns - 10_000_000_000
        os.utime(path, ns=(old, old))
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await pilot.press(*keys)
            await pilot.pause()
        assert app.return_code == 0
        assert path.stat().st_mtime_ns == old


# ── (h) validate names the line the editor shows ───────────────────


class TestValidateMatchesEditor:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "text",
        [
            "// Deck: X\n0 Bolt\n",
            "// Deck: X\n// Format: modern\n\n4 Goblin Guide\n0 Bolt\n",
            "4 Goblin Guide\n// Instant\n0 Bolt\n",
        ],
    )
    async def test_validate_line_is_the_editor_row(self, tmp_path: Path, text: str) -> None:
        import re

        from click.testing import CliRunner

        from vimtg.cli import main

        path = tmp_path / "q.deck"
        path.write_text(text)
        output = CliRunner().invoke(main, ["validate", str(path)]).output
        match = re.search(r"q\.deck:(\d+): error: Invalid quantity 0 for Bolt"
                          r"(?: \(line (\d+) in the vimtg editor\))?", output)
        assert match is not None, output
        file_line = int(match.group(1))
        editor_line = int(match.group(2) or file_line)
        assert text.split("\n")[file_line - 1] == "0 Bolt"

        app = VimTGApp(deck_path=path)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            buf = _screen(app)._state.buffer
            assert buf.get_line(editor_line - 1).text == "0 Bolt"
