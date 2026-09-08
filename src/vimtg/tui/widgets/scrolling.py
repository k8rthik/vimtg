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
    viewport, never less than one line), "home"/"end" for g/G, or None
    when the key is not a scroll key. Shared by every read-only scrolling
    view (help panel, help screen) so they cannot drift apart.
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
    if key == "g":
        return "home"
    if key == "G":
        return "end"
    return None
