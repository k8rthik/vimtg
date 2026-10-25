"""Card search helpers for / ? n N — TUI-agnostic, zero Textual imports.

Jump to the next card line matching a regex pattern in the buffer.
`n` / `N` repeat the last pattern through find_card_row.
"""

from __future__ import annotations

import re

from vimtg.editor.buffer import Buffer

_WRAP_NOTICE = {
    False: "search hit BOTTOM, continuing at TOP",
    True: "search hit TOP, continuing at BOTTOM",
}


def find_card_row(
    buffer: Buffer, row: int, pattern: str, *, backward: bool = False,
) -> int | None:
    """The next card line after `row` (before it when `backward`) whose
    text matches `pattern`, wrapping around the buffer and, as in vim,
    back to `row` itself; None when no card line matches. Raises
    re.error on an invalid pattern."""
    regex = re.compile(pattern, re.IGNORECASE)
    total = buffer.line_count()
    step = -1 if backward else 1
    for offset in range(1, total + 1):
        idx = (row + step * offset) % total
        if buffer.is_card_line(idx) and regex.search(buffer.get_line(idx).text):
            return idx
    return None


def wrapped(row: int, found: int, *, backward: bool) -> bool:
    """Whether a search from `row` went past the end of the buffer to
    reach `found`."""
    return found >= row if backward else found <= row


def search_message(echo: str, *, wrap: bool, backward: bool) -> str:
    """What the command line shows after a successful search: the
    search itself, or vim's notice that it wrapped around."""
    return _WRAP_NOTICE[backward] if wrap else echo
