"""Crash recovery files — TUI-agnostic, zero Textual imports.

When the editor hits an unexpected error it writes the buffer to
$XDG_STATE_HOME/vimtg/recovery/<name>.deck (plus a traceback log next to
it). The next time that deck is opened the editor offers :recover.
"""

from __future__ import annotations

from pathlib import Path

from vimtg.config.paths import recovery_dir

UNNAMED = "unnamed"


def recovery_path(deck_path: Path | None) -> Path:
    """Where the recovery copy of `deck_path` lives (unnamed buffers share one)."""
    stem = deck_path.stem if deck_path is not None and deck_path.stem else UNNAMED
    return recovery_dir() / f"{stem}.deck"


def write_recovery(deck_path: Path | None, text: str, log: str = "") -> Path | None:
    """Save `text` as the recovery copy; returns its path, or None when the
    write itself fails — recovery must never raise from a crash handler."""
    try:
        path = recovery_path(deck_path)
        path.write_text(text, encoding="utf-8")
        if log:
            path.with_suffix(".log").write_text(log, encoding="utf-8")
    except OSError:
        return None
    return path


def read_recovery(deck_path: Path | None) -> str | None:
    """The recovery copy's text, or None when there is none (or it is unreadable)."""
    try:
        return recovery_path(deck_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def discard_recovery(deck_path: Path | None) -> None:
    """Delete the recovery copy and its log, if present."""
    try:
        path = recovery_path(deck_path)
        path.unlink(missing_ok=True)
        path.with_suffix(".log").unlink(missing_ok=True)
    except OSError:
        pass


def pending_recovery(deck_path: Path | None, current_text: str) -> bool:
    """True when a recovery copy exists and differs from `current_text`.

    An identical copy (the crash happened with nothing unsaved) is stale
    and is removed so it is never offered.
    """
    text = read_recovery(deck_path)
    if text is None:
        return False
    if text == current_text:
        discard_recovery(deck_path)
        return False
    return True
