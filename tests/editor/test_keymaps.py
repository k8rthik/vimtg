"""Tests for key remapping infrastructure."""

from pathlib import Path

from vimtg.editor.keymaps import KeyRemapper
from vimtg.editor.modes import Mode


class TestKeyRemapper:
    def test_no_remap(self) -> None:
        r = KeyRemapper()
        assert r.resolve("j", Mode.NORMAL) == "j"

    def test_remap_all_modes(self) -> None:
        r = KeyRemapper()
        r.remap("s", ":w")
        assert r.resolve("s", Mode.NORMAL) == ":w"
        assert r.resolve("s", Mode.INSERT) == ":w"

    def test_remap_specific_mode(self) -> None:
        r = KeyRemapper()
        r.remap("s", ":w", Mode.NORMAL)
        assert r.resolve("s", Mode.NORMAL) == ":w"
        assert r.resolve("s", Mode.INSERT) == "s"

    def test_unmap(self) -> None:
        r = KeyRemapper()
        r.remap("s", ":w")
        r.unmap("s")
        assert r.resolve("s", Mode.NORMAL) == "s"

    def test_unmap_specific_mode(self) -> None:
        r = KeyRemapper()
        r.remap("s", ":w")
        r.unmap("s", Mode.NORMAL)
        assert r.resolve("s", Mode.NORMAL) == "s"
        assert r.resolve("s", Mode.INSERT) == ":w"

    def test_get_mappings(self) -> None:
        r = KeyRemapper()
        r.remap("s", ":w", Mode.NORMAL)
        r.remap("Q", ":q!", Mode.NORMAL)
        maps = r.get_mappings(Mode.NORMAL)
        assert len(maps) == 2

    def test_load_from_config(self, tmp_path: Path) -> None:
        config = tmp_path / "config.toml"
        config.write_text(
            '[keybindings]\n'
            '"ctrl_s" = ":w"\n'
            '\n'
            '[keybindings.normal]\n'
            '"Q" = ":q!"\n'
        )
        r = KeyRemapper()
        count = r.load_from_config(config)
        assert count == 2
        assert r.resolve("ctrl_s", Mode.NORMAL) == ":w"
        assert r.resolve("Q", Mode.NORMAL) == ":q!"
        assert r.resolve("Q", Mode.INSERT) == "Q"  # mode-specific

    def test_wrong_shape_mode_table_is_skipped(self, tmp_path: Path) -> None:
        """`normal = "x"` used to crash startup ('str' has no .items())."""
        config = tmp_path / "config.toml"
        config.write_text(
            '[keybindings]\nnormal = "x"\ninsert = ["a"]\nctrl_s = ":w"\n'
        )
        r = KeyRemapper()
        assert r.load_from_config(config) == 1
        assert r.resolve("ctrl_s", Mode.NORMAL) == ":w"
        assert r.resolve("normal", Mode.NORMAL) == "normal"

    def test_non_string_targets_are_skipped(self, tmp_path: Path) -> None:
        config = tmp_path / "config.toml"
        config.write_text('[keybindings.normal]\ns = 1\nQ = ":q!"\n')
        r = KeyRemapper()
        assert r.load_from_config(config) == 1
        assert r.resolve("s", Mode.NORMAL) == "s"

    def test_undecodable_config_is_ignored(self, tmp_path: Path) -> None:
        config = tmp_path / "config.toml"
        config.write_bytes(b"[keybindings]\ns = \"\xff\xfe\"\n")
        assert KeyRemapper().load_from_config(config) == 0

    def test_load_missing_config(self, tmp_path: Path) -> None:
        r = KeyRemapper()
        count = r.load_from_config(tmp_path / "nonexistent.toml")
        assert count == 0
