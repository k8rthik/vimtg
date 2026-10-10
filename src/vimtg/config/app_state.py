"""Small persistent UI state kept in the XDG state dir (not config).

Holds things the app remembers on the user's behalf rather than things
the user configures: decks opened recently (from any directory) and
whether the first-run tips panel was dismissed. Stored as one JSON file;
a missing, unreadable or malformed file simply means "no state yet" —
remembering is best-effort and must never stop the editor.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from vimtg.config.paths import state_dir

STATE_FILE = "state.json"
MAX_RECENT = 20


def _state_path() -> Path:
    return state_dir() / STATE_FILE


def _load() -> dict[str, Any]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _store(data: dict[str, Any]) -> None:
    # Best-effort: a read-only or full state dir costs a memory, not a crash
    with contextlib.suppress(OSError):
        path = _state_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)


def recent_decks() -> list[Path]:
    """Recently opened or saved decks, newest first, that still exist."""
    raw = _load().get("recent_decks", [])
    if not isinstance(raw, list):
        return []
    paths = [Path(p) for p in raw if isinstance(p, str) and p]
    return [p for p in paths if p.is_file()]


def remember_deck(path: Path) -> None:
    """Move `path` to the front of the recent-decks list."""
    entry = str(path.expanduser().resolve())
    data = _load()
    raw = data.get("recent_decks", [])
    previous = [p for p in raw if isinstance(p, str)] if isinstance(raw, list) else []
    data["recent_decks"] = [entry, *(p for p in previous if p != entry)][:MAX_RECENT]
    _store(data)


def tips_dismissed() -> bool:
    """True once the user turned the first-run tips panel off."""
    return _load().get("tips_dismissed") is True


def set_tips_dismissed(dismissed: bool) -> None:
    data = _load()
    data["tips_dismissed"] = dismissed
    _store(data)
