"""Cross-deck category name history for completion.

A plain newline-separated file under the config dir, most recent
first, capped. Read/write failures degrade silently — completion is a
convenience, never a reason to interrupt editing.
"""

from __future__ import annotations

import contextlib

from vimtg.config.paths import config_dir

_HISTORY_FILE = "categories"
_MAX_ENTRIES = 200


def load_category_history() -> tuple[str, ...]:
    """Load previously used category names, most recent first."""
    path = config_dir() / _HISTORY_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    seen: set[str] = set()
    names: list[str] = []
    for line in text.splitlines():
        name = line.strip().lower()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return tuple(names[:_MAX_ENTRIES])


def record_category(name: str) -> None:
    """Move `name` to the front of the history file (best-effort)."""
    name = name.strip().lower()
    if not name:
        return
    existing = [n for n in load_category_history() if n != name]
    updated = [name, *existing][:_MAX_ENTRIES]
    path = config_dir() / _HISTORY_FILE
    with contextlib.suppress(OSError):
        path.write_text("\n".join(updated) + "\n", encoding="utf-8")
