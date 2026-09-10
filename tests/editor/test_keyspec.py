"""Drift tests: the key spec, the keymap, which-key, and the docs agree.

A key cannot be handled without being documented, or documented without
being handled.
"""

from __future__ import annotations

from pathlib import Path

from vimtg.editor.help_text import HELP_OVERVIEW
from vimtg.editor.keymap import (
    _G_SUB_KEYS,
    _SPLIT_SUB_KEYS,
    _TAG_SUB_KEYS,
    _ZONE_SUB_KEYS,
    MODE_SWITCHES,
    MOTIONS,
    MULTI_KEY_STARTERS,
    OPERATORS,
    SPECIAL_KEYS,
    KeyMap,
    KeyResult,
)
from vimtg.editor.keyspec import (
    EDITOR_BINDINGS,
    MARK,
    PREFIX_TITLES,
    KeyBinding,
    bindings,
    quick_hints,
    which_key_menus,
)
from vimtg.editor.modes import Mode
from vimtg.tui.keys import display_key
from vimtg.tui.widgets.which_key import NORMAL_HINTS, PENDING_HINTS

DOCS = Path(__file__).parent.parent.parent / "docs" / "keybindings.md"
README = Path(__file__).parent.parent.parent / "README.md"


def _atoms(mode: str = "normal") -> list[tuple[KeyBinding, str]]:
    return [(b, key) for b in bindings(mode) for key in b.keys]


def _sample(key: str) -> list[str]:
    """Keystrokes that exercise a spec key; patterns use `a`."""
    key = key.replace(MARK, "a")
    if key in ("ctrl_d", "ctrl_u", "ctrl_r", "escape", "f1"):
        return [key]
    return list(key)


class TestSpecMatchesKeymap:
    def test_every_normal_key_completes_or_pends_as_declared(self) -> None:
        for b, key in _atoms("normal"):
            if key in ("f1", "?", "escape"):
                continue  # F1 is handled by the screen; ? and Esc are specials tested below
            km = KeyMap(mode=Mode.NORMAL)
            if key == "q":
                km.set_macro_recording(True)  # bare q stops a recording
            result = None
            for stroke in _sample(key):
                result, _ = km.feed(stroke)
            expected = KeyResult.COMPLETE if b.completes else KeyResult.PENDING
            assert result == expected, f"{key!r} -> {result}"

    def test_escape_and_help_are_specials(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        assert km.feed("escape")[0] == KeyResult.COMPLETE
        assert km.feed("?")[0] == KeyResult.COMPLETE

    def test_every_keymap_single_key_is_in_the_spec(self) -> None:
        declared = {key for _, key in _atoms("normal")}
        for key in MOTIONS | OPERATORS | set(MODE_SWITCHES) | SPECIAL_KEYS | {"G"}:
            assert key in declared, key

    def test_every_prefix_and_sub_key_is_in_the_spec(self) -> None:
        declared = {key for _, key in _atoms("normal")}
        for prefix in MULTI_KEY_STARTERS:
            assert prefix in PREFIX_TITLES, prefix
        for sub in _G_SUB_KEYS:
            assert f"g{sub}" in declared
        for sub in _TAG_SUB_KEYS:
            assert f"t{sub}" in declared
        for sub in _SPLIT_SUB_KEYS:
            assert f"S{sub}" in declared
        for sub in _ZONE_SUB_KEYS:
            assert f"z{sub}" in declared
        sequences = (
            "gg", "[[", "]]", "[v", "]v",
            f"m{MARK}", f"'{MARK}", f"q{MARK}", f"@{MARK}", "@@",
        )
        for key in sequences:
            assert key in declared, key

    def test_m_prefix_is_marks_only(self) -> None:
        for letter in "smdcpio":
            km = KeyMap(mode=Mode.NORMAL)
            km.feed("m")
            result, action = km.feed(letter)
            assert result == KeyResult.COMPLETE and action is not None
            assert action.action == f"m{letter}"

    def test_visual_keys_are_declared(self) -> None:
        declared = {key for _, key in _atoms("visual")}
        assert {"d", "y", "c", "o", "escape"} <= declared


class TestSpecFeedsTheSurfaces:
    def test_which_key_tables_come_from_the_spec(self) -> None:
        assert which_key_menus() == PENDING_HINTS
        assert quick_hints() == NORMAL_HINTS

    def test_every_prefix_has_a_menu(self) -> None:
        for prefix in MULTI_KEY_STARTERS | {"d", "y", "c", '"'}:
            assert PENDING_HINTS.get(prefix), prefix

    def test_help_overview_lists_every_key(self) -> None:
        for b in EDITOR_BINDINGS:
            assert b.display in HELP_OVERVIEW, b.display

    def test_help_overview_has_no_stale_zone_keys(self) -> None:
        for old in ("ms/mm/md", "mo / mi", "mc/mp"):
            assert old not in HELP_OVERVIEW


class TestDocsMatchTheSpec:
    def test_keybindings_doc_names_every_key(self) -> None:
        doc = DOCS.read_text()
        for _, key in _atoms("normal") + _atoms("visual"):
            spelled = display_key(key)
            assert f"`{spelled}`" in doc, spelled

    def test_readme_tables_use_the_z_prefix(self) -> None:
        readme = README.read_text()
        assert "`zs`" in readme and "`zo`" in readme
        for old in ("`ms`", "`mo`", "`mi`"):
            assert old not in readme, old
