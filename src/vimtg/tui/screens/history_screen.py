"""HistoryScreen — a floating, lazygit-style version control overlay.

Opens as a modal window centred over the editor (lazy.nvim style: a
bordered box with the editor dimmed behind it). Five panels — working
copy, branches, snapshots, diff, stats — with vim navigation, commits,
branches, tags, merge, rebase, cherry-pick, and restore. q, Escape, or gh
drop back into the editor.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from enum import Enum

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Key, Resize
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static

from vimtg.domain.deck_diff import DeckDiff
from vimtg.domain.deck_merge import CardKey
from vimtg.editor.config_options import currency_symbol_for
from vimtg.services.deck_diff_service import DeckDiffService
from vimtg.services.vcs_service import (
    MergeKind,
    PendingMerge,
    VersionControlService,
)
from vimtg.tui.key_translator import translate
from vimtg.tui.keys import CLOSE_KEYS, FULL_HELP_KEY, HELP_KEY, PENDING, VimNav, render_hints
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.branches_panel import BranchesPanel
from vimtg.tui.widgets.diff_panel import DiffPanel
from vimtg.tui.widgets.scroll_panel import ScrollablePanel
from vimtg.tui.widgets.snapshots_panel import SnapshotsPanel
from vimtg.tui.widgets.stats_panel import StatsPanel
from vimtg.tui.widgets.working_copy_panel import WorkingCopyPanel


class Panel(Enum):
    WORKING = 0
    BRANCHES = 1
    SNAPSHOTS = 2
    DIFF = 3
    STATS = 4


_PANEL_JUMP_KEYS = {str(p.value + 1): p for p in Panel}


class InputMode(Enum):
    NORMAL = "normal"
    COMMIT = "commit"
    BRANCH = "branch"
    TAG = "tag"
    CONFIRM_RESTORE = "confirm_restore"
    CONFIRM_REBASE = "confirm_rebase"
    CONFIRM_DELETE_BRANCH = "confirm_delete_branch"


# Action keys → HistoryScreen method names. Every key here must appear in
# _HINTS (tests/tui/test_history_overlay.py checks the two stay in sync).
# Navigation keys (j/k, gg/G, Ctrl-D/U, 1-5, Tab, Enter, q/Esc/gh) are
# documented in the window subtitle and the :help history topic.
_ACTIONS: dict[str, str] = {
    "c": "_start_commit",
    "b": "_start_branch",
    "B": "_switch_branch",
    "D": "_start_delete_branch",
    "m": "_merge_selected_branch",
    "r": "_start_rebase",
    "t": "_start_tag",
    "T": "_untag",
    "R": "_start_restore",
    "p": "_cherry_pick",
    "d": "_toggle_detail",
}

# Keys that act on a panel's cursor only live in that panel, so a user
# looking elsewhere is never surprised by an operation on a hidden cursor.
_BRANCH_ACTIONS = frozenset({"B", "D", "m", "r"})
_SNAPSHOT_ACTIONS = frozenset({"t", "T", "R", "p"})

_HINTS = (
    ("q/Esc", "back"), ("1-5", "panels"), ("c", "commit"),
    ("b/B/D", "branch"), ("m", "merge"), ("r", "rebase"),
    ("t/T", "tag"), ("R", "restore"), ("p", "pick"),
    ("d", "detail"), ("Enter", "open"), ("?", "help"),
)


class HistoryCommandLine(Static):
    """Bottom command line for history screen prompts."""

    prompt: reactive[str] = reactive("")
    text: reactive[str] = reactive("")
    message: reactive[str] = reactive("")
    cursor_pos: reactive[int] = reactive(0)
    pending: reactive[str] = reactive("")  # showcmd: a pending "g"

    def render(self) -> Text:
        t = Text()
        if self.pending:
            t.append(f" {self.pending}-", style=f"bold {COLORS['quantity']}")
        if self.message:
            t.append(f" {self.message}", style=f"bold {COLORS['mana_green']}")
            return t
        if self.prompt:
            pos = min(self.cursor_pos, len(self.text))
            before = self.text[:pos]
            cursor_char = self.text[pos] if pos < len(self.text) else " "
            after = self.text[pos + 1:] if pos < len(self.text) else ""
            t.append(f" {self.prompt}", style=f"bold {COLORS['mode_command']}")
            t.append(before, style="bold")
            t.append(cursor_char, style="bold reverse")
            t.append(after, style="bold")
            return t
        width = self.size.width - (len(self.pending) + 2 if self.pending else 0)
        t.append_text(render_hints(_HINTS, width))
        return t

    def show_prompt(self, prompt: str) -> None:
        self.prompt = prompt
        self.text = ""
        self.cursor_pos = 0
        self.message = ""

    def show_message(self, msg: str) -> None:
        self.message = msg
        self.prompt = ""
        self.text = ""

    def hide(self) -> None:
        self.prompt = ""
        self.text = ""
        self.message = ""
        self.cursor_pos = 0
        self.pending = ""


class HistoryStatusLine(Static):
    """Status bar for history screen."""

    deck_name: reactive[str] = reactive("")
    branch: reactive[str] = reactive("main")
    snapshot_count: reactive[int] = reactive(0)
    active_panel: reactive[Panel] = reactive(Panel.SNAPSHOTS)

    def render(self) -> Text:
        t = Text()
        t.append(" HISTORY ", style=f"bold {COLORS['mode_command']} on {COLORS['bg']}")
        t.append(f" {self.deck_name}", style="bold")
        t.append(f"  [{self.branch}]", style=f"bold {COLORS['mana_green']}")
        t.append(f"  {self.snapshot_count} snapshots", style="dim")
        panel_name = self.active_panel.name.title().replace("_", " ")
        t.append(f"  ┃ {panel_name}", style=f"dim {COLORS['comment']}")
        return t


class HistoryScreen(ModalScreen[None]):
    """Floating lazygit-style version control overlay."""

    CSS = f"""
    HistoryScreen {{
        align: center middle;
        background: rgba(0, 0, 0, 0.55);
    }}
    #history-window {{
        width: 90%;
        height: 85%;
        max-width: 140;
        layout: vertical;
        background: {COLORS['bg']};
        border: round {COLORS['tag']};
        border-title-color: {COLORS['tag']};
        border-title-style: bold;
        border-subtitle-color: {COLORS['comment']};
    }}
    #history-layout {{
        layout: horizontal;
        height: 1fr;
    }}
    #left-column {{
        width: 2fr;
        layout: vertical;
    }}
    #right-column {{
        width: 3fr;
        layout: vertical;
    }}
    #working-panel {{
        height: auto;
        max-height: 4;
    }}
    #branches-panel {{
        height: auto;
        max-height: 10;
    }}
    #snapshots-panel {{
        height: 1fr;
    }}
    #diff-panel {{
        height: 2fr;
    }}
    #stats-panel {{
        height: 1fr;
        max-height: 12;
    }}
    #history-bottom {{
        dock: bottom;
        height: 2;
        layout: vertical;
        background: {COLORS['bg']};
    }}
    #history-status, #history-command {{
        height: 1;
    }}
    """

    def __init__(
        self,
        vcs_service: VersionControlService,
        diff_service: DeckDiffService,
        current_deck_state: str,
        deck_name: str,
        on_restore: Callable[[str], None] | None = None,
        price_source: str = "usd",
        on_apply_state: Callable[[str, str], None] | None = None,
    ) -> None:
        """`on_restore(state)` loads a snapshot into the editor (R).
        `on_apply_state(state, reason)` adopts a merge/rebase/switch/
        cherry-pick result; when absent, on_restore is used for those too."""
        super().__init__()
        self._vcs = vcs_service
        self._diff_svc = diff_service
        self._current_state = current_deck_state
        self._deck_name = deck_name
        self._on_restore = on_restore
        self._on_apply_state = on_apply_state
        self._price_source = price_source
        self._diff_key: tuple[str, str] | None = None
        self._active_panel = Panel.SNAPSHOTS
        self._input_mode = InputMode.NORMAL
        self._input_text = ""
        self._rebase_target: str | None = None
        self._delete_target: str | None = None
        self._nav = VimNav()

    def compose(self) -> ComposeResult:
        with Container(id="history-window"):
            yield Container(
                Container(
                    WorkingCopyPanel(id="working-panel"),
                    BranchesPanel(id="branches-panel"),
                    SnapshotsPanel(id="snapshots-panel"),
                    id="left-column",
                ),
                Container(
                    DiffPanel(id="diff-panel"),
                    StatsPanel(id="stats-panel"),
                    id="right-column",
                ),
                id="history-layout",
            )
            yield Container(
                HistoryStatusLine(id="history-status"),
                HistoryCommandLine(id="history-command"),
                id="history-bottom",
            )

    def on_mount(self) -> None:
        window = self.query_one("#history-window", Container)
        window.border_title = f" History — {self._deck_name} "
        window.border_subtitle = " q / Esc / gh close "
        self._stats.currency = currency_symbol_for(self._price_source)
        self._refresh_data()
        self._update_diff()
        self._sync_focus()

    # ── Widget accessors ──────────────────────────────────

    @property
    def _working(self) -> WorkingCopyPanel:
        return self.query_one("#working-panel", WorkingCopyPanel)

    @property
    def _branches(self) -> BranchesPanel:
        return self.query_one("#branches-panel", BranchesPanel)

    @property
    def _snapshots(self) -> SnapshotsPanel:
        return self.query_one("#snapshots-panel", SnapshotsPanel)

    @property
    def _diff(self) -> DiffPanel:
        return self.query_one("#diff-panel", DiffPanel)

    @property
    def _stats(self) -> StatsPanel:
        return self.query_one("#stats-panel", StatsPanel)

    @property
    def _cl(self) -> HistoryCommandLine:
        return self.query_one("#history-command", HistoryCommandLine)

    def _scroll_panel(self) -> ScrollablePanel | None:
        if self._active_panel is Panel.DIFF:
            return self._diff
        if self._active_panel is Panel.STATS:
            return self._stats
        return None

    # ── Data refresh ──────────────────────────────────────

    def _refresh_data(self) -> None:
        bp, sp, wp = self._branches, self._snapshots, self._working
        sl = self.query_one("#history-status", HistoryStatusLine)

        bp.branches = self._vcs.list_branches()
        bp.current_branch = self._vcs.current_branch
        bp.clamp_selection()
        history = self._vcs.get_history()
        sp.snapshots = history
        sp.mainline_ids = frozenset(
            snap.id for snap in self._vcs.get_log(limit=max(1, len(history)))
        )
        sp.clamp_selection()

        tip = history[0] if history else None
        wp.has_tip = tip is not None
        wp.dirty = tip is not None and self._vcs.is_dirty(self._current_state)
        wp.diff = self._working_diff(tip.deck_state) if tip is not None else None
        self._diff_key = None  # data changed: next _update_diff recomputes

        sl.deck_name = self._deck_name
        sl.branch = self._vcs.current_branch
        sl.snapshot_count = len(sp.snapshots)
        sl.active_panel = self._active_panel

    def _working_diff(self, tip_state: str) -> DeckDiff:
        return self._diff_svc.diff_snapshot_parent(
            self._current_state, tip_state, self._price_source
        )

    def _update_diff(self) -> None:
        """Diff + stats follow the active panel: the working copy shows the
        buffer against the tip, anything else shows the selected snapshot
        against its parent. Recomputed only when the source changes, so
        moving between panels keeps the Diff's scroll position."""
        dp, stp = self._diff, self._stats
        snap = self._snapshots.get_selected_snapshot()
        key = (
            ("working", "") if self._active_panel is Panel.WORKING
            else ("snapshot", snap.id if snap else "")
        )
        if key == self._diff_key:
            return
        self._diff_key = key

        if self._active_panel is Panel.WORKING:
            diff = self._working.diff
            dp.diff = diff
            self._set_stats(diff)
            return
        if snap is None:
            dp.diff = None
            stp.stats_delta = None
            return
        parent_state: str | None = None
        if snap.parent_id:
            parent_state = self._vcs.checkout(snap.parent_id)
        diff = self._diff_svc.diff_snapshot_parent(
            snap.deck_state, parent_state, self._price_source
        )
        dp.diff = diff
        self._set_stats(diff)

    def _set_stats(self, diff: DeckDiff | None) -> None:
        stp = self._stats
        stp.stats_delta = diff.stats_delta if diff else None
        if diff is not None and diff.stats_delta is None:
            stp.placeholder = "No card data — run vimtg sync for stats"
        else:
            stp.placeholder = StatsPanel.DEFAULT_PLACEHOLDER

    def _sync_focus(self) -> None:
        self._working.focused_panel = self._active_panel is Panel.WORKING
        self._branches.focused_panel = self._active_panel is Panel.BRANCHES
        self._snapshots.focused_panel = self._active_panel is Panel.SNAPSHOTS
        self._diff.focused_panel = self._active_panel is Panel.DIFF
        self._stats.focused_panel = self._active_panel is Panel.STATS
        self.query_one("#history-status", HistoryStatusLine).active_panel = (
            self._active_panel
        )

    def on_resize(self, event: Resize) -> None:
        """Keep selections visible and offsets valid after a resize."""
        if not self.is_mounted:
            return
        self._snapshots.clamp_selection()
        self._branches.clamp_selection()
        self._diff.clamp()
        self._stats.clamp()

    def on_snapshots_panel_selection_changed(
        self, message: SnapshotsPanel.SelectionChanged
    ) -> None:
        """The wheel moved the snapshot selection: follow it in Diff/Stats."""
        message.stop()
        self._update_diff()

    # ── Key dispatch ──────────────────────────────────────

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+c":
            return
        event.prevent_default()
        event.stop()

        key = translate(event.key)
        try:
            self._dispatch_key(key, event)
        except sqlite3.Error as exc:
            # A locked/failed database must not take down the screen
            self._cl.show_message(f"E: Database error: {exc}")
            self._input_mode = InputMode.NORMAL
            self._input_text = ""

    def _dispatch_key(self, key: str, event: Key) -> None:
        if self._input_mode != InputMode.NORMAL:
            self._handle_input_key(key, event)
            return
        if self._cl.message:
            self._cl.hide()

        # Shared navigation: j/k, Ctrl-D/U, gg/G, Home/End — plus gh to close
        was_pending = self._nav.pending_g
        step = self._nav.feed(key, self._active_viewport())
        self._cl.pending = "g" if self._nav.pending_g else ""
        if step == PENDING:
            return
        if was_pending and key == "h":
            self._close()
            return
        if step == "home":
            self._go_top()
            return
        if step == "end":
            self._go_bottom()
            return
        if step is not None:
            self._nav_by(int(step))
            return

        if key in _PANEL_JUMP_KEYS:
            self._jump_panel(_PANEL_JUMP_KEYS[key])
        elif key == "tab":
            self._cycle_panel(1)
        elif key == "shift_tab":
            self._cycle_panel(-1)
        elif key in CLOSE_KEYS:
            self._close()
        elif key in (HELP_KEY, FULL_HELP_KEY):
            from vimtg.tui.screens.help_screen import HelpScreen

            self.app.push_screen(HelpScreen(topic="history" if key == HELP_KEY else None))
        elif key == "enter":
            self._handle_enter()
        else:
            self._dispatch_action(key)

    def _active_viewport(self) -> int:
        if self._active_panel is Panel.BRANCHES:
            return self._branches.max_visible
        if self._active_panel is Panel.SNAPSHOTS:
            return self._snapshots.max_visible
        if (panel := self._scroll_panel()) is not None:
            return panel.viewport_rows()
        return 1

    def _dispatch_action(self, key: str) -> None:
        method = _ACTIONS.get(key)
        if method is None:
            return
        if key in _BRANCH_ACTIONS and self._active_panel is not Panel.BRANCHES:
            self._cl.show_message("Branch actions work in the Branches panel (2)")
            return
        if key in _SNAPSHOT_ACTIONS and self._active_panel is not Panel.SNAPSHOTS:
            self._cl.show_message("Snapshot actions work in the Snapshots panel (3)")
            return
        action: Callable[[], None] = getattr(self, method)
        action()

    def _close(self) -> None:
        self.app.pop_screen()

    # ── Panels and navigation ─────────────────────────────

    def _jump_panel(self, panel: Panel) -> None:
        self._active_panel = panel
        self._sync_focus()
        self._update_diff()

    def _cycle_panel(self, direction: int) -> None:
        panels = list(Panel)
        idx = panels.index(self._active_panel)
        self._jump_panel(panels[(idx + direction) % len(panels)])

    def _nav_by(self, delta: int) -> None:
        if self._active_panel is Panel.BRANCHES:
            self._branches.select_by(delta)
        elif self._active_panel is Panel.SNAPSHOTS:
            self._snapshots.select_by(delta)
            self._update_diff()
        elif (panel := self._scroll_panel()) is not None:
            panel.scroll_by(delta)

    def _go_top(self) -> None:
        if self._active_panel is Panel.BRANCHES:
            self._branches.select_first()
        elif self._active_panel is Panel.SNAPSHOTS:
            self._snapshots.select_first()
            self._update_diff()
        elif (panel := self._scroll_panel()) is not None:
            panel.scroll_to_top()

    def _go_bottom(self) -> None:
        if self._active_panel is Panel.BRANCHES:
            self._branches.select_last()
        elif self._active_panel is Panel.SNAPSHOTS:
            self._snapshots.select_last()
            self._update_diff()
        elif (panel := self._scroll_panel()) is not None:
            panel.scroll_to_bottom()

    # ── Input mode handling ───────────────────────────────

    def _handle_input_key(self, key: str, event: Key) -> None:
        cl = self._cl
        if key == "escape":
            self._input_mode = InputMode.NORMAL
            self._input_text = ""
            cl.hide()
            return
        if key == "enter":
            self._submit_input()
            return
        if key == "backspace":
            if self._input_text:
                self._input_text = self._input_text[:-1]
                cl.text = self._input_text
                cl.cursor_pos = len(self._input_text)
            return
        char = event.character
        if char and len(char) == 1 and ord(char) >= 32:
            self._input_text += char
            cl.text = self._input_text
            cl.cursor_pos = len(self._input_text)

    def _submit_input(self) -> None:
        text = self._input_text.strip()
        mode = self._input_mode
        self._input_mode = InputMode.NORMAL
        self._input_text = ""
        handlers: dict[InputMode, Callable[[str], None]] = {
            InputMode.COMMIT: self._submit_commit,
            InputMode.BRANCH: self._submit_branch,
            InputMode.TAG: self._submit_tag,
            InputMode.CONFIRM_RESTORE: self._submit_restore,
            InputMode.CONFIRM_REBASE: self._submit_rebase,
            InputMode.CONFIRM_DELETE_BRANCH: self._submit_delete_branch,
        }
        handler = handlers.get(mode)
        if handler is not None:
            handler(text)

    @staticmethod
    def _confirmed(text: str) -> bool:
        return text.lower() in ("y", "yes")

    def _submit_commit(self, text: str) -> None:
        if not text:
            self._cl.show_message("Cancelled (empty description)")
            return
        snap = self._vcs.commit(self._current_state, text)
        self._cl.show_message(f"Snapshot: {snap.description}")
        self._refresh_data()
        self._update_diff()

    def _submit_branch(self, text: str) -> None:
        if not text:
            self._cl.show_message("Cancelled (empty name)")
            return
        if self._vcs.create_branch(text):
            self._cl.show_message(f"Branch created: {text}")
            self._refresh_data()
        else:
            self._cl.show_message(f"Branch '{text}' already exists")

    def _submit_tag(self, text: str) -> None:
        if not text:
            self._cl.show_message("Cancelled (empty tag)")
            return
        selected = self._snapshots.get_selected_snapshot()
        if selected:
            self._vcs.tag(selected.id, text)
            self._cl.show_message(f"Tagged: {text}")
            self._refresh_data()
            self._update_diff()

    def _submit_restore(self, text: str) -> None:
        if not self._confirmed(text):
            self._cl.show_message("Restore cancelled")
            return
        selected = self._snapshots.get_selected_snapshot()
        if selected is None:
            self._cl.show_message("No snapshot selected")
            return
        if self._on_restore is None:
            self._cl.show_message("Restore unavailable in this view")
            return
        self._on_restore(selected.deck_state)
        self._close()

    def _submit_rebase(self, text: str) -> None:
        target, self._rebase_target = self._rebase_target, None
        if not (self._confirmed(text) and target):
            self._cl.show_message("Rebase cancelled")
            return
        result = self._vcs.rebase(target)
        self._apply_vcs_state(result.new_state, f"rebase onto {target}")
        self._cl.show_message(result.message)
        self._refresh_data()
        self._update_diff()

    def _submit_delete_branch(self, text: str) -> None:
        target, self._delete_target = self._delete_target, None
        if not (self._confirmed(text) and target):
            self._cl.show_message("Delete cancelled")
            return
        if self._vcs.delete_branch(target):
            self._cl.show_message(f"Deleted branch: {target}")
        else:
            self._cl.show_message(f"Cannot delete branch: {target}")
        self._refresh_data()
        self._update_diff()

    # ── Action starters ───────────────────────────────────

    def _prompt(self, prompt: str, mode: InputMode) -> None:
        self._cl.show_prompt(prompt)
        self._input_mode = mode
        self._input_text = ""

    def _start_commit(self) -> None:
        self._prompt("Commit message: ", InputMode.COMMIT)

    def _start_branch(self) -> None:
        self._prompt("Branch name: ", InputMode.BRANCH)

    def _start_tag(self) -> None:
        snap = self._snapshots.get_selected_snapshot()
        if snap is None:
            self._cl.show_message("No snapshot selected")
            return
        self._prompt(f"Tag for {snap.id[:7]}: ", InputMode.TAG)

    def _start_restore(self) -> None:
        snap = self._snapshots.get_selected_snapshot()
        if snap is None:
            self._cl.show_message("No snapshot selected")
            return
        self._prompt(f"Restore {snap.id[:7]}? (y/N): ", InputMode.CONFIRM_RESTORE)

    def _start_delete_branch(self) -> None:
        branch = self._branches.get_selected_branch()
        if branch is None:
            self._cl.show_message("Select a branch (2 or Tab to Branches panel)")
            return
        if branch.name == self._vcs.current_branch:
            self._cl.show_message("Cannot delete the current branch (B to switch first)")
            return
        self._delete_target = branch.name
        self._prompt(
            f"Delete branch {branch.name}? (y/N): ", InputMode.CONFIRM_DELETE_BRANCH
        )

    def _switch_branch(self) -> None:
        branch = self._branches.get_selected_branch()
        if branch is None:
            self._cl.show_message("No branch selected")
            return
        if branch.name == self._vcs.current_branch:
            self._cl.show_message("Already on that branch")
            return
        if self._vcs.is_dirty(self._current_state):
            self._cl.show_message("Uncommitted changes — commit first (c)")
            return
        state = self._vcs.switch_branch(branch.name)
        if state is None:
            self._cl.show_message(f"Cannot switch to: {branch.name}")
            return
        self._apply_vcs_state(state, f"switch to {branch.name}")
        self._cl.show_message(f"Switched to: {branch.name}")
        self._refresh_data()
        self._snapshots.select_first()
        self._update_diff()

    def _untag(self) -> None:
        snap = self._snapshots.get_selected_snapshot()
        if snap is None or not snap.tag:
            self._cl.show_message("No tag on selected snapshot")
            return
        self._vcs.untag(snap.id)
        self._cl.show_message(f"Removed tag: {snap.tag}")
        self._refresh_data()
        self._update_diff()

    def _cherry_pick(self) -> None:
        snap = self._snapshots.get_selected_snapshot()
        if snap is None:
            self._cl.show_message("No snapshot selected")
            return
        if self._vcs.cherry_pick(snap.id) is None:
            self._cl.show_message("Cherry-pick failed")
            return
        tip = self._vcs.get_log(limit=1)
        if tip:
            self._apply_vcs_state(tip[0].deck_state, f"cherry-pick: {snap.description}")
        self._cl.show_message(f"Cherry-picked: {snap.description}")
        self._refresh_data()
        self._update_diff()

    def _apply_vcs_state(self, new_state: str | None, reason: str) -> None:
        """Adopt a merge/rebase/switch/cherry-pick result into the screen and
        the editor buffer; `reason` labels the editor's undo entry."""
        if new_state is None:
            return
        self._current_state = new_state
        if self._on_apply_state is not None:
            self._on_apply_state(new_state, reason)
        elif self._on_restore is not None:
            self._on_restore(new_state)

    def _selected_other_branch(self) -> str | None:
        """The selected branch name, or None if unusable as a merge source."""
        branch = self._branches.get_selected_branch()
        if branch is None:
            self._cl.show_message("Select a branch (2 or Tab to Branches panel)")
            return None
        if branch.name == self._vcs.current_branch:
            self._cl.show_message("Already on that branch")
            return None
        if self._vcs.is_dirty(self._current_state):
            self._cl.show_message("Uncommitted changes — commit first (c)")
            return None
        return branch.name

    def _merge_selected_branch(self) -> None:
        name = self._selected_other_branch()
        if name is None:
            return
        result = self._vcs.merge_branch(name)
        if result.kind is MergeKind.CONFLICTS and result.pending is not None:
            from vimtg.tui.screens.merge_screen import MergeScreen

            pending = result.pending
            self.app.push_screen(MergeScreen(
                pending=pending,
                deck_name=self._deck_name,
                on_complete=lambda res: self._finish_merge(pending, res),
                on_abort=self._merge_aborted,
            ))
            return
        self._apply_vcs_state(result.new_state, f"merge {name}")
        self._cl.show_message(result.message)
        self._refresh_data()
        self._update_diff()

    def _merge_aborted(self) -> None:
        self._cl.show_message("Merge aborted — nothing committed")

    def _finish_merge(
        self,
        pending: PendingMerge,
        resolutions: dict[CardKey, int | None],
    ) -> None:
        # Runs from MergeScreen's callback, outside on_key's sqlite guard —
        # a locked DB here must not crash the app after the user resolved
        # every conflict by hand.
        try:
            result = self._vcs.complete_merge(pending, resolutions)
        except sqlite3.Error as exc:
            self._cl.show_message(f"E: Merge failed: {exc}")
            return
        self._apply_vcs_state(result.new_state, f"merge {pending.source_label}")
        self._cl.show_message(result.message)
        self._refresh_data()
        self._update_diff()

    def _start_rebase(self) -> None:
        name = self._selected_other_branch()
        if name is None:
            return
        self._rebase_target = name
        self._prompt(
            f"Rebase {self._vcs.current_branch} onto {name}? (y/N): ",
            InputMode.CONFIRM_REBASE,
        )

    def _toggle_detail(self) -> None:
        dp = self._diff
        dp.show_unchanged = not dp.show_unchanged
        self._cl.show_message(
            "Detail: showing unchanged cards"
            if dp.show_unchanged
            else "Detail: hiding unchanged cards"
        )

    def _handle_enter(self) -> None:
        """Enter opens the item: switch to the branch, or read the diff."""
        if self._active_panel is Panel.BRANCHES:
            self._switch_branch()
        elif self._active_panel in (Panel.SNAPSHOTS, Panel.WORKING):
            self._jump_panel(Panel.DIFF)
