"""Crash recovery files — TUI-agnostic, zero Textual imports.

When the editor hits an unexpected error, or the session ends with
unsaved changes (terminal closed, SIGHUP/SIGTERM, Ctrl-C/Ctrl-Q), it
writes the buffer to $XDG_STATE_HOME/vimtg/recovery/ (plus a traceback
log next to it for a crash). The next time that deck is opened the
editor offers :recover.

A copy belongs to exactly one deck: its file name carries a hash of the
deck's resolved absolute path (so one/burn.deck and two/burn.deck, or
a.deck and a.txt, never share a copy), and its first line records that
path so a copy whose deck is gone can still say what it was. A buffer
with no file gets its own id, so two unnamed buffers never share one.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from vimtg.config.paths import recovery_dir

UNNAMED = "unnamed"
SUFFIX = ".deck"
# First line of every copy: this marker, then JSON {"path": str | null}
HEADER = "// vimtg-recovery: "

_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")


def new_buffer_id() -> str:
    """A fresh id for an unnamed buffer's recovery copy."""
    return uuid.uuid4().hex[:12]


def _resolved(deck_path: Path) -> str:
    """The absolute, symlink-resolved path that identifies a deck."""
    return os.path.realpath(deck_path.expanduser())


def _readable_stem(stem: str) -> str:
    return _UNSAFE.sub("-", stem).strip("-")[:40] or UNNAMED


def recovery_path(deck_path: Path | None, buffer_id: str | None = None) -> Path:
    """Where the recovery copy of `deck_path` lives.

    Named decks are keyed on a hash of the resolved absolute path (the
    stem is kept in front only so a person browsing the directory can
    tell copies apart). An unnamed buffer is keyed on `buffer_id`.
    """
    if deck_path is not None:
        resolved = _resolved(deck_path)
        # A path with undecodable bytes (surrogates) still gets a key
        digest = hashlib.sha256(resolved.encode("utf-8", "surrogateescape")).hexdigest()[:16]
        name = f"{_readable_stem(Path(resolved).stem)}.{digest}"
    else:
        name = f"{UNNAMED}.{_readable_stem(buffer_id or '')}" if buffer_id else UNNAMED
    return recovery_dir() / f"{name}{SUFFIX}"


def _log_path(copy: Path) -> Path:
    return copy.with_suffix(".log")


def _encode(deck_path: Path | None, text: str) -> str:
    original = _resolved(deck_path) if deck_path is not None else None
    return HEADER + json.dumps({"path": original}) + "\n" + text


def _decode(raw: str) -> tuple[str | None, bool, str]:
    """(original path, has header, deck text) of a copy's contents."""
    if not raw.startswith(HEADER):
        return None, False, raw  # a copy from before the header existed
    first, _, rest = raw.partition("\n")
    try:
        meta = json.loads(first[len(HEADER):])
    except ValueError:
        return None, True, rest
    path = meta.get("path") if isinstance(meta, dict) else None
    return (path if isinstance(path, str) else None), True, rest


def write_recovery(
    deck_path: Path | None, text: str, log: str = "", buffer_id: str | None = None
) -> Path | None:
    """Save `text` as the recovery copy; returns its path, or None when the
    write itself fails — recovery must never raise from a crash handler."""
    try:
        path = recovery_path(deck_path, buffer_id)
        path.write_text(_encode(deck_path, text), encoding="utf-8")
        if log:
            _log_path(path).write_text(log, encoding="utf-8")
    except OSError:
        return None
    return path


def read_copy(copy: Path) -> str | None:
    """The deck text a recovery copy holds (header removed), or None."""
    try:
        raw = copy.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return _decode(raw)[2]


def read_recovery(deck_path: Path | None, buffer_id: str | None = None) -> str | None:
    """The recovery copy's text, or None when there is none (or it is
    unreadable, or it records a different deck)."""
    try:
        raw = recovery_path(deck_path, buffer_id).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    original, has_header, text = _decode(raw)
    if has_header and deck_path is not None and original != _resolved(deck_path):
        return None  # never hand one deck's copy to another
    return text


def discard_copy(copy: Path) -> None:
    """Delete one recovery copy and its log, if present."""
    try:
        copy.unlink(missing_ok=True)
        _log_path(copy).unlink(missing_ok=True)
    except OSError:
        pass


def discard_recovery(deck_path: Path | None, buffer_id: str | None = None) -> None:
    """Delete the recovery copy (and its log) of exactly this deck."""
    try:
        copy = recovery_path(deck_path, buffer_id)
    except OSError:  # the recovery directory cannot be created
        return
    discard_copy(copy)


def pending_recovery(
    deck_path: Path | None, current_text: str, buffer_id: str | None = None
) -> bool:
    """True when a recovery copy exists and differs from `current_text`.

    An identical copy (the crash happened with nothing unsaved) is stale
    and is removed so it is never offered.
    """
    text = read_recovery(deck_path, buffer_id)
    if text is None:
        return False
    if text == current_text:
        discard_recovery(deck_path, buffer_id)
        return False
    return True


@dataclass(frozen=True)
class RecoveryCopy:
    """One copy in the recovery directory, as the greeter lists it."""

    copy: Path
    original: Path | None  # the deck it was saved from; None = unnamed
    mtime: float

    @property
    def orphaned(self) -> bool:
        """True when nothing will offer this copy on open: the buffer had
        no file, or its file no longer exists."""
        return self.original is None or not self.original.exists()

    @property
    def buffer_id(self) -> str | None:
        """The unnamed-buffer id the copy is keyed on (None when named)."""
        if self.original is not None:
            return None
        _, _, rest = self.copy.stem.partition(".")
        return rest or None

    @property
    def label(self) -> str:
        return self.original.name if self.original is not None else "(unnamed buffer)"


def list_recoveries() -> list[RecoveryCopy]:
    """Every recovery copy, newest first."""
    try:
        copies = list(recovery_dir().glob(f"*{SUFFIX}"))
    except OSError:
        return []
    found: list[RecoveryCopy] = []
    for copy in copies:
        try:
            with copy.open(encoding="utf-8") as f:
                first = f.readline()
            mtime = copy.stat().st_mtime
        except (OSError, UnicodeDecodeError):
            continue
        original, _, _ = _decode(first)
        found.append(RecoveryCopy(
            copy=copy, original=Path(original) if original else None, mtime=mtime,
        ))
    found.sort(key=lambda c: c.mtime, reverse=True)
    return found


def orphaned_recoveries() -> list[RecoveryCopy]:
    """Copies no deck open will offer: unnamed buffers and copies whose
    deck file is gone. The greeter lists these to open or discard."""
    return [c for c in list_recoveries() if c.orphaned]
