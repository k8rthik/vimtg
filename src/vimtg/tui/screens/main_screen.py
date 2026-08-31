"""MainScreen — thin Textual wiring layer.

Connects KeyMap events to the pure key_handler functions,
then syncs updated EditorState to Textual widgets.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Key
from textual.screen import Screen

from vimtg.config.paths import cache_dir
from vimtg.config.settings import Settings
from vimtg.data.database import Database
from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.domain.card_types import primary_type
from vimtg.domain.formats import get_format_rules
from vimtg.editor.buffer import Buffer, LineType, insertion_zone
from vimtg.editor.command_completer import CommandCompleter
from vimtg.editor.commands import CommandRegistry
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult, ParsedAction
from vimtg.editor.keymaps import load_remapper
from vimtg.editor.layout import (
    LAYOUT_CATEGORY,
    detect_layout,
    enclosing_category,
)
from vimtg.editor.lint import (
    EMPTY_LINT,
    LintResult,
    effective_format,
    lint_buffer,
)
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.sections import (
    matched_indent,
    normalize_sections,
    type_section_insert_row,
)
from vimtg.editor.session import (
    EditorState,
    HandlerResult,
    InsertSubmode,
    count_cards,
    handle_command,
    handle_command_special,
    handle_comment_input_special,
    handle_insert_special,
    handle_line_edit_special,
    handle_mode_switch,
    handle_motion,
    handle_normal_special,
    handle_operator,
    handle_tag_input_special,
    resolve_cards,
)
from vimtg.editor.splits import EdhrecOpen, SplitDirection, SplitOpen
from vimtg.services.edhrec import EdhrecClient, EdhrecError, EdhrecPage
from vimtg.services.history_service import HistoryService
from vimtg.tui.key_translator import translate
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.command_line import GENERIC_HINT, CommandLine
from vimtg.tui.widgets.deck_view import DeckView
from vimtg.tui.widgets.edhrec_panel import EdhrecPanel
from vimtg.tui.widgets.help_panel import HelpPanel
from vimtg.tui.widgets.search_results import SearchResults
from vimtg.tui.widgets.status_line import StatusLine
from vimtg.tui.widgets.which_key import WhichKey

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository
    from vimtg.domain.deck_merge import CardKey
    from vimtg.services.search_service import SearchService
    from vimtg.services.vcs_service import (
        MergeResult,
        PendingMerge,
        VersionControlService,
    )


_GENERIC_HINT = GENERIC_HINT
_CARD_HINT = "+/- quantity  |  dd delete  |  yy yank  |  p paste  |  : command"

_NAMED_KEYS = frozenset({
    "escape", "enter", "tab", "backspace", "delete",
    "space", "up", "down", "left", "right", "home", "end",
})


def _is_named_key(key: str) -> bool:
    """A single named key ("escape", "ctrl_r") vs a multi-char sequence."""
    return key in _NAMED_KEYS or "_" in key


def _hint_for_cursor(buffer: Buffer, row: int) -> str:
    """Return the appropriate command-line hint for the current cursor position."""
    if buffer.is_card_line(row):
        return _CARD_HINT
    return _GENERIC_HINT


def _card_type_section(type_line: str) -> str:
    """Map a card's type_line to its singular section name."""
    return primary_type(type_line) or "Other"


_matched_indent = matched_indent


def _remapped_row(old_buf: Buffer, new_buf: Buffer, row: int) -> int:
    """Row of `old_buf[row]`'s line after normalization rewrote the buffer.

    Normalization inserts/removes blanks and drops empty headers but
    never edits or reorders the surviving lines, so the cursor line is
    refound by matching its text occurrence count. Falls back to the
    old row (clamped by the caller) for blank or dropped lines."""
    if row >= old_buf.line_count():
        return row
    text = old_buf.get_line(row).text
    if not text.strip():
        return row
    nth = sum(
        1 for i in range(row + 1) if old_buf.get_line(i).text == text
    )
    seen = 0
    for i in range(new_buf.line_count()):
        if new_buf.get_line(i).text == text:
            seen += 1
            if seen == nth:
                return i
    return row


@dataclass
class _SplitPane:
    """State of the split pane (second deck or EDHREC)."""

    kind: str  # "deck" | "edhrec"
    direction: SplitDirection
    focused: bool = False
    path: Path | None = None
    buffer: Buffer | None = None
    resolved: dict[str, Card] = field(default_factory=dict)
    cursor_row: int = 0


class MainScreen(Screen[None]):
    """Primary editor screen: deck view, status line, command line."""

    def __init__(
        self,
        buffer: Buffer,
        file_path: Path | None = None,
        registry: CommandRegistry | None = None,
        search_service: SearchService | None = None,
        card_repo: CardRepository | None = None,
        save_fn: Callable[[Path, str], None] | None = None,
        settings: Settings | None = None,
        db: Database | None = None,
    ) -> None:
        super().__init__()
        self._state = EditorState(
            buffer=buffer,
            cursor=Cursor(),
            mode_mgr=ModeManager(),
            registers=RegisterStore(),
            history=HistoryService(),
            modified=False,
            resolved_cards={},
            settings=settings or Settings(),
            card_repo=card_repo,
        )
        self._state.history.initialize(buffer)
        self.file_path = file_path
        self.registry = registry or CommandRegistry()
        self._state.cmd_completer = CommandCompleter(self.registry)
        self.search_service = search_service
        self.card_repo = card_repo
        self.save_fn = save_fn
        self.keymap = KeyMap()
        self.remapper = load_remapper()
        self._state.remapper = self.remapper
        self._db = db
        self._vcs_service: VersionControlService | None = None  # Lazily initialized
        self._replaying = False  # guards against recursive macro replay
        self._lint: LintResult = EMPTY_LINT
        # (buffer, resolved_cards, fmt) of the last lint — buffer and
        # resolved dict are compared by identity (both are replaced, never
        # mutated, on change), so cursor-only keys cost one comparison
        self._lint_key: tuple[Buffer, dict[str, Card], str] | None = None
        self._lint_resolved_names: frozenset[str] = frozenset()
        self._split_pane: _SplitPane | None = None
        # Bumped on every :edhrec so a stale fetch can't overwrite a
        # newer result (results deliver via call_from_thread)
        self._edhrec_generation = 0
        # Deck card names for the EDHREC ✓ marks, cached by buffer identity
        self._deck_names: frozenset[str] = frozenset()
        self._deck_names_key: Buffer | None = None

    def compose(self) -> ComposeResult:
        yield Container(
            DeckView(id="deck-view"),
            DeckView(id="deck-view-2"),
            EdhrecPanel(id="edhrec-panel"),
            id="editor-area",
        )
        yield SearchResults(id="search-results")
        yield HelpPanel(id="help-panel")
        yield WhichKey(id="which-key")
        yield StatusLine(id="status-line")
        yield CommandLine(id="command-line")

    def on_mount(self) -> None:
        # Start overlay panels hidden (Textual display=False = CSS display:none)
        self.query_one("#search-results", SearchResults).display = False
        self.query_one("#help-panel", HelpPanel).display = False
        self.query_one("#which-key", WhichKey).display = False
        self.query_one("#deck-view-2", DeckView).display = False
        self.query_one("#edhrec-panel", EdhrecPanel).display = False

        if self.card_repo:
            self._state.resolved_cards = resolve_cards(
                self._state.buffer, self.card_repo,
            )
        self._sync_widgets()

    # ── Key dispatch ─────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        # Let Ctrl+C through for emergency quit
        if event.key == "ctrl+c":
            return
        event.prevent_default()
        event.stop()

        # ── Help panel modal: block all keys except ? and Escape ──
        hp = self.query_one("#help-panel", HelpPanel)
        if hp.display:
            key = translate(event.key)
            if key in ("?", "escape"):
                hp.display = False
            return

        # F1 opens the full help screen from normal mode
        if event.key == "f1" and self._state.mode_mgr.is_normal():
            self._open_help(None)
            return

        # Clear transient messages from the previous keypress
        cl = self.query_one("#command-line", CommandLine)
        if cl.message:
            cl.message = ""
        # Translate Textual key name → canonical vim key name
        key = translate(event.key)
        self._process_key(key)

    def _process_key(self, key: str, resolve: bool = True) -> None:
        """Run one canonical key through remap, keymap, and dispatch.

        Shared by live keypresses, macro replay, and mapping expansion
        (expanded keys pass resolve=False so mappings don't re-resolve).
        """
        # Split pane focused: navigation keys drive the pane; ':' and
        # 'S' sequences pass through; any other key refocuses the editor
        # and is handled normally. Applies during macro replay too, so
        # replayed keys hit the same routing they were recorded under.
        if (
            resolve
            and self._split_pane is not None
            and self._split_pane.focused
            and self._state.mode_mgr.is_normal()
            and not self.keymap.awaiting_more_keys
        ):
            if self._handle_split_pane_key(key):
                self._sync_widgets()
                return
            if key not in (":", "S"):
                self._split_pane.focused = False
                self._sync_pane_focus()
        # A bare 'q' only stops recording in NORMAL mode with no pending
        # sequence — in INSERT/COMMAND modes (or mid-sequence) it is a
        # literal character and must be recorded like any other key.
        is_stop_q = (
            key == "q"
            and self._state.mode_mgr.is_normal()
            and not self.keymap.awaiting_more_keys
        )
        if (
            self._state.macros.is_recording
            and not self._replaying
            and resolve
            and not is_stop_q
        ):
            self._state.macros.record_key(key)
        if resolve:
            resolved = self.remapper.resolve(key, self._state.mode_mgr.current)
            if resolved != key and len(resolved) > 1 and not _is_named_key(resolved):
                # Multi-char mapping target (":w", "dd"): feed char by char.
                # An ex-command target is submitted with a trailing enter.
                for expanded in resolved:
                    self._process_key(expanded, resolve=False)
                if resolved.startswith(":"):
                    self._process_key("enter", resolve=False)
                return
            key = resolved
        result, action = self.keymap.feed(key)

        # Update which-key tooltip and status-line pending sequence (showcmd)
        wk = self.query_one("#which-key", WhichKey)
        sl = self.query_one("#status-line", StatusLine)
        sl.pending_keys = self.keymap.pending_display
        if result == KeyResult.PENDING:
            wk.pending_key = key
            wk.display = self._state.settings.show_which_key
            return
        wk.pending_key = ""
        wk.display = False

        if result != KeyResult.COMPLETE or action is None:
            return

        s = self._state
        hr = None
        if action.action_type == "motion":
            hr = handle_motion(s, action)
        elif action.action_type == "operator":
            hr = handle_operator(s, action)
        elif action.action_type == "mode_switch":
            hr = handle_mode_switch(s, action)
        elif action.action_type == "command_submit":
            prev_settings = s.settings
            hr = handle_command(s, action, self.registry, self.file_path, self.save_fn)
            if s.settings is not prev_settings:
                self._on_settings_saved(s.settings)
            s.mode_mgr.force_normal()
            self.keymap.set_mode(Mode.NORMAL)
        elif action.action_type == "special":
            hr = self._dispatch_special(action)

        self.keymap.set_macro_recording(s.macros.is_recording)
        if hr:
            self._apply_handler_result(hr)
        self._sync_widgets()

    def _replay_macro_keys(self, keys: tuple[str, ...]) -> None:
        """Replay recorded keys through the normal key pipeline.

        Replay is not re-entrant: an @ inside a macro is skipped rather
        than looping forever.
        """
        if self._replaying:
            return
        self._replaying = True
        try:
            for key in keys:
                self._process_key(key)
        finally:
            self._replaying = False

    def _dispatch_special(self, action: ParsedAction) -> HandlerResult | None:
        s = self._state
        if s.mode_mgr.is_insert():
            cl = self.query_one("#command-line", CommandLine)
            if s.insert_submode == InsertSubmode.TAG_INPUT:
                cl.text = action.text or ""
                cl.cursor_pos = action.cursor_pos if action.cursor_pos is not None else len(cl.text)
                hr = handle_tag_input_special(s, action)
                # Category input ghosts a completion; Tab accepts it
                if hr.command_accept:
                    cl.text = hr.command_accept
                    cl.cursor_pos = len(hr.command_accept)
                    self.keymap.set_insert_text(hr.command_accept)
                cl.ghost = hr.command_ghost
                return hr
            if s.insert_submode == InsertSubmode.COMMENT_INPUT:
                cl.text = action.text or ""
                cl.cursor_pos = action.cursor_pos if action.cursor_pos is not None else len(cl.text)
                return handle_comment_input_special(s, action)
            if s.insert_submode == InsertSubmode.LINE_EDIT:
                cl.text = action.text or ""
                cl.cursor_pos = action.cursor_pos if action.cursor_pos is not None else len(cl.text)
                hr = handle_line_edit_special(s, action)
                # The // Format: line ghost-completes known formats
                if hr.command_accept:
                    cl.text = hr.command_accept
                    cl.cursor_pos = len(hr.command_accept)
                    self.keymap.set_insert_text(hr.command_accept)
                cl.ghost = hr.command_ghost
                return hr
            cl.cursor_pos = (
                action.cursor_pos if action.cursor_pos is not None else len(action.text or "")
            )
            return handle_insert_special(s, action)
        if s.mode_mgr.is_command():
            cl = self.query_one("#command-line", CommandLine)
            cl.text = action.text or ""
            cl.cursor_pos = action.cursor_pos if action.cursor_pos is not None else len(cl.text)
            hr = handle_command_special(s, action)
            if hr.command_accept:
                cl.text = hr.command_accept
                cl.cursor_pos = len(hr.command_accept)
                self.keymap.set_command_text(hr.command_accept)
            cl.ghost = hr.command_ghost
            return None
        return handle_normal_special(s, action)

    def _apply_exit_to_normal(self) -> None:
        s = self._state
        # If cancelling a line edit (Escape), restore the original line.
        if (
            s.insert_submode == InsertSubmode.LINE_EDIT
            and s.line_edit_original is not None
            and s.line_edit_row is not None
            and s.line_edit_row < s.buffer.line_count()
        ):
            s.buffer = s.buffer.set_line(s.line_edit_row, s.line_edit_original)
        s.line_edit_original = None
        s.line_edit_row = None
        s.line_edit_prefix = ""
        s.tag_input_action = ""
        s.insert_submode = InsertSubmode.CARD_SEARCH
        s.mode_mgr.force_normal()
        self.keymap.set_mode(Mode.NORMAL)
        self.query_one("#search-results", SearchResults).display = False
        self.query_one("#help-panel", HelpPanel).display = False
        self.query_one("#command-line", CommandLine).hide()

    def _apply_enter_line_edit(self) -> None:
        s = self._state
        s.mode_mgr.transition(Mode.INSERT)
        self.keymap.set_mode(Mode.INSERT)
        prefix = s.line_edit_prefix
        row = s.line_edit_row if s.line_edit_row is not None else s.cursor.row
        full_text = s.buffer.get_line(row).text
        editable = full_text[len(prefix):]
        self.keymap.set_insert_text(editable)
        cl = self.query_one("#command-line", CommandLine)
        cl.show(prefix)
        cl.text = editable
        cl.cursor_pos = len(editable)
        cl.message = ""

    def _apply_enter_tag_input(self, tag_prompt: str) -> None:
        s = self._state
        s.insert_submode = InsertSubmode.TAG_INPUT
        s.mode_mgr.transition(Mode.INSERT)
        self.keymap.set_mode(Mode.INSERT)
        self.keymap.reset_text()
        cl = self.query_one("#command-line", CommandLine)
        cl.show(tag_prompt)
        cl.message = ""

    def _apply_enter_comment_input(self, prefill: str) -> None:
        s = self._state
        s.insert_submode = InsertSubmode.COMMENT_INPUT
        s.mode_mgr.transition(Mode.INSERT)
        self.keymap.set_mode(Mode.INSERT)
        # set_mode resets pending keys but not the text accumulator, so
        # the prefill survives for editing (same ordering as line edit)
        self.keymap.set_insert_text(prefill)
        cl = self.query_one("#command-line", CommandLine)
        cl.show("comment: ")
        cl.text = prefill
        cl.cursor_pos = len(prefill)
        cl.message = ""

    def _apply_enter_card_search(self) -> None:
        s = self._state
        s.insert_submode = InsertSubmode.CARD_SEARCH
        s.mode_mgr.transition(Mode.INSERT)
        self.keymap.set_mode(Mode.INSERT)
        self.keymap.reset_text()
        cl = self.query_one("#command-line", CommandLine)
        cl.show("")
        cl.message = "Type card name to search..."

    def _apply_handler_result(self, hr: HandlerResult) -> None:
        s = self._state
        if hr.exit_to_normal:
            self._apply_exit_to_normal()
        if hr.enter_line_edit:
            self._apply_enter_line_edit()
        if hr.enter_tag_input:
            self._apply_enter_tag_input(hr.tag_prompt)
        if hr.enter_comment_input:
            self._apply_enter_comment_input(hr.comment_prefill)
        if hr.enter_insert:
            self._apply_enter_card_search()
        if hr.enter_command:
            s.mode_mgr.transition(Mode.COMMAND)
            self.keymap.set_mode(Mode.COMMAND)
            self.keymap.reset_text()
            # A previous session's completion must not survive into a
            # fresh prompt — Tab would accept it over the current text
            s.cmd_completion = None
            cl = self.query_one("#command-line", CommandLine)
            cl.show(":")
            if hr.command_prefill:
                self.keymap.set_command_text(hr.command_prefill)
                cl.text = hr.command_prefill
                cl.cursor_pos = len(hr.command_prefill)
        if hr.enter_search:
            s.mode_mgr.transition(Mode.SEARCH)
            self.keymap.set_mode(Mode.SEARCH)
            self.keymap.reset_text()
            self.query_one("#command-line", CommandLine).show("/")
        if hr.enter_visual:
            s.mode_mgr.transition(hr.enter_visual)
            self.keymap.set_mode(hr.enter_visual)
        if hr.command_message:
            self.query_one("#command-line", CommandLine).set_message(
                hr.command_message, error=hr.error
            )
        if hr.file_path is not None:
            if self.file_path != hr.file_path:
                # Rebind VCS history to the new path (e.g. first :w of an
                # unsaved deck) instead of the stale "(unsaved)" bucket.
                self._vcs_service = None
            self.file_path = hr.file_path
        if hr.file_saved:
            # Only an actual save auto-snapshots — every ex command carries
            # file_path, and committing on each one would defeat the
            # uncommitted-changes guard on merge/rebase/switch.
            self._vcs_auto_snapshot()
        if hr.help_requested:
            hp = self.query_one("#help-panel", HelpPanel)
            hp.display = not hp.display
            self.query_one("#which-key", WhichKey).display = not hp.display
        if hr.greeter_requested:
            app = self.app
            self.app.pop_screen()
            show_greeter = getattr(app, "show_greeter", None)
            if callable(show_greeter):  # duck-typed navigation
                show_greeter()
            return
        if hr.quit_requested:
            self.app.exit()
        if hr.open_config_screen:
            self._open_config()
        if hr.open_history_screen:
            self._open_history()
        if hr.open_help_screen:
            self._open_help(hr.help_topic)
        if hr.vcs_commit_description:
            self._vcs_commit(hr.vcs_commit_description)
        if hr.vcs_checkpoint_name:
            self._vcs_checkpoint(hr.vcs_checkpoint_name)
        if hr.vcs_list_branches:
            self._vcs_list_branches()
        if hr.vcs_create_branch:
            self._vcs_create_branch(hr.vcs_create_branch)
        if hr.vcs_switch_branch:
            self._vcs_switch_branch(hr.vcs_switch_branch)
        if hr.vcs_merge_target:
            self._vcs_merge(hr.vcs_merge_target)
        if hr.vcs_rebase_target:
            self._vcs_rebase(hr.vcs_rebase_target)
        if hr.search_query is not None:
            self._handle_search_action(hr.search_query)
        if hr.replay_keys:
            self._replay_macro_keys(hr.replay_keys)
        if hr.insert_confirm:
            self._confirm_insert()
        if hr.split_close:
            self._close_split()
        if hr.split_open is not None:
            self._open_split_deck(hr.split_open)
        if hr.edhrec_open is not None:
            self._open_edhrec(hr.edhrec_open)
        if hr.focus_next_pane:
            self._toggle_pane_focus()
        if hr.run_ex_command:
            self._execute_ex(hr.run_ex_command)

    # ── Search and insert ────────────────────────────────────────

    def _handle_search_action(self, query: str) -> None:
        sr = self.query_one("#search-results", SearchResults)
        cl = self.query_one("#command-line", CommandLine)
        if query == "__next__":
            sr.select_next()
            selected = sr.get_selected()
            cl.ghost = selected.name if selected else ""
            return
        elif query == "__prev__":
            sr.select_prev()
            selected = sr.get_selected()
            cl.ghost = selected.name if selected else ""
            return
        else:
            cl.message = ""
            cl.text = query
            if len(query) >= 2 and self.search_service:
                self._run_search(query)
            elif len(query) < 2:
                sr.display = False

    def _write_zone_card(self, name: str, zone: LineType) -> None:
        """Replace the opened blank line with a card in `zone`'s style.

        Inside a zone block the line is written indented bare; among
        prefix-style entries it gets the SB:/CMD: prefix.
        """
        from vimtg.editor.operators import ZONE_PREFIXES

        s = self._state
        indent = _matched_indent(s.buffer, s.cursor.row)
        text = (
            f"{indent}1 {name}" if indent else f"{ZONE_PREFIXES[zone]}1 {name}"
        )
        s.buffer = s.buffer.set_line(s.cursor.row, text)

    def _delete_blank_cursor_line(self) -> bool:
        """Delete the cursor line if blank (the leftover from an 'o' insert).

        Returns True when a line was removed so callers can adjust offsets.
        """
        s = self._state
        if s.buffer.get_line(s.cursor.row).text.strip() == "":
            s.buffer, _ = s.buffer.delete_lines(s.cursor.row, s.cursor.row)
            return True
        return False

    def _confirm_insert(self) -> None:
        sr = self.query_one("#search-results", SearchResults)
        cl = self.query_one("#command-line", CommandLine)
        card = sr.get_selected()
        if card:
            s = self._state
            # The cursor's zone decides where the card goes: opening a
            # line inside the CMD:/SB: block (or among prefix lines of a
            # zone) adds the card to THAT zone
            zone = insertion_zone(s.buffer, s.cursor.row)
            # Check for duplicate — increment quantity instead of adding new line
            duplicate_line = self._find_card_line(card.name, zone)
            if duplicate_line is not None:
                qty = s.buffer.quantity_at(duplicate_line) or 0
                s.buffer = s.buffer.set_quantity(duplicate_line, qty + 1)
                if self._delete_blank_cursor_line() and duplicate_line > s.cursor.row:
                    duplicate_line -= 1
                s.cursor = s.cursor.move_to(min(duplicate_line, s.buffer.line_count() - 1), 0)
            elif zone != LineType.CARD_ENTRY:
                # Non-main zones aren't type-grouped: the card lands
                # exactly where opened, in the zone's own style
                self._write_zone_card(card.name, zone)
            elif not s.settings.auto_sort:
                # auto_sort off: card goes exactly where the user opened it
                indent = _matched_indent(s.buffer, s.cursor.row)
                s.buffer = s.buffer.set_line(s.cursor.row, f"{indent}1 {card.name}")
            elif detect_layout(s.buffer) == LAYOUT_CATEGORY:
                # Category layout: stay where opened, inherit the
                # enclosing '// @name' section's category
                indent = _matched_indent(s.buffer, s.cursor.row)
                s.buffer = s.buffer.set_line(s.cursor.row, f"{indent}1 {card.name}")
                category = enclosing_category(s.buffer, s.cursor.row)
                if category:
                    s.buffer = s.buffer.set_category(s.cursor.row, category)
            else:
                # Remove the blank line 'o' opened BEFORE the section
                # math — creating a header can shift rows past the
                # cursor, leaving a stale row for the blank's deletion
                self._delete_blank_cursor_line()
                s.buffer, insert_row = self._find_type_section_row(card, s.buffer)
                if insert_row is None:
                    insert_row = s.buffer.line_count()
                indent = _matched_indent(s.buffer, insert_row)
                s.buffer = s.buffer.insert_line(insert_row, f"{indent}1 {card.name}")
                s.cursor = s.cursor.move_to(insert_row, 0)
            s.modified = True
            s.history.record(s.buffer, f"added {card.name}")
            if self.card_repo:
                s.resolved_cards = resolve_cards(s.buffer, self.card_repo)
            from vimtg.editor.operators import ZONE_LABELS

            zone_note = (
                f" to {ZONE_LABELS[zone]}"
                if zone != LineType.CARD_ENTRY
                else ""
            )
            cl.set_message(
                f"Added {card.name}{zone_note}  (+/- to change qty, dd to remove)"
            )
        else:
            # No card selected — clean up blank line from 'o'
            s = self._state
            if self._delete_blank_cursor_line():
                s.cursor = s.cursor.clamp(s.buffer.line_count() - 1)
            cl.hide()
        sr.display = False
        self._state.mode_mgr.force_normal()
        self.keymap.set_mode(Mode.NORMAL)

    # ── Split panes and EDHREC ───────────────────────────────────

    def _execute_ex(self, text: str) -> None:
        """Run an ex command as if the user typed :text<Enter>."""
        s = self._state
        prev_settings = s.settings
        hr = handle_command(
            s, ParsedAction("command_submit", "enter", text=text),
            self.registry, self.file_path, self.save_fn,
        )
        if s.settings is not prev_settings:
            self._on_settings_saved(s.settings)
        s.mode_mgr.force_normal()
        self.keymap.set_mode(Mode.NORMAL)
        if hr:
            self._apply_handler_result(hr)

    def _split_pane_widget(self) -> DeckView | EdhrecPanel:
        if self._split_pane is not None and self._split_pane.kind == "edhrec":
            return self.query_one("#edhrec-panel", EdhrecPanel)
        return self.query_one("#deck-view-2", DeckView)

    def _apply_split_layout(self) -> None:
        """Show the split-pane widget in the requested direction."""
        comp = self._split_pane
        if comp is None:
            return
        area = self.query_one("#editor-area", Container)
        side_by_side = comp.direction is SplitDirection.VERTICAL
        area.styles.layout = "horizontal" if side_by_side else "vertical"
        show = self._split_pane_widget()
        for widget in (
            self.query_one("#deck-view-2", DeckView),
            self.query_one("#edhrec-panel", EdhrecPanel),
        ):
            widget.display = widget is show
        self._sync_pane_focus()

    def _sync_pane_focus(self) -> None:
        """Reflect which pane is active: separator color + panel state."""
        comp = self._split_pane
        if comp is None:
            return
        widget = self._split_pane_widget()
        color = COLORS["focus"] if comp.focused else COLORS["comment"]
        if comp.direction is SplitDirection.VERTICAL:
            widget.styles.border_left = ("solid", color)
            widget.styles.border_top = None
        else:
            widget.styles.border_top = ("solid", color)
            widget.styles.border_left = None
        panel = self.query_one("#edhrec-panel", EdhrecPanel)
        panel.focused_panel = comp.kind == "edhrec" and comp.focused

    def _open_split_deck(self, spec: SplitOpen) -> None:
        cl = self.query_one("#command-line", CommandLine)
        try:
            text = spec.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            cl.set_message(f"E: Cannot open {spec.path.name}: {exc}", error=True)
            return
        buf = Buffer.from_text(text)
        resolved = resolve_cards(buf, self.card_repo) if self.card_repo else {}
        self._split_pane = _SplitPane(
            kind="deck", direction=spec.direction,
            path=spec.path, buffer=buf, resolved=resolved,
        )
        self._apply_split_layout()
        cl.set_message(
            f"Split: {spec.path.name}  (Ss switch pane, :close to close)"
        )

    def _open_edhrec(self, req: EdhrecOpen) -> None:
        # Focus starts on the panel so j/k/h/l work immediately
        self._split_pane = _SplitPane(
            kind="edhrec", direction=req.direction, focused=True,
        )
        self._apply_split_layout()
        panel = self.query_one("#edhrec-panel", EdhrecPanel)
        panel.page = None
        panel.status_error = False
        if os.environ.get("VIMTG_NO_EDHREC"):
            panel.status = "EDHREC lookups disabled (VIMTG_NO_EDHREC)"
            return
        names = " + ".join(req.commanders)
        panel.status = f"Fetching EDHREC recommendations for {names}..."
        self._edhrec_generation += 1
        self._run_edhrec_fetch(
            req.commanders, req.initial_tab, self._edhrec_generation
        )

    @work(thread=True)
    def _run_edhrec_fetch(
        self, commanders: tuple[str, ...], initial_tab: str, generation: int
    ) -> None:
        client = EdhrecClient(cache_dir=cache_dir())
        try:
            page = client.fetch(commanders)
        except EdhrecError as exc:
            self.app.call_from_thread(self._edhrec_failed, str(exc), generation)
            return
        self.app.call_from_thread(
            self._edhrec_loaded, page, initial_tab, generation
        )

    def _edhrec_stale(self, generation: int) -> bool:
        """True when the pane closed or a newer :edhrec superseded this fetch."""
        return (
            self._split_pane is None
            or self._split_pane.kind != "edhrec"
            or generation != self._edhrec_generation
        )

    def _edhrec_failed(self, message: str, generation: int) -> None:
        if self._edhrec_stale(generation):
            return
        panel = self.query_one("#edhrec-panel", EdhrecPanel)
        panel.status = f"E: {message}"
        panel.status_error = True

    def _edhrec_loaded(
        self, page: EdhrecPage, initial_tab: str, generation: int
    ) -> None:
        if self._edhrec_stale(generation):
            return
        panel = self.query_one("#edhrec-panel", EdhrecPanel)
        panel.status = ""
        panel.page = page
        if initial_tab:
            panel.set_tab_by_label(initial_tab)
        self._sync_widgets()

    def _close_split(self) -> None:
        cl = self.query_one("#command-line", CommandLine)
        if self._split_pane is None:
            cl.set_message("E: No split open", error=True)
            return
        self._split_pane = None
        self.query_one("#deck-view-2", DeckView).display = False
        self.query_one("#edhrec-panel", EdhrecPanel).display = False

    def _toggle_pane_focus(self) -> None:
        cl = self.query_one("#command-line", CommandLine)
        if self._split_pane is None:
            cl.set_message("E: No split open (Sv/Sh or :vsplit)", error=True)
            return
        self._split_pane.focused = not self._split_pane.focused
        self._sync_pane_focus()

    def _handle_split_pane_key(self, key: str) -> bool:
        """Drive the focused split pane; True when the key was consumed."""
        comp = self._split_pane
        assert comp is not None
        if key == "escape":
            comp.focused = False
            self._sync_pane_focus()
            return True
        if comp.kind == "deck":
            return self._split_deck_key(comp, key)
        return self._split_edhrec_key(key)

    def _split_deck_key(self, comp: _SplitPane, key: str) -> bool:
        if comp.buffer is None:
            return False
        last = comp.buffer.line_count() - 1
        page = max(1, self.query_one("#deck-view-2", DeckView).size.height // 2)
        if key in ("j", "down"):
            comp.cursor_row = min(comp.cursor_row + 1, last)
        elif key in ("k", "up"):
            comp.cursor_row = max(comp.cursor_row - 1, 0)
        elif key == "ctrl_d":
            comp.cursor_row = min(comp.cursor_row + page, last)
        elif key == "ctrl_u":
            comp.cursor_row = max(comp.cursor_row - page, 0)
        elif key in ("g", "home"):
            comp.cursor_row = 0
        elif key in ("G", "end"):
            comp.cursor_row = last
        else:
            return False
        return True

    def _split_edhrec_key(self, key: str) -> bool:
        panel = self.query_one("#edhrec-panel", EdhrecPanel)
        if key in ("j", "down"):
            panel.select_next()
        elif key in ("k", "up"):
            panel.select_prev()
        elif key in ("l", "right", "tab"):
            panel.next_tab()
        elif key in ("h", "left", "shift_tab"):
            panel.prev_tab()
        elif key == "enter":
            self._insert_from_edhrec()
        else:
            return False
        return True

    def _insert_from_edhrec(self) -> None:
        """Add the selected recommendation to the deck (Enter in the panel)."""
        panel = self.query_one("#edhrec-panel", EdhrecPanel)
        cl = self.query_one("#command-line", CommandLine)
        rec = panel.get_selected()
        if rec is None:
            return
        s = self._state
        existing = self._find_card_line(rec.name)
        if existing is not None:
            qty = s.buffer.quantity_at(existing) or 0
            s.buffer = s.buffer.set_quantity(existing, qty + 1)
            row = existing
        else:
            card = self.card_repo.get_by_name(rec.name) if self.card_repo else None
            if card is not None:
                s.buffer, insert_row = self._find_type_section_row(card, s.buffer)
                if insert_row is None:
                    insert_row = s.buffer.line_count()
            else:
                insert_row = s.buffer.line_count()
            indent = _matched_indent(s.buffer, insert_row)
            s.buffer = s.buffer.insert_line(insert_row, f"{indent}1 {rec.name}")
            row = insert_row
            if self.card_repo:
                s.resolved_cards = resolve_cards(s.buffer, self.card_repo)
        s.cursor = s.cursor.move_to(min(row, s.buffer.line_count() - 1), 0)
        s.modified = True
        s.history.record(s.buffer, f"added {rec.name} (EDHREC)")
        cl.set_message(f"Added {rec.name}")

    def attach_card_repo(
        self, card_repo: CardRepository, search_service: SearchService,
    ) -> None:
        """Adopt a card repository that became available after mount.

        Called when a background auto-sync finishes on a screen that
        started without card data: wires search, re-resolves the
        buffer's cards, and forces a lint recompute.
        """
        self.card_repo = card_repo
        self.search_service = search_service
        s = self._state
        s.card_repo = card_repo
        s.resolved_cards = resolve_cards(s.buffer, card_repo)
        self._lint_key = None
        self._lint_resolved_names = frozenset()
        self._sync_widgets()

    def _open_help(self, topic: str | None) -> None:
        from vimtg.tui.screens.help_screen import HelpScreen

        self.app.push_screen(HelpScreen(topic=topic))

    def _open_config(self) -> None:
        from vimtg.tui.screens.config_screen import ConfigScreen

        self.app.push_screen(ConfigScreen(
            settings=self._state.settings,
            on_save=self._on_settings_saved,
        ))

    def _on_settings_saved(self, new_settings: Settings) -> None:
        self._state.settings = new_settings
        from vimtg.tui.app import VimTGApp
        app = self.app
        if isinstance(app, VimTGApp):
            app.update_settings(new_settings)
        self._sync_widgets()
        self.query_one("#command-line", CommandLine).set_message("Settings saved")

    # ── VCS integration ─────────────────────────────────────

    def _get_vcs_service(self) -> VersionControlService | None:
        """Lazily initialize VCS service on first use."""
        if self._vcs_service is not None:
            return self._vcs_service
        if self._db is None:
            return None
        from vimtg.data.snapshot_repository import SnapshotRepository
        from vimtg.services.vcs_service import VersionControlService
        deck_path = str(self.file_path.resolve()) if self.file_path else "(unsaved)"
        repo = SnapshotRepository(self._db)
        self._vcs_service = VersionControlService(repo, deck_path)
        return self._vcs_service

    def _open_history(self) -> None:
        from vimtg.services.deck_diff_service import DeckDiffService
        from vimtg.tui.screens.history_screen import HistoryScreen
        vcs = self._get_vcs_service()
        if vcs is None:
            cl = self.query_one("#command-line", CommandLine)
            cl.set_message("VCS unavailable (no database)")
            return
        diff_svc = DeckDiffService(card_repo=self.card_repo)
        self.app.push_screen(HistoryScreen(
            vcs_service=vcs,
            diff_service=diff_svc,
            current_deck_state=self._state.buffer.to_text(),
            deck_name=self.file_path.name if self.file_path else "(new)",
            on_restore=self._on_restore,
        ))

    def _on_restore(self, deck_state: str) -> None:
        """Callback from HistoryScreen when user restores a snapshot."""
        self._state.buffer = Buffer.from_text(deck_state)
        self._state.cursor = Cursor()
        self._state.modified = True
        self._state.history.record(self._state.buffer, "restore from VCS")
        if self.card_repo:
            self._state.resolved_cards = resolve_cards(
                self._state.buffer, self.card_repo,
            )
        self._sync_widgets()

    def _vcs_commit(self, description: str) -> None:
        """Create a VCS snapshot with the given description."""
        vcs = self._get_vcs_service()
        cl = self.query_one("#command-line", CommandLine)
        if vcs is None:
            cl.set_message("VCS unavailable (no database)")
            return
        try:
            snap = vcs.commit(self._state.buffer.to_text(), description)
        except sqlite3.Error as exc:
            cl.set_message(f"E: Snapshot failed: {exc}", error=True)
            return
        cl.set_message(f"Snapshot: {snap.description}")
        self._sync_widgets()

    def _vcs_checkpoint(self, name: str) -> None:
        """Commit the current deck state and tag the snapshot with name."""
        vcs = self._get_vcs_service()
        cl = self.query_one("#command-line", CommandLine)
        if vcs is None:
            cl.set_message("VCS unavailable (no database)")
            return
        try:
            snap = vcs.commit(self._state.buffer.to_text(), name)
            vcs.tag(snap.id, name)
        except sqlite3.Error as exc:
            cl.set_message(f"E: Checkpoint failed: {exc}", error=True)
            return
        cl.set_message(f"Checkpoint: {name}")
        self._sync_widgets()

    def _vcs_list_branches(self) -> None:
        """Show all branches on the command line, marking the current one."""
        vcs = self._get_vcs_service()
        cl = self.query_one("#command-line", CommandLine)
        if vcs is None:
            cl.set_message("VCS unavailable (no database)")
            return
        try:
            branches = vcs.list_branches()
        except sqlite3.Error as exc:
            cl.set_message(f"E: Branch list failed: {exc}", error=True)
            return
        if not branches:
            cl.set_message("Branches: (none — nothing committed yet)")
            return
        names = [
            f"*{b.name}" if b.name == vcs.current_branch else b.name
            for b in branches
        ]
        cl.set_message("Branches: " + ", ".join(names))

    def _vcs_create_branch(self, name: str) -> None:
        """Create a branch at the current branch tip."""
        vcs = self._get_vcs_service()
        cl = self.query_one("#command-line", CommandLine)
        if vcs is None:
            cl.set_message("VCS unavailable (no database)")
            return
        try:
            existing = {b.name for b in vcs.list_branches()}
            if name in existing:
                cl.set_message(f"E: Branch exists: {name}", error=True)
                return
            branch = vcs.create_branch(name)
        except sqlite3.Error as exc:
            cl.set_message(f"E: Branch failed: {exc}", error=True)
            return
        if branch is None:
            cl.set_message("E: Nothing committed yet — :commit first", error=True)
            return
        cl.set_message(f"Branch created: {name}")

    def _vcs_switch_branch(self, name: str) -> None:
        """Switch to a branch and load its tip into the buffer."""
        vcs = self._get_vcs_service()
        cl = self.query_one("#command-line", CommandLine)
        if vcs is None:
            cl.set_message("VCS unavailable (no database)")
            return
        try:
            if vcs.is_dirty(self._state.buffer.to_text()):
                cl.set_message(
                    "E: Uncommitted changes — :commit first", error=True
                )
                return
            state = vcs.switch_branch(name)
        except sqlite3.Error as exc:
            cl.set_message(f"E: Switch failed: {exc}", error=True)
            return
        if state is None:
            cl.set_message(f"E: Branch not found: {name}", error=True)
            return
        self._on_restore(state)
        cl.set_message(f"Switched to branch: {name}")

    def _vcs_merge(self, target: str) -> None:
        """Merge a branch, or another deck file, into the current branch.

        Disambiguation: an exact branch-name match wins; otherwise an
        argument containing a path separator or ending in .deck is treated
        as a deck file. Anything else is an error.
        """
        vcs = self._get_vcs_service()
        cl = self.query_one("#command-line", CommandLine)
        if vcs is None:
            cl.set_message("VCS unavailable (no database)")
            return
        if self.file_path is None:
            cl.set_message("E: Save the deck before merging (:w)", error=True)
            return
        try:
            if vcs.is_dirty(self._state.buffer.to_text()):
                cl.set_message(
                    "E: Uncommitted changes — :commit first", error=True
                )
                return
            branch_names = {b.name for b in vcs.list_branches()}
            result: MergeResult | None
            if target in branch_names:
                result = vcs.merge_branch(target)
            elif "/" in target or "\\" in target or target.endswith(".deck"):
                result = self._merge_deck_file(target)
            else:
                cl.set_message(
                    f"E: No branch or deck file: {target}", error=True
                )
                return
        except sqlite3.Error as exc:
            cl.set_message(f"E: Merge failed: {exc}", error=True)
            return
        if result is not None:
            self._handle_merge_result(result)

    def _merge_deck_file(self, arg: str) -> MergeResult | None:
        """Read another deck file and merge its cards (empty merge base)."""
        cl = self.query_one("#command-line", CommandLine)
        vcs = self._vcs_service
        if vcs is None:
            return None

        path = Path(arg).expanduser()
        if not path.is_absolute():
            base_dir = (
                self.file_path.parent if self.file_path else Path.cwd()
            )
            for candidate in (base_dir / path, Path.cwd() / path):
                if candidate.exists():
                    path = candidate
                    break
        if self.file_path and path.resolve() == self.file_path.resolve():
            cl.set_message("E: Cannot merge a deck into itself", error=True)
            return None
        try:
            theirs_state = path.read_text(encoding="utf-8")
        except OSError as exc:
            cl.set_message(f"E: Cannot read {arg}: {exc}", error=True)
            return None
        return vcs.merge_external(theirs_state, path.name)

    def _handle_merge_result(self, result: MergeResult) -> None:
        """Apply a merge outcome: adopt state, or open conflict resolution."""
        from vimtg.services.vcs_service import MergeKind
        from vimtg.tui.screens.merge_screen import MergeScreen

        cl = self.query_one("#command-line", CommandLine)
        if result.kind is MergeKind.CONFLICTS and result.pending is not None:
            pending = result.pending
            deck_name = self.file_path.name if self.file_path else "(new)"
            self.app.push_screen(MergeScreen(
                pending=pending,
                deck_name=deck_name,
                on_complete=lambda res: self._finish_merge(pending, res),
            ))
            return
        if result.new_state is not None:
            self._on_restore(result.new_state)
        cl.set_message(
            ("E: " if result.kind is MergeKind.FAILED else "")
            + result.message,
            error=result.kind is MergeKind.FAILED,
        )

    def _finish_merge(
        self,
        pending: PendingMerge,
        resolutions: dict[CardKey, int | None],
    ) -> None:
        """Complete a conflicted merge with the user's resolutions."""
        vcs = self._vcs_service
        cl = self.query_one("#command-line", CommandLine)
        if vcs is None:
            return
        try:
            result = vcs.complete_merge(pending, resolutions)
        except sqlite3.Error as exc:
            cl.set_message(f"E: Merge failed: {exc}", error=True)
            return
        self._handle_merge_result(result)

    def _vcs_rebase(self, target: str) -> None:
        """Replay the current branch's commits onto the target branch tip."""
        from vimtg.services.vcs_service import MergeKind

        vcs = self._get_vcs_service()
        cl = self.query_one("#command-line", CommandLine)
        if vcs is None:
            cl.set_message("VCS unavailable (no database)")
            return
        if self.file_path is None:
            cl.set_message("E: Save the deck before rebasing (:w)", error=True)
            return
        try:
            if vcs.is_dirty(self._state.buffer.to_text()):
                cl.set_message(
                    "E: Uncommitted changes — :commit first", error=True
                )
                return
            result = vcs.rebase(target)
        except sqlite3.Error as exc:
            cl.set_message(f"E: Rebase failed: {exc}", error=True)
            return
        if result.new_state is not None:
            self._on_restore(result.new_state)
        cl.set_message(
            ("E: " if result.kind is MergeKind.FAILED else "")
            + result.message,
            error=result.kind is MergeKind.FAILED,
        )

    def _vcs_auto_snapshot(self) -> None:
        """Auto-create VCS snapshot on :w (if enabled).

        A snapshot failure must never take down the app on :w — the
        file write already succeeded; report the error instead.
        """
        if not self._state.settings.auto_snapshot:
            return
        vcs = self._get_vcs_service()
        if vcs is None:
            return
        try:
            vcs.commit(self._state.buffer.to_text(), "auto: save")
        except sqlite3.Error as exc:
            cl = self.query_one("#command-line", CommandLine)
            cl.set_message(f"E: Auto-snapshot failed: {exc}", error=True)

    def _find_card_line(
        self, card_name: str, zone: LineType | None = None
    ) -> int | None:
        """Find an existing line with this card name in `zone`.

        Duplicate detection is zone-scoped: adding a card where the
        cursor is must increment a copy in THAT zone, never one in
        another zone. Defaults to the mainboard.
        """
        target = zone if zone is not None else LineType.CARD_ENTRY
        buf = self._state.buffer
        for i in range(buf.line_count()):
            if (
                buf.get_line(i).line_type == target
                and buf.card_name_at(i) == card_name
            ):
                return i
        return None

    def _find_type_section_row(self, card: Card, buf: Buffer) -> tuple[Buffer, int | None]:
        """Find the right row to insert a card based on its primary type.

        Uses singular type names: "Creature", "Instant", "Sorcery", etc.
        Returns (buffer, insert_row) — buffer may have new section header lines.
        """
        return type_section_insert_row(buf, _card_type_section(card.type_line))

    @work(thread=True)
    def _run_search(self, query: str) -> None:
        if self.search_service:
            settings = self._state.settings
            results = self.search_service.search(
                query, limit=settings.search_limit
            )
            # Same format resolution as lint: the deck's declared
            # "// Format:" wins over the global default. Only filter on
            # formats we actually know — an unknown or misspelled format
            # must not silently empty the results.
            deck = parse_deck_text(self._state.buffer.to_text())
            fmt = effective_format(deck, settings.default_format)
            if fmt and get_format_rules(fmt) is not None:
                # Restricted cards are playable (1 copy) — hiding them
                # from search would make vintage staples unfindable
                results = [
                    c for c in results
                    if c.legalities.get(fmt) in ("legal", "restricted")
                ]
            self.app.call_from_thread(self._update_search_results, results)

    def _update_search_results(self, results: list[Card]) -> None:
        sr = self.query_one("#search-results", SearchResults)
        sr.results = results
        sr.selected = 0
        sr.display = bool(results)
        # Show top match as ghost completion in command line
        cl = self.query_one("#command-line", CommandLine)
        if results:
            cl.ghost = results[0].name
        else:
            cl.ghost = ""

    # ── Widget sync ──────────────────────────────────────────────

    def _cleanup_empty_sections(self) -> None:
        """Normalize sections, folding any change into the last undo step.

        No-op (and no state churn) when the buffer is already clean, so
        pure cursor motion never rewrites the document.
        """
        s = self._state
        cleaned = normalize_sections(s.buffer)
        if cleaned is s.buffer:
            return
        new_row = _remapped_row(s.buffer, cleaned, s.cursor.row)
        s.buffer = cleaned
        s.cursor = s.cursor.move_to(new_row).clamp(cleaned.line_count() - 1)
        s.modified = True
        s.history.amend(cleaned)

    def _update_lint(self) -> None:
        """Recompute validation for the deck view gutter when inputs change.

        Cheap on cursor-only keys (identity compare); re-parses on buffer
        change; hits the card DB only when the set of card names changes.
        """
        s = self._state
        fmt = s.settings.default_format
        key = self._lint_key
        if (
            key is not None
            and key[0] is s.buffer
            and key[1] is s.resolved_cards
            and key[2] == fmt
        ):
            return
        deck = parse_deck_text(s.buffer.to_text())
        names = frozenset(n.lower() for n in deck.unique_card_names())
        if names != self._lint_resolved_names and self.card_repo is not None:
            s.resolved_cards = resolve_cards(s.buffer, self.card_repo)
            self._lint_resolved_names = names
        self._lint = lint_buffer(s.buffer, s.resolved_cards, fmt, deck=deck)
        self._lint_key = (s.buffer, s.resolved_cards, fmt)

    def _sync_widgets(self) -> None:
        # Only clean up sections in NORMAL mode — INSERT/VISUAL have transient blanks
        if self._state.mode_mgr.is_normal():
            self._cleanup_empty_sections()
        self._update_lint()

        s = self._state
        from vimtg.editor.config_options import currency_symbol_for

        price_src = s.settings.price_source
        cur_sym = currency_symbol_for(price_src)

        dv = self.query_one("#deck-view", DeckView)
        dv.buffer = s.buffer
        dv.cursor = s.cursor
        dv.resolved_cards = s.resolved_cards
        dv.price_source = price_src
        dv.currency_symbol = cur_sym
        dv.show_prices = s.settings.show_prices
        dv.show_line_numbers = s.settings.show_line_numbers
        dv.auto_expand = s.settings.auto_expand
        dv.tag_filter = s.tag_filter
        dv.line_errors = self._lint.line_errors

        comp = self._split_pane
        if comp is not None:
            if comp.kind == "deck" and comp.buffer is not None:
                dv2 = self.query_one("#deck-view-2", DeckView)
                dv2.buffer = comp.buffer
                dv2.cursor = Cursor(row=comp.cursor_row)
                dv2.resolved_cards = comp.resolved
                dv2.price_source = price_src
                dv2.currency_symbol = cur_sym
                dv2.show_prices = s.settings.show_prices
                dv2.show_line_numbers = s.settings.show_line_numbers
                dv2.auto_expand = s.settings.auto_expand
            elif comp.kind == "edhrec":
                if self._deck_names_key is not s.buffer:
                    self._deck_names = frozenset(
                        name.lower()
                        for i in range(s.buffer.line_count())
                        if (name := s.buffer.card_name_at(i))
                    )
                    self._deck_names_key = s.buffer
                panel = self.query_one("#edhrec-panel", EdhrecPanel)
                panel.deck_names = self._deck_names

        sr = self.query_one("#search-results", SearchResults)
        sr.price_source = price_src
        sr.currency_symbol = cur_sym
        sr.show_prices = s.settings.show_prices

        sl = self.query_one("#status-line", StatusLine)
        sl.mode = s.mode_mgr.current
        sl.filename = self.file_path.name if self.file_path else "(new)"
        sl.modified = s.modified
        sl.card_count = count_cards(s.buffer)
        sl.cursor_line = s.cursor.row
        sl.total_lines = s.buffer.line_count()
        sl.recording_register = s.macros.recording_register or ""
        sl.pending_keys = self.keymap.pending_display
        sl.lint_error_count = self._lint.error_count
        sl.lint_warning_count = self._lint.warning_count
        cursor_err = self._lint.line_errors.get(s.cursor.row)
        sl.cursor_lint = cursor_err.message if cursor_err else ""
        sl.cursor_lint_level = cursor_err.level if cursor_err else ""

        # VCS status — a DB hiccup here must not crash the render path
        vcs = self._vcs_service  # Don't lazily init on every sync
        if vcs is not None:
            try:
                status = vcs.status(s.buffer.to_text())
            except sqlite3.Error:
                pass
            else:
                sl.vcs_branch = status.branch
                sl.vcs_snapshot_count = status.snapshot_count

        cl = self.query_one("#command-line", CommandLine)
        if s.mode_mgr.is_normal():
            cl.hint = _hint_for_cursor(s.buffer, s.cursor.row)
        else:
            cl.hint = ""
