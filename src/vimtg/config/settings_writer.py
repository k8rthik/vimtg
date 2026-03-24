"""TOML writer for Settings — persists to ~/.config/vimtg/config.toml.

Uses a simple hand-rolled serializer since tomllib is read-only and
our settings are flat primitives (str, int, bool) under [editor].
"""

from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import asdict
from pathlib import Path

from vimtg.config.paths import config_dir
from vimtg.config.settings import Settings


def _format_value(value: object) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return str(value)


def settings_to_toml(settings: Settings) -> str:
    """Serialize Settings to a TOML [editor] section string."""
    lines = ["[editor]"]
    for key, value in asdict(settings).items():
        lines.append(f"{key} = {_format_value(value)}")
    return "\n".join(lines) + "\n"


def save_settings(settings: Settings) -> Path:
    """Write settings to config.toml, preserving non-[editor] sections.

    Uses atomic write (temp file + rename) to prevent corruption.
    """
    config_path = config_dir() / "config.toml"

    # Preserve existing non-editor sections (e.g. [keybindings])
    other_sections: dict[str, dict] = {}
    if config_path.exists():
        with open(config_path, "rb") as f:
            existing = tomllib.load(f)
        for section, data in existing.items():
            if section != "editor":
                other_sections[section] = data

    # Build full TOML content
    parts = [settings_to_toml(settings)]
    for section, data in other_sections.items():
        parts.append(f"\n[{section}]")
        for key, value in data.items():
            if isinstance(value, dict):
                # Nested table like [keybindings.normal]
                parts.append(f"\n[{section}.{key}]")
                for k, v in value.items():
                    parts.append(f"{k} = {_format_value(v)}")
            else:
                parts.append(f"{key} = {_format_value(value)}")
        parts.append("")

    content = "\n".join(parts)

    # Atomic write
    fd, tmp_path = tempfile.mkstemp(
        dir=config_path.parent, suffix=".tmp", prefix="config_",
    )
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.replace(tmp_path, config_path)
    except Exception:
        os.close(fd) if not os.get_inheritable(fd) else None
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return config_path
