"""Viewport scrolling math shared by list-style widgets.

Pure functions — no Textual imports, no mutation.
"""

from __future__ import annotations


def compute_scroll_offset(
    selected: int,
    current_offset: int,
    total: int,
    viewport: int,
    scrolloff: int = 2,
) -> int:
    """Compute the scroll offset keeping `selected` visible with scrolloff.

    Returns a new offset value; the current offset is preserved when the
    selection is already comfortably inside the viewport.
    """
    if total <= viewport:
        return 0

    # A scrolloff at or above half the viewport makes the two
    # adjustments fight and can push the selection out of the window
    # entirely (a 3-row pane with scrolloff 3 hides the cursor).
    scrolloff = min(scrolloff, max(0, (viewport - 1) // 2))

    max_offset = total - viewport
    offset = current_offset

    # Scrolling down: selection too close to bottom of viewport
    if selected > offset + viewport - 1 - scrolloff:
        offset = selected - viewport + 1 + scrolloff

    # Scrolling up: selection too close to top of viewport
    if selected < offset + scrolloff:
        offset = selected - scrolloff

    return max(0, min(offset, max_offset))


def compute_block_scroll_offset(
    selected: int,
    block_height: int,
    current_offset: int,
    total: int,
    viewport: int,
    scrolloff: int = 2,
    bottom_pad: int = 0,
) -> int:
    """Scroll offset keeping a multi-row selection block visible.

    The selected line renders `block_height` rows (its own row plus any
    expansion beneath it); every other line renders one row. The whole
    block is kept on screen with `scrolloff` rows of context above and
    below it. When the block is taller than that allows, the selected
    row and its top context win and the expansion clips at the bottom.

    The view may scroll up to `bottom_pad` rows past the last line so a
    block at the end of the buffer still gets its context; the pad never
    forces a scroll when the content already fits the viewport.

    Offsets are buffer-line indices: rows above the selection map 1:1
    to buffer lines, and the offset never passes the selected line.
    """
    extra = max(0, block_height - 1)
    if viewport <= 0 or total + extra <= viewport:
        return 0

    scrolloff = min(scrolloff, max(0, (viewport - 1) // 2))
    max_offset = total + extra + bottom_pad - viewport
    offset = current_offset

    # Scrolling down: block bottom (plus context) below the viewport
    if selected + extra > offset + viewport - 1 - scrolloff:
        offset = selected + extra - viewport + 1 + scrolloff

    # Scrolling up: selected row (plus context) above the viewport.
    # Applied last so the cursor row always wins over the expansion.
    if selected < offset + scrolloff:
        offset = selected - scrolloff

    return max(0, min(offset, max_offset))


def scroll_step_for_key(key: str, viewport: int) -> int | str | None:
    """Vim-style scroll command for a translated key.

    Returns a signed line delta (j/k/arrows one line, Ctrl-D/U half a
    viewport, never less than one line), "home" for Home, "end" for G or
    End, or None when the key is not a scroll key. `gg` is handled by
    tui.keys.VimNav, which owns the pending `g`; a bare `g` is never a
    scroll key. Shared by every read-only scrolling view so they cannot
    drift apart.
    """
    half = max(1, viewport // 2)
    if key in ("j", "down"):
        return 1
    if key in ("k", "up"):
        return -1
    if key == "ctrl_d":
        return half
    if key == "ctrl_u":
        return -half
    if key == "home":
        return "home"
    if key in ("G", "end"):
        return "end"
    return None


# Buffer rows one wheel notch moves (vim's default for the mouse wheel)
WHEEL_LINES = 3


def wheel_scroll(
    offset: int,
    cursor: int,
    delta: int,
    total: int,
    viewport: int,
    scrolloff: int = 2,
) -> tuple[int, int]:
    """Vim-style wheel scroll: move the window by `delta` rows and return
    (new_offset, new_cursor).

    The window moves freely within the content; the cursor stays put
    unless it would leave the scrolloff band, in which case it is
    dragged to the band's edge — so the view never scrolls the cursor
    off screen, and never yanks it around when it is comfortably inside.
    """
    if viewport <= 0 or total <= viewport:
        return 0, cursor
    scrolloff = min(scrolloff, max(0, (viewport - 1) // 2))
    max_offset = total - viewport
    new_offset = max(0, min(offset + delta, max_offset))
    # At the very top/bottom of the content the band opens up: the
    # cursor may sit on the first or last line, as in vim
    low = new_offset + scrolloff if new_offset > 0 else 0
    high = (
        new_offset + viewport - 1 - scrolloff
        if new_offset < max_offset
        else total - 1
    )
    new_cursor = max(low, min(cursor, high))
    return new_offset, new_cursor


def resolved_viewport(height: int, default: int, reserved: int = 0) -> int:
    """Rows available for content.

    Uses the widget's real height once it is laid out, else `default`
    (headless tests, or before the first layout); `reserved` rows (a
    header, a hint line) are subtracted. Never below one row.
    """
    base = height if height > 0 else default
    return max(1, base - reserved)


def max_window_offset(total: int, rows: int) -> int:
    """Largest offset for window_lines: every line reachable, tip aligned."""
    if total <= rows:
        return 0
    if rows <= 2:
        return total - rows
    # Scrolled to the bottom one row holds the "more above" marker
    return total - rows + 1


def window_lines(total: int, offset: int, rows: int) -> tuple[int, int, bool, bool]:
    """The slice of `total` lines shown in `rows` at `offset`.

    Returns (start, end, above, below): the half-open body slice plus
    whether a "more above" / "more below" marker row is shown. Marker
    rows are reserved out of `rows`, so every body line is reachable at
    some offset; with two rows or fewer the markers are dropped so the
    body still shows.
    """
    if total <= rows:
        return 0, total, False, False
    start = max(0, min(offset, max_window_offset(total, rows)))
    if rows <= 2:
        return start, start + rows, False, False
    above = start > 0
    body = rows - (1 if above else 0)
    end = min(total, start + body)
    below = end < total
    if below:
        end = min(total, start + body - 1)
    return start, end, above, below


def marker_above() -> str:
    return "   ... more above"


def marker_below(remaining: int) -> str:
    return f"   ... {remaining} more below"
