"""MergeScreen — interactive per-card conflict resolution for merges.

Pushed when a merge returns conflicts. Nothing is committed while this
screen is open: all state lives in the frozen PendingMerge, so aborting
requires no cleanup. Confirming hands the resolutions to on_complete.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from rich.text import Text
from textual.app import ComposeResult
from textual.events import Key
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Static

from vimtg.domain.deck_merge import CardKey
from vimtg.services.vcs_service import PendingMerge
from vimtg.tui.key_translator import translate
from vimtg.tui.keys import CLOSE_KEYS, FULL_HELP_KEY, HELP_KEY, PENDING, VimNav, render_hints
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.conflicts_panel import ConflictsPanel

# Action keys and the shared navigation vocabulary; the hint bar and the
# test in tests/tui/test_merge_screen.py both read this table.
HINTS = (
    ("q/Esc", "abort"), ("j/k", "nav"), ("o", "ours"), ("t", "theirs"),
    ("c", "custom"), ("u", "unresolve"), ("Enter", "confirm"), ("?", "help"),
)
ACTIONS: dict[str, str] = {
    "o": "_pick_ours", "t": "_pick_theirs", "c": "_start_custom_qty",
    "u": "_unresolve_selected", "enter": "_confirm",
}


class MergeInputMode(Enum):
    NORMAL = "normal"
    CUSTOM_QTY = "custom_qty"


class MergeCommandLine(Static):
    """Bottom command line for the merge screen: hints, prompt, messages."""

    prompt: reactive[str] = reactive("")
    text: reactive[str] = reactive("")
    message: reactive[str] = reactive("")

    def render(self) -> Text:
        t = Text()
        if self.message:
            t.append(f" {self.message}", style=f"bold {COLORS['mana_green']}")
            return t
        if self.prompt:
            t.append(f" {self.prompt}", style=f"bold {COLORS['mode_command']}")
            t.append(self.text, style="bold")
            t.append(" ", style="bold reverse")
            return t
        return render_hints(HINTS, self.size.width)

    def show_prompt(self, prompt: str) -> None:
        self.prompt = prompt
        self.text = ""
        self.message = ""

    def show_message(self, msg: str) -> None:
        self.message = msg
        self.prompt = ""
        self.text = ""

    def hide(self) -> None:
        self.prompt = ""
        self.text = ""
        self.message = ""


class MergeHeader(Static):
    """Title bar naming the merge source and conflict count."""

    source_label: reactive[str] = reactive("")
    deck_name: reactive[str] = reactive("")
    conflict_count: reactive[int] = reactive(0)

    def render(self) -> Text:
        t = Text()
        t.append(" MERGE ", style=f"bold {COLORS['mode_command']} on {COLORS['bg']}")
        t.append(f" {self.deck_name}", style="bold")
        t.append(f"  ← {self.source_label}", style=f"bold {COLORS['mana_blue']}")
        t.append(
            f"  {self.conflict_count} conflict(s)",
            style=f"bold {COLORS['sideboard']}",
        )
        return t


class MergeScreen(Screen[None]):
    """Interactive conflict resolution: pick ours/theirs/custom per card."""

    CSS = f"""
    #merge-header {{
        height: 1;
        dock: top;
        background: {COLORS['bg']};
    }}
    #conflicts-panel {{
        height: 1fr;
    }}
    #merge-command {{
        height: 1;
        dock: bottom;
        background: {COLORS['bg']};
    }}
    """

    def __init__(
        self,
        pending: PendingMerge,
        deck_name: str,
        on_complete: Callable[[dict[CardKey, int | None]], None],
        on_abort: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._pending = pending
        self._deck_name = deck_name
        self._on_complete = on_complete
        self._on_abort = on_abort
        self._nav = VimNav()
        self._resolutions: dict[CardKey, int | None] = {}
        self._input_mode = MergeInputMode.NORMAL
        self._input_text = ""

    def compose(self) -> ComposeResult:
        yield MergeHeader(id="merge-header")
        yield ConflictsPanel(id="conflicts-panel")
        yield MergeCommandLine(id="merge-command")

    def on_mount(self) -> None:
        header = self.query_one("#merge-header", MergeHeader)
        header.source_label = self._pending.source_label
        header.deck_name = self._deck_name
        header.conflict_count = len(self._pending.conflicts)

        cp = self.query_one("#conflicts-panel", ConflictsPanel)
        cp.conflicts = self._pending.conflicts

    # ── Key dispatch ──────────────────────────────────────

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+c":
            return
        event.prevent_default()
        event.stop()
        key = translate(event.key)

        if self._input_mode is MergeInputMode.CUSTOM_QTY:
            self._handle_qty_key(key, event)
            return

        cl = self.query_one("#merge-command", MergeCommandLine)
        if cl.message:
            cl.hide()

        cp = self.query_one("#conflicts-panel", ConflictsPanel)
        step = self._nav.feed(key, max(1, len(cp.conflicts)))
        if step == PENDING:
            return
        if step == "home":
            cp.select_first()
        elif step == "end":
            cp.select_last()
        elif step is not None:
            cp.select_by(int(step))
        elif key in CLOSE_KEYS:
            self._abort()
        elif key in (HELP_KEY, FULL_HELP_KEY):
            from vimtg.tui.screens.help_screen import HelpScreen

            self.app.push_screen(HelpScreen(topic="merge" if key == HELP_KEY else None))
        elif (method := ACTIONS.get(key)) is not None:
            getattr(self, method)()

    def _pick_ours(self) -> None:
        self._resolve_selected(lambda c: c.ours_quantity)

    def _pick_theirs(self) -> None:
        self._resolve_selected(lambda c: c.theirs_quantity)

    # ── Resolution actions ────────────────────────────────

    def _resolve_selected(self, pick: Callable[..., int | None]) -> None:
        cp = self.query_one("#conflicts-panel", ConflictsPanel)
        conflict = cp.get_selected_conflict()
        if conflict is None:
            return
        quantity = pick(conflict)
        # A zero/None side means the card is omitted from the result
        self._resolutions[conflict.key] = quantity if quantity else None
        cp.resolutions = dict(self._resolutions)
        cp.select_next()

    def _unresolve_selected(self) -> None:
        cp = self.query_one("#conflicts-panel", ConflictsPanel)
        conflict = cp.get_selected_conflict()
        if conflict is None or conflict.key not in self._resolutions:
            return
        del self._resolutions[conflict.key]
        cp.resolutions = dict(self._resolutions)

    def _start_custom_qty(self) -> None:
        cp = self.query_one("#conflicts-panel", ConflictsPanel)
        conflict = cp.get_selected_conflict()
        if conflict is None:
            return
        cl = self.query_one("#merge-command", MergeCommandLine)
        cl.show_prompt(f"Quantity for {conflict.card_name} (0 omits): ")
        self._input_mode = MergeInputMode.CUSTOM_QTY
        self._input_text = ""

    def _handle_qty_key(self, key: str, event: Key) -> None:
        cl = self.query_one("#merge-command", MergeCommandLine)
        if key == "escape":
            self._input_mode = MergeInputMode.NORMAL
            self._input_text = ""
            cl.hide()
            return
        if key == "enter":
            self._submit_custom_qty()
            return
        if key == "backspace":
            self._input_text = self._input_text[:-1]
            cl.text = self._input_text
            return
        char = event.character
        if char and char.isdigit():
            self._input_text += char
            cl.text = self._input_text

    def _submit_custom_qty(self) -> None:
        cl = self.query_one("#merge-command", MergeCommandLine)
        cp = self.query_one("#conflicts-panel", ConflictsPanel)
        conflict = cp.get_selected_conflict()
        text = self._input_text.strip()
        self._input_mode = MergeInputMode.NORMAL
        self._input_text = ""

        if conflict is None or not text:
            cl.hide()
            return
        quantity = int(text)
        self._resolutions[conflict.key] = quantity if quantity > 0 else None
        cp.resolutions = dict(self._resolutions)
        cl.hide()
        cp.select_next()

    # ── Confirm / abort ───────────────────────────────────

    def _confirm(self) -> None:
        unresolved = [
            c for c in self._pending.conflicts
            if c.key not in self._resolutions
        ]
        if unresolved:
            cl = self.query_one("#merge-command", MergeCommandLine)
            cl.show_message(f"{len(unresolved)} conflict(s) unresolved")
            return
        self.app.pop_screen()
        self._on_complete(dict(self._resolutions))

    def _abort(self) -> None:
        self.app.pop_screen()
        if self._on_abort is not None:
            self._on_abort()
