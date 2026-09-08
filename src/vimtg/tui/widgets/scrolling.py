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
