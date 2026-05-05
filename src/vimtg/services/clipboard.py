"""OSC52 system-clipboard helper.

The OSC52 escape sequence asks the terminal emulator to put text on the
system clipboard. It works in iTerm2, kitty, Alacritty, Wezterm, and
Windows Terminal. Best-effort: the emulator may have OSC52 disabled,
in which case the bytes are silently dropped.
"""

from __future__ import annotations

import base64
import sys
from typing import IO

_OSC52_PREFIX = "\033]52;c;"
_OSC52_TERMINATOR = "\007"


def copy_to_clipboard(text: str, *, stream: IO[str] | None = None) -> bool:
    """Copy ``text`` to the system clipboard via OSC52.

    Returns True if the escape sequence was written and flushed; this does
    not guarantee the terminal honored it. Pass ``stream`` for testing.
    """
    out = stream if stream is not None else sys.stdout
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    try:
        out.write(f"{_OSC52_PREFIX}{encoded}{_OSC52_TERMINATOR}")
        out.flush()
    except (OSError, ValueError):
        return False
    return True
