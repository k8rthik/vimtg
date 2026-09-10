"""The shared key vocabulary: VimNav, display spelling, hint rendering."""

from __future__ import annotations

from vimtg.tui.keys import (
    CLOSE_KEYS,
    PENDING,
    VimNav,
    display_key,
    render_hints,
)


class TestVimNav:
    def test_gg_is_home_and_bare_g_pends(self) -> None:
        nav = VimNav()
        assert nav.feed("g", 20) == PENDING
        assert nav.pending_g is True
        assert nav.feed("g", 20) == "home"
        assert nav.pending_g is False

    def test_pending_g_then_other_key_parses_that_key(self) -> None:
        nav = VimNav()
        nav.feed("g", 20)
        assert nav.feed("j", 20) == 1
        assert nav.pending_g is False

    def test_pending_g_then_non_nav_key_returns_none(self) -> None:
        nav = VimNav()
        nav.feed("g", 20)
        assert nav.feed("q", 20) is None  # the caller closes on q
        assert nav.pending_g is False

    def test_shared_keys(self) -> None:
        nav = VimNav()
        assert nav.feed("j", 20) == 1 and nav.feed("down", 20) == 1
        assert nav.feed("k", 20) == -1 and nav.feed("up", 20) == -1
        assert nav.feed("ctrl_d", 20) == 10 and nav.feed("ctrl_u", 20) == -10
        assert nav.feed("G", 20) == "end" and nav.feed("end", 20) == "end"
        assert nav.feed("home", 20) == "home"
        assert nav.feed("x", 20) is None

    def test_reset_clears_pending(self) -> None:
        nav = VimNav()
        nav.feed("g", 20)
        nav.reset()
        assert nav.feed("g", 20) == PENDING


class TestDisplayKey:
    def test_named_keys(self) -> None:
        assert display_key("ctrl_d") == "Ctrl-D"
        assert display_key("escape") == "Esc"
        assert display_key("shift_tab") == "Shift-Tab"
        assert display_key("f1") == "F1"
        assert display_key(" ") == "Space"

    def test_plain_keys_pass_through(self) -> None:
        assert display_key("j") == "j"
        assert display_key("gg") == "gg"


class TestRenderHints:
    HINTS = (("q/Esc", "close"), ("j/k", "move"), ("?", "help"))

    def test_full_form(self) -> None:
        plain = render_hints(self.HINTS).plain
        assert plain == " q/Esc close  j/k move  ? help"

    def test_compact_when_narrow(self) -> None:
        plain = render_hints(self.HINTS, width=20).plain
        assert plain == " q/Esc  j/k  ?"
        assert len(plain) <= 20

    def test_close_keys(self) -> None:
        assert {"q", "escape"} == CLOSE_KEYS
