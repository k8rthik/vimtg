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

    max_offset = total - viewport
    offset = current_offset

    # Scrolling down: selection too close to bottom of viewport
    if selected > offset + viewport - 1 - scrolloff:
        offset = selected - viewport + 1 + scrolloff

    # Scrolling up: selection too close to top of viewport
    if selected < offset + scrolloff:
        offset = selected - scrolloff

    return max(0, min(offset, max_offset))
