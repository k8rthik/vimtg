"""Tests for WhichKey — pending-key hints with a normal-mode fallback.

The widget only ever displays while a key sequence is pending (that is
the only state where MainScreen sets display=True), so there are no
per-mode hint sets — those were unreachable UI and have been removed.
"""

from __future__ import annotations

from vimtg.tui.widgets.which_key import PENDING_HINTS, WhichKey


class TestFallbackHints:
    def test_fallback_shows_navigation(self) -> None:
        w = WhichKey()
        plain = w.render().plain
        assert "Navigation:" in plain
        assert "j/k" in plain

    def test_fallback_shows_editing(self) -> None:
        w = WhichKey()
        plain = w.render().plain
        assert "Editing:" in plain
        assert "dd" in plain

    def test_fallback_shows_commands_overview(self) -> None:
        w = WhichKey()
        plain = w.render().plain
        assert "Commands:" in plain
        assert "u" in plain  # undo

    def test_section_direction_is_prev_next(self) -> None:
        """'{' is prev, '}' is next — the hint once said the reverse."""
        w = WhichKey()
        assert "prev/next section" in w.render().plain


class TestPendingKeyOverride:
    def test_pending_d_shows_only_d_motions(self) -> None:
        w = WhichKey()
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

    def test_pending_mark_keys_show_mark_hints(self) -> None:
        w = WhichKey()
        w.pending_key = "m"
        assert "set mark" in w.render().plain
        w.pending_key = "'"
        assert "jump to mark" in w.render().plain

    def test_unknown_pending_key_falls_back(self) -> None:
        w = WhichKey()
        w.pending_key = "Z"  # not in PENDING_HINTS
        assert "Navigation:" in w.render().plain

    def test_all_documented_pending_keys_render(self) -> None:
        """Every key in PENDING_HINTS produces a non-empty hint render."""
        for key in PENDING_HINTS:
            w = WhichKey()
            w.pending_key = key
            plain = w.render().plain
            assert "Next:" in plain
            assert len(plain.strip()) > 5
