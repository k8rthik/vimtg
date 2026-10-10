"""Safe file writes and on-disk change detection.

`atomic_write_text` is the one place vimtg replaces a user file. It
stages the new contents next to the real target and renames over it,
so a crash leaves either the old or the new file, never half of one —
while keeping the things a plain rename would lose: symlinks stay
symlinks (the link target is replaced), the original permission bits
survive, and both the file and its directory are fsynced.

`FileStamp` records what a file looked like when it was read, so a
later save can tell that something else changed it in the meantime.
"""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Mode a brand-new file gets before the umask is applied (as open(2) does)
_NEW_FILE_MODE = 0o666


@dataclass(frozen=True)
class FileStamp:
    """Modification time and size of a file at one point in time.

    `ABSENT` stands for "the file did not exist" — comparing it against
    a later stamp catches a file that appeared in the meantime.
    """

    mtime_ns: int
    size: int


ABSENT = FileStamp(mtime_ns=-1, size=-1)


def file_stamp(path: Path) -> FileStamp:
    """The current stamp of `path` (following symlinks), or ABSENT."""
    try:
        st = path.stat()
    except FileNotFoundError:
        return ABSENT
    return FileStamp(mtime_ns=st.st_mtime_ns, size=st.st_size)


def _current_umask() -> int:
    """The process umask, read without changing it where possible.

    os.umask() can only be queried by setting it, which races with
    other threads creating files; Linux exposes it read-only in /proc.
    """
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("Umask:"):
                    return int(line.split()[1], 8)
    except (OSError, ValueError, IndexError):
        pass
    return 0o022


def _fsync_dir(directory: Path) -> None:
    """Flush a directory entry change (the rename) to disk. POSIX only."""
    if os.name != "posix":
        return
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass  # some filesystems refuse fsync on directories
    finally:
        os.close(fd)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> Path:
    """Atomically replace `path` with `text`; return the file written.

    A symlink is resolved first, so the link's target is rewritten and
    the link itself survives. An existing file keeps its permission
    bits; a new one gets the default 0666 & ~umask like any other
    newly created file. The temp file is unique (mkstemp), so two
    writers never collide on a predictable name.
    """
    target = Path(os.path.realpath(path))
    try:
        mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        mode = _NEW_FILE_MODE & ~_current_umask()

    fd, tmp_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, target)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    _fsync_dir(target.parent)
    return target
