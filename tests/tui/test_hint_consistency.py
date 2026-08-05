"""Keybinding hints must agree with the actual keymap.

These are drift tests: which-key and help once documented keys that did
not exist (or documented them backwards).
"""

from __future__ import annotations

from vimtg.editor.help_text import HELP_OVERVIEW
from vimtg.editor.keymap import (
    _TAG_SUB_KEYS,
    MULTI_KEY_STARTERS,
    KeyMap,
    KeyResult,
)
from vimtg.editor.motions import MOTION_REGISTRY, motion_next_section
from vimtg.tui.widgets.which_key import PENDING_HINTS


class TestWhichKeyMatchesKeymap:
    def test_every_pending_hint_key_is_reachable(self) -> None:
        """A PENDING_HINTS entry must correspond to a real pending state."""
        km = KeyMap()
        for prefix in PENDING_HINTS:
            km.reset()
            if prefix == '"':
                result, _ = km.feed('"')
            elif prefix in ("d", "y", "c"):
                result, _ = km.feed(prefix)
            else:
                result, _ = km.feed(prefix)
            assert result == KeyResult.PENDING, f"{prefix!r} never pends"

    def test_multi_key_starters_have_hints(self) -> None:
        missing = [k for k in MULTI_KEY_STARTERS if k not in PENDING_HINTS]
        assert missing == []

    def test_tag_subkeys_all_hinted(self) -> None:
        hinted = {key[1] for key, _ in PENDING_HINTS["t"]}
        assert hinted == set(_TAG_SUB_KEYS)


class TestHelpMatchesMotions:
    def test_brace_direction_documented_correctly(self) -> None:
        """'{' is PREV section, '}' is NEXT — help once said the reverse."""
        assert MOTION_REGISTRY["}"] is motion_next_section
        assert "{/}           Prev/next section" in HELP_OVERVIEW

    def test_all_registered_motions_appear_in_help(self) -> None:
        symbolic = {"j", "k", "w", "b", "{", "}", "gg", "G", "[[", "]]"}
        for key in symbolic:
            assert key in MOTION_REGISTRY
            assert key in HELP_OVERVIEW
