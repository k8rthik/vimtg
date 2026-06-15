"""HistoryScreen — lazygit-style version control for decklists.

Multi-pane TUI for browsing deck history, creating snapshots, managing
branches, tagging tournament versions, and restoring previous states.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Key
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Static

from vimtg.services.deck_diff_service import DeckDiffService
from vimtg.services.vcs_service import VersionControlService
from vimtg.tui.key_translator import translate
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.branches_panel import BranchesPanel
from vimtg.tui.widgets.diff_panel import DiffPanel
from vimtg.tui.widgets.snapshots_panel import SnapshotsPanel
from vimtg.tui.widgets.stats_panel import StatsPanel


class Panel(Enum):
    BRANCHES = 0
    SNAPSHOTS = 1
    DIFF = 2
    STATS = 3


class InputMode(Enum):
    NORMAL = "normal"
    COMMIT = "commit"
    BRANCH = "branch"
    TAG = "tag"
    CONFIRM_RESTORE = "confirm_restore"


class HistoryCommandLine(Static):
    """Bottom command line for history screen prompts."""

    prompt: reactive[str] = reactive("")
    text: reactive[str] = reactive("")
    message: reactive[str] = reactive("")
    cursor_pos: reactive[int] = reactive(0)

    def render(self) -> Text:
        t = Text()
        if self.message:
            t.append(f" {self.message}", style=f"bold {COLORS['mana_green']}")
            return t
        if self.prompt:
            t.append(f" {self.prompt}", style=f"bold {COLORS['mode_command']}")
            t.append(self.text, style="bold")
            # Cursor
            if self.cursor_pos <= len(self.text):
                pos = self.cursor_pos
                before = self.text[:pos]
                cursor_char = self.text[pos] if pos < len(self.text) else " "
                after = self.text[pos + 1:] if pos < len(self.text) else ""
                t = Text()
                t.append(f" {self.prompt}", style=f"bold {COLORS['mode_command']}")
                t.append(before, style="bold")
                t.append(cursor_char, style="bold reverse")
                t.append(after, style="bold")
            return t
        # Default hint bar
        t.append(" c", style=f"bold {COLORS['quantity']}")
        t.append("ommit ", style="dim")
        t.append("b", style=f"bold {COLORS['quantity']}")
        t.append("ranch ", style="dim")
        t.append("t", style=f"bold {COLORS['quantity']}")
        t.append("ag ", style="dim")
        t.append("R", style=f"bold {COLORS['quantity']}")
        t.append("estore ", style="dim")
        t.append("d", style=f"bold {COLORS['quantity']}")
        t.append("etail ", style="dim")
        t.append("Tab", style=f"bold {COLORS['quantity']}")
        t.append(":panels ", style="dim")
        t.append("q", style=f"bold {COLORS['quantity']}")
        t.append(":back", style="dim")
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
        panel_name = self.active_panel.name.title()
        t.append(f"  \u2503 {panel_name}", style=f"dim {COLORS['comment']}")
        return t


class HistoryScreen(Screen[None]):
    """Lazygit-style version control screen for deck history."""

    CSS = f"""
    #history-layout {{
        layout: horizontal;
        height: 1fr;
    }}
    #left-column {{
        width: 1fr;
        layout: vertical;
    }}
    #right-column {{
        width: 2fr;
        layout: vertical;
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
        height: auto;
        max-height: 12;
    }}
    #history-status {{
        height: 1;
        dock: bottom;
        background: {COLORS['bg']};
    }}
    #history-command {{
        height: 1;
        dock: bottom;
        background: {COLORS['bg']};
    }}
    """

    def __init__(
        self,
        vcs_service: VersionControlService,
        diff_service: DeckDiffService,
        current_deck_state: str,
        deck_name: str,
        on_restore: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self._vcs = vcs_service
        self._diff_svc = diff_service
        self._current_state = current_deck_state
        self._deck_name = deck_name
        self._on_restore = on_restore
        self._active_panel = Panel.SNAPSHOTS
        self._input_mode = InputMode.NORMAL
        self._input_text = ""

    def compose(self) -> ComposeResult:
        yield Container(
            Container(
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
        yield HistoryStatusLine(id="history-status")
        yield HistoryCommandLine(id="history-command")

    def on_mount(self) -> None:
        self._refresh_data()
        self._update_diff_for_selected()
        self._sync_focus()

    # ── Data refresh ──────────────────────────────────────

    def _refresh_data(self) -> None:
        bp = self.query_one("#branches-panel", BranchesPanel)
        sp = self.query_one("#snapshots-panel", SnapshotsPanel)
        sl = self.query_one("#history-status", HistoryStatusLine)

        bp.branches = self._vcs.list_branches()
        bp.current_branch = self._vcs.current_branch
        sp.snapshots = self._vcs.get_log()

        sl.deck_name = self._deck_name
        sl.branch = self._vcs.current_branch
        sl.snapshot_count = len(sp.snapshots)
        sl.active_panel = self._active_panel

    def _update_diff_for_selected(self) -> None:
        sp = self.query_one("#snapshots-panel", SnapshotsPanel)
        dp = self.query_one("#diff-panel", DiffPanel)
        stp = self.query_one("#stats-panel", StatsPanel)

        snap = sp.get_selected_snapshot()
        if snap is None:
            dp.diff = None
            stp.stats_delta = None
            return

        # Get parent state
        parent_state: str | None = None
        if snap.parent_id:
            parent_state = self._vcs.checkout(snap.parent_id)

        diff = self._diff_svc.diff_snapshot_parent(
            snap.deck_state, parent_state,
        )
        dp.diff = diff
        stp.stats_delta = diff.stats_delta

    def _sync_focus(self) -> None:
        bp = self.query_one("#branches-panel", BranchesPanel)
        sp = self.query_one("#snapshots-panel", SnapshotsPanel)
        dp = self.query_one("#diff-panel", DiffPanel)
        stp = self.query_one("#stats-panel", StatsPanel)

        bp.focused_panel = self._active_panel == Panel.BRANCHES
        sp.focused_panel = self._active_panel == Panel.SNAPSHOTS
        dp.focused_panel = self._active_panel == Panel.DIFF
        stp.focused_panel = self._active_panel == Panel.STATS

        sl = self.query_one("#history-status", HistoryStatusLine)
        sl.active_panel = self._active_panel

    # ── Key dispatch ──────────────────────────────────────

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+c":
            return
        event.prevent_default()
        event.stop()

        key = translate(event.key)

        # Handle input modes (commit, branch, tag prompts)
        if self._input_mode != InputMode.NORMAL:
            self._handle_input_key(key, event)
            return

        cl = self.query_one("#history-command", HistoryCommandLine)
        if cl.message:
            cl.hide()

        # Panel navigation
        if key == "tab":
            self._cycle_panel(1)
        elif key == "shift_tab":
            self._cycle_panel(-1)
        elif key in ("j", "down"):
            self._nav_down()
        elif key in ("k", "up"):
            self._nav_up()
        # Actions
        elif key == "c":
            self._start_commit()
        elif key == "b":
            self._start_branch()
        elif key == "B":
            self._switch_branch()
        elif key == "t":
            self._start_tag()
        elif key == "T":
            self._untag()
        elif key == "R":
            self._start_restore()
        elif key == "p":
            self._cherry_pick()
        elif key == "d":
            self._toggle_detail()
        elif key in ("q", "escape"):
            self.app.pop_screen()
        elif key == "enter":
            self._handle_enter()

    def _cycle_panel(self, direction: int) -> None:
        panels = list(Panel)
        idx = panels.index(self._active_panel)
        self._active_panel = panels[(idx + direction) % len(panels)]
        self._sync_focus()

    def _nav_down(self) -> None:
        if self._active_panel == Panel.BRANCHES:
            bp = self.query_one("#branches-panel", BranchesPanel)
            bp.select_next()
        elif self._active_panel == Panel.SNAPSHOTS:
            sp = self.query_one("#snapshots-panel", SnapshotsPanel)
            sp.select_next()
            self._update_diff_for_selected()

    def _nav_up(self) -> None:
        if self._active_panel == Panel.BRANCHES:
            bp = self.query_one("#branches-panel", BranchesPanel)
            bp.select_prev()
        elif self._active_panel == Panel.SNAPSHOTS:
            sp = self.query_one("#snapshots-panel", SnapshotsPanel)
            sp.select_prev()
            self._update_diff_for_selected()

    # ── Input mode handling ───────────────────────────────

    def _handle_input_key(self, key: str, event: Key) -> None:
        cl = self.query_one("#history-command", HistoryCommandLine)

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

        # Regular character input
        char = event.character
        if char and len(char) == 1 and ord(char) >= 32:
            self._input_text += char
            cl.text = self._input_text
            cl.cursor_pos = len(self._input_text)

    def _submit_input(self) -> None:
        cl = self.query_one("#history-command", HistoryCommandLine)
        text = self._input_text.strip()

        if self._input_mode == InputMode.COMMIT:
            if text:
                snap = self._vcs.commit(self._current_state, text)
                cl.show_message(f"Snapshot: {snap.description}")
                self._refresh_data()
                self._update_diff_for_selected()
            else:
                cl.show_message("Cancelled (empty description)")

        elif self._input_mode == InputMode.BRANCH:
            if text:
                branch = self._vcs.create_branch(text)
                if branch:
                    cl.show_message(f"Branch created: {text}")
                    self._refresh_data()
                else:
                    cl.show_message(f"Branch '{text}' already exists")
            else:
                cl.show_message("Cancelled (empty name)")

        elif self._input_mode == InputMode.TAG:
            if text:
                sp = self.query_one("#snapshots-panel", SnapshotsPanel)
                selected = sp.get_selected_snapshot()
                if selected:
                    self._vcs.tag(selected.id, text)
                    cl.show_message(f"Tagged: {text}")
                    self._refresh_data()
                    self._update_diff_for_selected()
            else:
                cl.show_message("Cancelled (empty tag)")

        elif self._input_mode == InputMode.CONFIRM_RESTORE:
            if text.lower() in ("y", "yes"):
                sp = self.query_one("#snapshots-panel", SnapshotsPanel)
                selected = sp.get_selected_snapshot()
                if selected and self._on_restore:
                    self._on_restore(selected.deck_state)
                    self.app.pop_screen()
                    return
            else:
                cl.show_message("Restore cancelled")

        self._input_mode = InputMode.NORMAL
        self._input_text = ""

    # ── Action starters ───────────────────────────────────

    def _start_commit(self) -> None:
        cl = self.query_one("#history-command", HistoryCommandLine)
        cl.show_prompt("Commit message: ")
        self._input_mode = InputMode.COMMIT
        self._input_text = ""

    def _start_branch(self) -> None:
        cl = self.query_one("#history-command", HistoryCommandLine)
        cl.show_prompt("Branch name: ")
        self._input_mode = InputMode.BRANCH
        self._input_text = ""

    def _start_tag(self) -> None:
        sp = self.query_one("#snapshots-panel", SnapshotsPanel)
        snap = sp.get_selected_snapshot()
        if snap is None:
            return
        cl = self.query_one("#history-command", HistoryCommandLine)
        cl.show_prompt(f"Tag for {snap.id[:7]}: ")
        self._input_mode = InputMode.TAG
        self._input_text = ""

    def _start_restore(self) -> None:
        sp = self.query_one("#snapshots-panel", SnapshotsPanel)
        snap = sp.get_selected_snapshot()
        if snap is None:
            return
        cl = self.query_one("#history-command", HistoryCommandLine)
        cl.show_prompt(f"Restore {snap.id[:7]}? (y/N): ")
        self._input_mode = InputMode.CONFIRM_RESTORE
        self._input_text = ""

    def _switch_branch(self) -> None:
        bp = self.query_one("#branches-panel", BranchesPanel)
        branch = bp.get_selected_branch()
        if branch is None:
            return
        state = self._vcs.switch_branch(branch.name)
        if state is not None:
            self._current_state = state
            cl = self.query_one("#history-command", HistoryCommandLine)
            cl.show_message(f"Switched to: {branch.name}")
            self._refresh_data()
            sp = self.query_one("#snapshots-panel", SnapshotsPanel)
            sp.selected = 0
            sp.scroll_pos = 0
            self._update_diff_for_selected()

    def _untag(self) -> None:
        sp = self.query_one("#snapshots-panel", SnapshotsPanel)
        snap = sp.get_selected_snapshot()
        if snap and snap.tag:
            self._vcs.untag(snap.id)
            cl = self.query_one("#history-command", HistoryCommandLine)
            cl.show_message(f"Removed tag: {snap.tag}")
            self._refresh_data()
            self._update_diff_for_selected()

    def _cherry_pick(self) -> None:
        sp = self.query_one("#snapshots-panel", SnapshotsPanel)
        snap = sp.get_selected_snapshot()
        if snap is None:
            return
        diff = self._vcs.cherry_pick(snap.id)
        cl = self.query_one("#history-command", HistoryCommandLine)
        if diff:
            cl.show_message(f"Cherry-picked: {snap.description}")
            self._refresh_data()
            self._update_diff_for_selected()
        else:
            cl.show_message("Cherry-pick failed")

    def _toggle_detail(self) -> None:
        dp = self.query_one("#diff-panel", DiffPanel)
        dp.show_unchanged = not dp.show_unchanged

    def _handle_enter(self) -> None:
        if self._active_panel == Panel.BRANCHES:
            self._switch_branch()
