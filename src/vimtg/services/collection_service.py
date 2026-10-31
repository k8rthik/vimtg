"""Loading a collection CSV from disk, cached by path and mtime.

The editor loads the configured collection on every deck open and on
:collection; the cache makes that free while the file is unchanged and
picks up a re-export the next time either happens.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from vimtg.domain.collection import Collection, CollectionError, parse_collection_csv

# Resolved path -> (mtime_ns, size, Collection)
_CACHE: dict[Path, tuple[int, int, Collection]] = {}


def collection_path(setting: str) -> Path:
    """The file the `collection` setting names: ~ expanded, relative to the cwd."""
    path = Path(setting).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def load_collection(path: Path) -> Collection:
    """The collection in `path`, re-read only when the file changed.

    Raises :class:`CollectionError` for a missing or unreadable file and
    for a CSV with no recognisable columns.
    """
    try:
        resolved = path.resolve()
        stat = resolved.stat()
    except FileNotFoundError:
        raise CollectionError(f"collection file not found: {path}") from None
    except OSError as exc:
        raise CollectionError(f"cannot read {path}: {exc}") from exc
    if not resolved.is_file():
        raise CollectionError(f"{path} is not a file")
    cached = _CACHE.get(resolved)
    if cached is not None and cached[:2] == (stat.st_mtime_ns, stat.st_size):
        return cached[2]
    try:
        text = resolved.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise CollectionError(f"cannot read {path}: {exc}") from exc
    collection = parse_collection_csv(text, path, datetime.now())
    _CACHE[resolved] = (stat.st_mtime_ns, stat.st_size, collection)
    return collection
