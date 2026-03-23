"""Key remapping infrastructure for vimtg.

Supports user-defined key remappings loaded from config. Mappings are
per-mode: a key in NORMAL mode can map to something different than in
INSERT mode. Remappings are resolved before the KeyMap state machine
processes the key.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from vimtg.editor.modes import Mode


@dataclass(frozen=True)
class KeyMapping:
    from_key: str
    to_key: str
    mode: Mode


class KeyRemapper:
    """Resolves user key remappings before keys reach the KeyMap state machine."""

    def __init__(self) -> None:
        self._maps: dict[Mode, dict[str, str]] = {mode: {} for mode in Mode}

    def remap(self, from_key: str, to_key: str, mode: Mode | None = None) -> None:
        """Add a remapping. If mode is None, apply to all modes."""
        if mode is None:
            for m in Mode:
                self._maps[m][from_key] = to_key
        else:
            self._maps[mode][from_key] = to_key

    def unmap(self, from_key: str, mode: Mode | None = None) -> None:
        """Remove a remapping."""
        if mode is None:
            for m in Mode:
                self._maps[m].pop(from_key, None)
        else:
            self._maps[mode].pop(from_key, None)

    def resolve(self, key: str, mode: Mode) -> str:
        """Resolve a key through remappings. Returns the mapped key or original."""
        return self._maps[mode].get(key, key)

    def get_mappings(self, mode: Mode | None = None) -> list[KeyMapping]:
        """List all active mappings, optionally filtered by mode."""
        result = []
        modes = [mode] if mode else list(Mode)
        for m in modes:
            for from_key, to_key in self._maps[m].items():
                result.append(KeyMapping(from_key=from_key, to_key=to_key, mode=m))
        return result

    def load_from_config(self, config_path: Path) -> int:
        """Load remappings from a TOML config file. Returns count loaded.

        Config format:
        [keybindings]
        # Global (all modes)
        "ctrl_s" = ":w"

        [keybindings.normal]
        "s" = ":w"
        "Q" = ":q!"

        [keybindings.insert]
        "ctrl_j" = "escape"
        """
        if not config_path.exists():
            return 0

        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        bindings = data.get("keybindings", {})
        count = 0

        mode_map = {
            "normal": Mode.NORMAL,
            "insert": Mode.INSERT,
            "visual": Mode.VISUAL,
            "command": Mode.COMMAND,
        }

        # Top-level bindings apply to all modes
        for key, value in bindings.items():
            if isinstance(value, str):
                self.remap(key, value)
                count += 1

        # Mode-specific bindings
        for mode_name, mode_enum in mode_map.items():
            mode_bindings = bindings.get(mode_name, {})
            for key, value in mode_bindings.items():
                if isinstance(value, str):
                    self.remap(key, value, mode_enum)
                    count += 1

        return count


def load_remapper() -> KeyRemapper:
    """Create a KeyRemapper with user config loaded."""
    from vimtg.config.paths import config_dir

    remapper = KeyRemapper()
    config_path = config_dir() / "config.toml"
    remapper.load_from_config(config_path)
    return remapper
