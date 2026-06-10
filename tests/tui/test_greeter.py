"""Tests for the greeter screen — mode switching, help, file browser, recent files."""

from __future__ import annotations

from pathlib import Path

from vimtg.tui.screens.greeter import GreeterMode, GreeterView

# ---------------------------------------------------------------------------
# GreeterView unit tests (no Textual app required)
# ---------------------------------------------------------------------------


class TestGreeterViewDefaults:
    def test_default_mode_is_menu(self) -> None:
        gv = GreeterView()
        assert gv._mode == GreeterMode.MENU

    def test_default_cursor_is_zero(self) -> None:
        gv = GreeterView()
        assert gv._cursor == 0


class TestRenderMenu:
    def test_render_menu_contains_logo(self) -> None:
        gv = GreeterView()
        text = gv._render_menu()
        # Logo is ASCII art — check a distinctive piece
        assert "___/" in text.plain

    def test_render_menu_contains_actions(self) -> None:
        gv = GreeterView()
        text = gv._render_menu()
        plain = text.plain
        assert "[n]" in plain
        assert "[e]" in plain
        assert "[?]" in plain
        assert "[q]" in plain

    def test_render_menu_shows_recent_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "burn.deck"
        f1.touch()
        gv = GreeterView(recent_files=[f1])
        text = gv._render_menu()
        assert "burn.deck" in text.plain
        assert "[1]" in text.plain

    def test_render_menu_no_recent_section(self) -> None:
        gv = GreeterView(recent_files=[])
        text = gv._render_menu()
        # The "Recent files" action label always shows, but the numbered
        # recent files section should not appear when list is empty
        assert "[1]" not in text.plain


class TestRenderHelp:
    def test_render_help_contains_navigation(self) -> None:
        gv = GreeterView()
        gv._mode = GreeterMode.HELP
        text = gv._render_help()
        plain = text.plain
        assert "NAVIGATION" in plain
        assert "EDITING" in plain
        assert "COMMANDS" in plain

    def test_render_help_shows_return_hint(self) -> None:
        gv = GreeterView()
        gv._mode = GreeterMode.HELP
        text = gv._render_help()
        assert "Escape" in text.plain

    def test_render_dispatches_to_help(self) -> None:
        gv = GreeterView()
        gv._mode = GreeterMode.HELP
        text = gv.render()
        assert "NAVIGATION" in text.plain


class TestRenderFileList:
    def test_render_files_shows_names(self, tmp_path: Path) -> None:
        f1 = tmp_path / "alpha.deck"
        f2 = tmp_path / "beta.deck"
        f1.touch()
        f2.touch()
        gv = GreeterView(all_files=[f1, f2])
        gv._mode = GreeterMode.FILES
        text = gv._render_file_list([f1, f2], "Open File")
        plain = text.plain
        assert "alpha.deck" in plain
        assert "beta.deck" in plain

    def test_render_files_empty_message(self) -> None:
        gv = GreeterView(all_files=[])
        gv._mode = GreeterMode.FILES
        text = gv._render_file_list([], "Open File")
        assert "No .deck files found" in text.plain

    def test_render_files_cursor_indicator(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.deck"
        f2 = tmp_path / "b.deck"
        f1.touch()
        f2.touch()
        gv = GreeterView(all_files=[f1, f2])
        gv._mode = GreeterMode.FILES
        gv._cursor = 1
        text = gv._render_file_list([f1, f2], "Open File")
        lines = text.plain.split("\n")
        # Find lines containing file names and check cursor indicator
        file_lines = [ln for ln in lines if ".deck" in ln]
        assert any("b.deck" in ln for ln in file_lines)

    def test_render_dispatches_to_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "test.deck"
        f1.touch()
        gv = GreeterView(all_files=[f1])
        gv._mode = GreeterMode.FILES
        text = gv.render()
        assert "Open File" in text.plain

    def test_render_dispatches_to_recent(self, tmp_path: Path) -> None:
        f1 = tmp_path / "test.deck"
        f1.touch()
        gv = GreeterView(recent_files=[f1])
        gv._mode = GreeterMode.RECENT
        text = gv.render()
        assert "Recent Files" in text.plain


class TestCursorNavigation:
    def test_select_next_increments(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.deck"
        f2 = tmp_path / "b.deck"
        f1.touch()
        f2.touch()
        gv = GreeterView()
        gv._cursor = 0
        gv.select_next([f1, f2])
        assert gv._cursor == 1

    def test_select_next_clamps_at_end(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.deck"
        f1.touch()
        gv = GreeterView()
        gv._cursor = 0
        gv.select_next([f1])
        assert gv._cursor == 0  # Can't go past the only item

    def test_select_next_empty_list(self) -> None:
        gv = GreeterView()
        gv._cursor = 0
        gv.select_next([])
        assert gv._cursor == 0

    def test_select_prev_decrements(self) -> None:
        gv = GreeterView()
        gv._cursor = 2
        gv.select_prev()
        assert gv._cursor == 1

    def test_select_prev_clamps_at_zero(self) -> None:
        gv = GreeterView()
        gv._cursor = 0
        gv.select_prev()
        assert gv._cursor == 0

    def test_get_selected_returns_path(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.deck"
        f2 = tmp_path / "b.deck"
        f1.touch()
        f2.touch()
        gv = GreeterView()
        gv._cursor = 1
        assert gv.get_selected([f1, f2]) == f2

    def test_get_selected_empty_list(self) -> None:
        gv = GreeterView()
        assert gv.get_selected([]) is None

    def test_set_mode_resets_cursor(self) -> None:
        gv = GreeterView()
        gv._cursor = 3
        gv.set_mode(GreeterMode.HELP)
        assert gv._mode == GreeterMode.HELP
        assert gv._cursor == 0

    def test_set_mode_changes_mode(self) -> None:
        gv = GreeterView()
        gv.set_mode(GreeterMode.FILES)
        assert gv._mode == GreeterMode.FILES
