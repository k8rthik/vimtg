"""Working-copy panel — the editor buffer versus the branch tip.

The lazygit "files" box: what would go into the next commit. Selecting it
in the overlay shows the same diff in the Diff panel.
"""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.deck_diff import ChangeType, DeckDiff
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.scroll_panel import fit_line, render_panel_header


class WorkingCopyPanel(Static):
    """Summarises uncommitted changes against the current branch tip.

    `dirty` is the VCS's own verdict (cards, metadata, and sideboard plans),
    so it agrees with the merge/rebase gate; `diff` only knows about cards
    and supplies the counts.
    """

    diff: reactive[DeckDiff | None] = reactive(None, recompose=False)
    dirty: reactive[bool] = reactive(False)
    has_tip: reactive[bool] = reactive(True)
    focused_panel: reactive[bool] = reactive(False)

    def render(self) -> Text:
        t = render_panel_header("Working copy", self.focused_panel, self.size.width)
        t.append_text(self._with_hint(self._summary()))
        t.append("\n")
        return t

    def _summary(self) -> Text:
        if not self.has_tip:
            return Text("  (no snapshots yet)", style="dim")
        if not self.dirty:
            return Text("  clean — matches the tip", style=f"dim {COLORS['mana_green']}")
        diff = self.diff
        if diff is None or not diff.has_changes:
            return Text("  metadata or plans changed", style=f"{COLORS['sideboard']}")

        changed = sum(
            1 for c in diff.changes
            if c.change_type in (ChangeType.QUANTITY_CHANGED, ChangeType.SECTION_MOVED)
        )
        t = Text("  ")
        t.append(f"+{diff.added_count}", style=f"bold {COLORS['mana_green']}")
        t.append("  ")
        t.append(f"-{diff.removed_count}", style=f"bold {COLORS['mana_red']}")
        if changed:
            t.append("  ")
            t.append(f"~{changed}", style=f"bold {COLORS['sideboard']}")
        t.append("  uncommitted", style="dim")
        return t

    def _with_hint(self, line: Text) -> Text:
        """Append the commit hint when it fits; never let the row wrap."""
        hint = "   c commit"
        if self.has_tip and not self.dirty:
            return fit_line(line, self.size.width)
        width = self.size.width
        if width <= 0 or line.cell_len + len(hint) <= width:
            line.append(hint, style=f"dim {COLORS['comment']}")
        return fit_line(line, width)
