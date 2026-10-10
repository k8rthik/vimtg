"""TOML writer for Settings — persists to ~/.config/vimtg/config.toml.

tomllib is read-only, so this module carries a small serializer for
the value shapes a vimtg config holds (strings, numbers, booleans,
arrays and nested tables). Every document it produces is parsed back
with tomllib and compared before anything touches disk, so a value it
cannot represent raises instead of silently corrupting the file.
"""

from __future__ import annotations

import re
import shutil
import tomllib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from vimtg.config.paths import config_dir
from vimtg.config.settings import Settings
from vimtg.data.file_io import atomic_write_text

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")

_ESCAPES = {
    "\\": "\\\\", '"': '\\"', "\b": "\\b", "\t": "\\t",
    "\n": "\\n", "\f": "\\f", "\r": "\\r",
}


class SettingsWriteError(Exception):
    """config.toml could not be written without losing user data."""


def _format_string(value: str) -> str:
    out = []
    for ch in value:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _format_key(key: str) -> str:
    """A TOML key: bare when it can be, quoted otherwise ("ctrl+s")."""
    return key if _BARE_KEY.match(key) else _format_string(key)


def _format_value(value: object) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return _format_string(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_value(v) for v in value) + "]"
    if isinstance(value, dict):
        pairs = (f"{_format_key(k)} = {_format_value(v)}" for k, v in value.items())
        return "{" + ", ".join(pairs) + "}"
    raise TypeError(f"cannot write {type(value).__name__} to TOML")


def _dump_table(path: list[str], table: dict[str, Any], out: list[str]) -> None:
    """Append `table` (scalars first, then sub-tables) under its header."""
    scalars = {k: v for k, v in table.items() if not isinstance(v, dict)}
    subtables = {k: v for k, v in table.items() if isinstance(v, dict)}
    if path and (scalars or not subtables):
        if out:
            out.append("")
        out.append("[" + ".".join(_format_key(p) for p in path) + "]")
    for key, value in scalars.items():
        out.append(f"{_format_key(key)} = {_format_value(value)}")
    for key, value in subtables.items():
        _dump_table([*path, key], value, out)


def dumps_toml(data: dict[str, Any]) -> str:
    """Serialize `data` to TOML, verified by parsing it back."""
    out: list[str] = []
    try:
        _dump_table([], data, out)
    except TypeError as exc:
        raise SettingsWriteError(str(exc)) from exc
    text = "\n".join(out) + "\n"
    if tomllib.loads(text) != data:
        raise SettingsWriteError("settings did not survive a TOML round trip")
    return text


def settings_to_toml(settings: Settings) -> str:
    """Serialize Settings to a TOML [editor] section string."""
    return dumps_toml({"editor": asdict(settings)})


def _back_up(config_path: Path) -> Path:
    """Copy an unreadable config aside (reusing an identical backup)."""
    data = config_path.read_bytes()
    n = 0
    while True:
        backup = config_path.with_name(
            f"{config_path.name}.bak" + (f"{n}" if n else "")
        )
        if not backup.exists():
            shutil.copy2(config_path, backup)
            return backup
        if backup.read_bytes() == data:
            return backup
        n += 1


def save_settings(settings: Settings) -> Path:
    """Write settings to config.toml, preserving every other section.

    Raises SettingsWriteError (after backing the file up) when the
    existing config.toml cannot be parsed, and OSError when it cannot
    be written. The write itself is atomic (see data.file_io).
    """
    config_path = config_dir() / "config.toml"

    # Every other section (e.g. [keybindings]) is kept verbatim. A file
    # that does not parse is never overwritten: the user's mappings
    # would be lost for good. Back it up and make the user fix it.
    existing: dict[str, Any] = {}
    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                existing = tomllib.load(f)
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            backup = _back_up(config_path)
            raise SettingsWriteError(
                f"{config_path} is not valid TOML ({exc}); not overwriting it. "
                f"A copy is at {backup.name} — fix or remove the file, then save again."
            ) from exc

    data = dict(existing)
    editor = existing.get("editor")
    data["editor"] = {**(editor if isinstance(editor, dict) else {}), **asdict(settings)}
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    updated = update_editor_in_place(text, asdict(settings), data)
    atomic_write_text(config_path, updated if updated is not None else dumps_toml(data))
    return config_path


# ── In-place editing: keep the user's comments and layout ──────────

_HEADER = re.compile(r"^\s*\[\[?\s*([^\]]*?)\s*\]\]?\s*(#.*)?$")
_KEY_LINE = re.compile(r"^(\s*)(\"[^\"]*\"|'[^']*'|[A-Za-z0-9_-]+)(\s*=\s*)(.*)$")


def _value_end(rest: str) -> int:
    """Index just past the TOML scalar at the start of `rest` (before any
    trailing whitespace and comment)."""
    if rest.startswith('"'):
        i = 1
        while i < len(rest):
            if rest[i] == "\\":
                i += 2
                continue
            if rest[i] == '"':
                return i + 1
            i += 1
        return len(rest)
    if rest.startswith("'"):
        end = rest.find("'", 1)
        return len(rest) if end < 0 else end + 1
    hash_at = rest.find("#")
    return len(rest[: hash_at if hash_at >= 0 else len(rest)].rstrip())


def update_editor_in_place(
    text: str, values: dict[str, Any], expected: dict[str, Any],
) -> str | None:
    """`text` with the [editor] keys in `values` set, everything else —
    comments, blank lines, key order, other tables — untouched.

    Returns None when the file is laid out in a way this line editor
    does not handle (dotted keys, an inline table, multi-line values):
    the result must parse back to exactly `expected`, or it is not used.
    """
    lines = text.splitlines()
    start = end = None
    for i, line in enumerate(lines):
        m = _HEADER.match(line)
        if not m:
            continue
        if start is not None and end is None:
            end = i
        if m.group(1) == "editor" and not line.lstrip().startswith("[["):
            start, end = i, None
    if start is not None and end is None:
        end = len(lines)

    pending = dict(values)
    if start is not None and end is not None:
        last_key = start
        for i in range(start + 1, end):
            m = _KEY_LINE.match(lines[i])
            if not m:
                continue
            last_key = i
            key = m.group(2).strip("\"'")
            if key not in pending:
                continue
            rest = m.group(4)
            cut = _value_end(rest)
            lines[i] = (
                m.group(1) + m.group(2) + m.group(3)
                + _format_value(pending.pop(key)) + rest[cut:]
            )
        added = [f"{_format_key(k)} = {_format_value(v)}" for k, v in pending.items()]
        lines[last_key + 1:last_key + 1] = added
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("[editor]")
        lines.extend(f"{_format_key(k)} = {_format_value(v)}" for k, v in pending.items())

    result = "\n".join(lines) + "\n"
    try:
        if tomllib.loads(result) != expected:
            return None
    except tomllib.TOMLDecodeError:
        return None
    return result
