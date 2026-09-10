"""ScrollablePanel — a titled, line-windowed panel for the history overlay.

Subclasses supply body_lines(); the base renders a two-row header (title
plus rule), windows the body to the widget's height, and exposes vim-style
scrolling (j/k, Ctrl-D/U, gg/G) and the mouse wheel. Headless tests set
default_viewport.
"""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.scrolling import (
    WHEEL_LINES,
    marker_above,
    marker_below,
    max_window_offset,
    resolved_viewport,
    scroll_step_for_key,
    window_lines,
)

HEADER_ROWS = 2  # title row + rule row, shared by every overlay panel
DEFAULT_VIEWPORT = 20
DEFAULT_RULE_WIDTH = 28


def rule_width_for(width: int, default: int = DEFAULT_RULE_WIDTH) -> int:
    """Rule length that fits the panel: one cell of indent, no wrapping."""
    return width - 1 if width > 0 else default


def fit_line(line: Text, width: int) -> Text:
    """Truncate a rendered row to the panel width so it never wraps and
    row-count assumptions (two rows per snapshot) hold. No-op headless."""
    if width > 0 and line.cell_len > width:
        line.truncate(width, overflow="ellipsis")
    return line


def render_panel_header(title: str, focused: bool, width: int, extra: Text | None = None) -> Text:
    """The shared two-row panel header: a title and a rule."""
    color = COLORS["focus"] if focused else COLORS["comment"]
    t = Text()
    t.append(f" {title}", style=f"bold {color}")
    if extra is not None:
        t.append_text(extra)
    t.append("\n")
    t.append(f" {'─' * rule_width_for(width)}\n", style=f"dim {COLORS['comment']}")
    return t


class ScrollablePanel(Static):
    """Titled panel whose body scrolls one line at a time."""

    title: str = ""
    default_viewport: int = DEFAULT_VIEWPORT

    focused_panel: reactive[bool] = reactive(False)
    scroll_pos: reactive[int] = reactive(0)

    # ── Subclass API ──────────────────────────────────────

    def body_lines(self) -> list[Text]:
        """The full, unwindowed body. Override in subclasses."""
        return []

    # ── Geometry ──────────────────────────────────────────

    def viewport_rows(self) -> int:
        """Body rows available: real height when mounted, else the default."""
        return resolved_viewport(self.size.height, self.default_viewport, HEADER_ROWS)

    @property
    def max_scroll(self) -> int:
        return max_window_offset(len(self.body_lines()), self.viewport_rows())

    # ── Scrolling ─────────────────────────────────────────

    def scroll_by(self, delta: int) -> None:
        self.scroll_pos = max(0, min(self.scroll_pos + delta, self.max_scroll))

    def scroll_half_page(self, direction: int) -> None:
        self.scroll_by(direction * max(1, self.viewport_rows() // 2))

    def scroll_to_top(self) -> None:
        self.scroll_pos = 0

    def scroll_to_bottom(self) -> None:
        self.scroll_pos = self.max_scroll

    def clamp(self) -> None:
        """Re-clamp after the body or the viewport changed (resize)."""
        self.scroll_by(0)

    def scroll_key(self, key: str) -> bool:
        """Apply a translated vim scroll key; True when it was one."""
        step = scroll_step_for_key(key, self.viewport_rows())
        if step is None:
            return False
        if step == "home":
            self.scroll_to_top()
        elif step == "end":
            self.scroll_to_bottom()
        else:
            self.scroll_by(int(step))
        return True

    def wheel(self, delta: int) -> None:
        self.scroll_by(delta)

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        self.wheel(WHEEL_LINES)

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        self.wheel(-WHEEL_LINES)

    # ── Rendering ─────────────────────────────────────────

    def window(self) -> list[Text]:
        """The visible rows: body lines plus reserved marker rows."""
        lines = self.body_lines()
        start, end, above, below = window_lines(
            len(lines), self.scroll_pos, self.viewport_rows()
        )
        marker = f"dim {COLORS['comment']}"
        out: list[Text] = []
        if above:
            out.append(Text(marker_above(), style=marker))
        out.extend(lines[start:end])
        if below:
            out.append(Text(marker_below(len(lines) - end), style=marker))
        return out

    def render(self) -> Text:
        t = render_panel_header(self.title, self.focused_panel, self.size.width)
        for line in self.window():
            t.append_text(line)
            t.append("\n")
        return t
