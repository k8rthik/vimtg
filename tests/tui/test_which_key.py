"""Tests for WhichKey — context-sensitive keybinding hints by mode and pending key."""

from __future__ import annotations

from vimtg.editor.modes import Mode
from vimtg.tui.widgets.which_key import PENDING_HINTS, WhichKey


class TestNormalModeHints:
    def test_normal_mode_shows_navigation(self) -> None:
        w = WhichKey()
        w.mode = Mode.NORMAL
        plain = w.render().plain
        assert "Navigation:" in plain
        assert "j/k" in plain

    def test_normal_mode_shows_editing(self) -> None:
        w = WhichKey()
        w.mode = Mode.NORMAL
        plain = w.render().plain
        assert "Editing:" in plain
        assert "dd" in plain

    def test_normal_mode_shows_commands_overview(self) -> None:
        w = WhichKey()
        w.mode = Mode.NORMAL
        plain = w.render().plain
        assert "Commands:" in plain
        assert "u" in plain  # undo


class TestInsertModeHints:
    def test_insert_mode_shows_insert_hints(self) -> None:
        w = WhichKey()
        w.mode = Mode.INSERT
        plain = w.render().plain
        assert "Insert Mode:" in plain
        assert "Tab" in plain
        assert "Esc" in plain

    def test_insert_with_line_edit_shows_line_edit_hints(self) -> None:
        w = WhichKey()
        w.mode = Mode.INSERT
        w.line_edit = True
        plain = w.render().plain
        assert "Line Edit:" in plain
        # Line edit hints, not search-result hints
        assert "Ctrl-J" not in plain


class TestCommandModeHints:
    def test_command_mode_shows_ex_commands(self) -> None:
        w = WhichKey()
        w.mode = Mode.COMMAND
        plain = w.render().plain
        assert "Commands:" in plain
        assert ":w" in plain
        assert ":sort" in plain

    def test_command_mode_shows_tag_commands(self) -> None:
        w = WhichKey()
        w.mode = Mode.COMMAND
        plain = w.render().plain
        assert "Tags:" in plain
        assert ":tag" in plain

    def test_search_mode_uses_command_hints(self) -> None:
        w = WhichKey()
        w.mode = Mode.SEARCH
        plain = w.render().plain
        assert ":w" in plain


class TestPendingKeyOverride:
    def test_pending_d_shows_only_d_motions(self) -> None:
        w = WhichKey()
        w.mode = Mode.NORMAL
        w.pending_key = "d"
        plain = w.render().plain
        assert "Next:" in plain
        assert "dd" in plain
        assert "dw" in plain
        # Should not show full normal-mode hints when pending
        assert "Navigation:" not in plain
        assert "Editing:" not in plain

    def test_pending_y_shows_only_y_motions(self) -> None:
        w = WhichKey()
        w.pending_key = "y"
        plain = w.render().plain
        assert "yy" in plain
        assert "y}" in plain

    def test_pending_g_shows_g_motions(self) -> None:
        w = WhichKey()
        w.pending_key = "g"
        plain = w.render().plain
        assert "gg" in plain

    def test_unknown_pending_key_falls_back_to_mode_hints(self) -> None:
        w = WhichKey()
        w.mode = Mode.NORMAL
        w.pending_key = "Z"  # not in PENDING_HINTS
        plain = w.render().plain
        assert "Navigation:" in plain

    def test_all_documented_pending_keys_render(self) -> None:
        """Every key in PENDING_HINTS produces a non-empty hint render."""
        for key in PENDING_HINTS:
            w = WhichKey()
            w.pending_key = key
            plain = w.render().plain
            assert "Next:" in plain
            assert len(plain.strip()) > 5
