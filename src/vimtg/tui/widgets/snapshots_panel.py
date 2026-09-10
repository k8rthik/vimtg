"""Snapshots panel — renders snapshot log like git log."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.vcs import VCSSnapshot
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.scroll_panel import HEADER_ROWS, fit_line, render_panel_header
from vimtg.tui.widgets.scrolling import (
    WHEEL_LINES,
    compute_scroll_offset,
    resolved_viewport,
    wheel_scroll,
)

ROWS_PER_SNAPSHOT = 2
DEFAULT_VIEWPORT = 42  # 20 snapshots
DESCRIPTION_WIDTH = 35


class SnapshotsPanel(Static):
    """Renders snapshot history for the history screen."""

    class SelectionChanged(Message):
        """The wheel dragged the selection to a different snapshot."""

    default_viewport: int = DEFAULT_VIEWPORT

    snapshots: reactive[list[VCSSnapshot]] = reactive(list, recompose=False)
    selected: reactive[int] = reactive(0)
    focused_panel: reactive[bool] = reactive(False)
    scroll_pos: reactive[int] = reactive(0)
    # Ids on the current branch's first-parent chain; anything else was
    # merged in and is labelled with the branch it came from.
    mainline_ids: reactive[frozenset[str]] = reactive(frozenset)

    @property
    def max_visible(self) -> int:
        """Snapshots that fit: real height when mounted, else the default."""
        rows = resolved_viewport(self.size.height, self.default_viewport, HEADER_ROWS)
        return max(1, rows // ROWS_PER_SNAPSHOT)

    def render(self) -> Text:
        t = render_panel_header(
            "History", self.focused_panel, self.size.width,
            Text(f"  ({len(self.snapshots)})", style="dim"),
        )
        if not self.snapshots:
            t.append("  (no snapshots)\n", style="dim")
            t.append("  Press c to commit\n", style=f"dim {COLORS['comment']}")
            return t

        start = self.scroll_pos
        end = min(start + self.max_visible, len(self.snapshots))
        for i in range(start, end):
            t.append_text(self._render_entry(self.snapshots[i], i == self.selected))
        return t

    def _render_entry(self, snap: VCSSnapshot, selected: bool) -> Text:
        is_selected = selected and self.focused_panel
        width = self.size.width
        # Narrow panels keep the merge/branch/tag decorations and shorten
        # the timestamp to the time alone before anything is truncated.
        t = self._header_row(snap, is_selected, "%b %d %H:%M")
        if width > 0 and t.cell_len > width:
            t = self._header_row(snap, is_selected, "%H:%M")
        fit_line(t, width)
        t.append("\n")

        desc = snap.description
        if len(desc) > DESCRIPTION_WIDTH:
            desc = desc[: DESCRIPTION_WIDTH - 1] + "…"
        style = f"on {COLORS['cursor_bg']}" if is_selected else "dim"
        t.append_text(fit_line(Text(f"     {desc}", style=style), self.size.width))
        t.append("\n")
        return t

    def _header_row(self, snap: VCSSnapshot, is_selected: bool, ts_fmt: str) -> Text:
        t = Text()
        short_hash = snap.id[:7]
        if is_selected:
            t.append(" > ", style=f"bold {COLORS['quantity']}")
            t.append(short_hash, style=f"bold {COLORS['mana_blue']} on {COLORS['cursor_bg']}")
        else:
            t.append("   ", style="")
            t.append(short_hash, style=f"{COLORS['mana_blue']}")
        t.append(f" {snap.timestamp.strftime(ts_fmt)}", style="dim")
        if snap.merge_parent_id:
            t.append(" ⇄ merge", style=f"dim {COLORS['mana_blue']}")
        if self.mainline_ids and snap.id not in self.mainline_ids:
            t.append(f" [{snap.branch}]", style=f"dim {COLORS['category']}")
        if snap.tag:
            t.append(f" ({snap.tag})", style=f"bold {COLORS['sideboard']}")
        return t

    # ── Selection ─────────────────────────────────────────

    def select_next(self) -> None:
        self.select_by(1)

    def select_prev(self) -> None:
        self.select_by(-1)

    def select_first(self) -> None:
        self.select_by(-len(self.snapshots))

    def select_last(self) -> None:
        self.select_by(len(self.snapshots))

    def select_by(self, delta: int) -> None:
        if self.snapshots:
            self.selected = max(0, min(self.selected + delta, len(self.snapshots) - 1))
        else:
            self.selected = 0
        self._adjust_scroll()

    def clamp_selection(self) -> None:
        """Keep selection and scroll valid after the list shrinks or the
        panel is resized (branch delete, rebase, terminal resize)."""
        self.select_by(0)

    def _adjust_scroll(self) -> None:
        self.scroll_pos = compute_scroll_offset(
            self.selected, self.scroll_pos, len(self.snapshots), self.max_visible,
            scrolloff=0,
        )

    def get_selected_snapshot(self) -> VCSSnapshot | None:
        if 0 <= self.selected < len(self.snapshots):
            return self.snapshots[self.selected]
        return None

    # ── Mouse wheel ───────────────────────────────────────

    def wheel(self, delta: int) -> None:
        """Move the window by `delta` snapshots, dragging the selection
        only when it would leave the window (vim-style)."""
        offset, cursor = wheel_scroll(
            self.scroll_pos, self.selected, delta, len(self.snapshots),
            self.max_visible, scrolloff=0,
        )
        changed = cursor != self.selected
        self.scroll_pos, self.selected = offset, cursor
        if changed:
            self.post_message(self.SelectionChanged())

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        self.wheel(max(1, WHEEL_LINES // ROWS_PER_SNAPSHOT))

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        self.wheel(-max(1, WHEEL_LINES // ROWS_PER_SNAPSHOT))
