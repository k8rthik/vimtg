"""MainScreen — thin Textual wiring layer.

Connects KeyMap events to the pure key_handler functions,
then syncs updated EditorState to Textual widgets.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.events import Key
from textual.screen import Screen

from vimtg.config.settings import Settings
from vimtg.data.database import Database
from vimtg.domain.card import Card
from vimtg.domain.card_types import primary_type
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_completer import CommandCompleter
from vimtg.editor.commands import CommandRegistry
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult, ParsedAction
from vimtg.editor.keymaps import load_remapper
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.sections import normalize_sections
from vimtg.services.history_service import HistoryService
from vimtg.tui.key_translator import translate
from vimtg.tui.screens.key_handler import (
    EditorState,
    HandlerResult,
    InsertSubmode,
    count_cards,
    handle_command,
    handle_command_special,
    handle_insert_special,
    handle_line_edit_special,
    handle_mode_switch,
    handle_motion,
    handle_normal_special,
    handle_operator,
    handle_tag_input_special,
    resolve_cards,
)
from vimtg.tui.widgets.command_line import GENERIC_HINT, CommandLine
from vimtg.tui.widgets.deck_view import DeckView
from vimtg.tui.widgets.help_panel import HelpPanel
from vimtg.tui.widgets.search_results import SearchResults
from vimtg.tui.widgets.status_line import StatusLine
from vimtg.tui.widgets.which_key import WhichKey

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository
    from vimtg.services.search_service import SearchService
    from vimtg.services.vcs_service import VersionControlService


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

    def compose(self) -> ComposeResult:
        yield DeckView(id="deck-view")
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
        if (
            self._state.macros.is_recording
            and not self._replaying
            and resolve
            and not (key == "q" and not self.keymap.awaiting_more_keys)
        ):
            # Record the typed key (the recording-stop 'q' is skipped)
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

        # Update which-key tooltip
        wk = self.query_one("#which-key", WhichKey)
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
                return handle_tag_input_special(s, action)
            if s.insert_submode == InsertSubmode.LINE_EDIT:
                cl.text = action.text or ""
                cl.cursor_pos = action.cursor_pos if action.cursor_pos is not None else len(cl.text)
                return handle_line_edit_special(s, action)
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
        if hr.enter_insert:
            self._apply_enter_card_search()
        if hr.enter_command:
            s.mode_mgr.transition(Mode.COMMAND)
            self.keymap.set_mode(Mode.COMMAND)
            self.keymap.reset_text()
            self.query_one("#command-line", CommandLine).show(":")
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
            self._vcs_auto_snapshot()
        if hr.help_requested:
            hp = self.query_one("#help-panel", HelpPanel)
            hp.display = not hp.display
            self.query_one("#which-key", WhichKey).display = not hp.display
        if hr.greeter_requested:
            self.app.pop_screen()
            self.app._launch_greeter()  # type: ignore[attr-defined]
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
        if hr.search_query is not None:
            self._handle_search_action(hr.search_query)
        if hr.replay_keys:
            self._replay_macro_keys(hr.replay_keys)
        if hr.insert_confirm:
            self._confirm_insert()

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
            # Check for duplicate — increment quantity instead of adding new line
            duplicate_line = self._find_card_line(card.name)
            if duplicate_line is not None:
                qty = s.buffer.quantity_at(duplicate_line) or 0
                s.buffer = s.buffer.set_quantity(duplicate_line, qty + 1)
                self._delete_blank_cursor_line()
                s.cursor = s.cursor.move_to(min(duplicate_line, s.buffer.line_count() - 1), 0)
            elif not s.settings.auto_sort:
                # auto_sort off: card goes exactly where the user opened it
                s.buffer = s.buffer.set_line(s.cursor.row, f"1 {card.name}")
            else:
                # Find or create the right type section, then insert there
                s.buffer, insert_row = self._find_type_section_row(card, s.buffer)
                if insert_row is not None and insert_row != s.cursor.row:
                    # Remove the blank line 'o' inserted and place card in correct section
                    if self._delete_blank_cursor_line() and insert_row > s.cursor.row:
                        insert_row -= 1
                    s.buffer = s.buffer.insert_line(insert_row, f"1 {card.name}")
                    s.cursor = s.cursor.move_to(insert_row, 0)
                else:
                    s.buffer = s.buffer.set_line(s.cursor.row, f"1 {card.name}")
            s.modified = True
            s.history.record(s.buffer, f"added {card.name}")
            if self.card_repo:
                s.resolved_cards = resolve_cards(s.buffer, self.card_repo)
            cl.set_message(f"Added {card.name}  (+/- to change qty, dd to remove)")
        else:
            # No card selected — clean up blank line from 'o'
            s = self._state
            if self._delete_blank_cursor_line():
                s.cursor = s.cursor.clamp(s.buffer.line_count() - 1)
            cl.hide()
        sr.display = False
        self._state.mode_mgr.force_normal()
        self.keymap.set_mode(Mode.NORMAL)

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

    def _find_card_line(self, card_name: str) -> int | None:
        """Find existing line with this card name (for duplicate detection)."""
        buf = self._state.buffer
        for i in range(buf.line_count()):
            if buf.card_name_at(i) == card_name:
                return i
        return None

    def _find_type_section_row(self, card: Card, buf: Buffer) -> tuple[Buffer, int | None]:
        """Find the right row to insert a card based on its primary type.

        Uses singular type names: "Creature", "Instant", "Sorcery", etc.
        Creates the section header if it doesn't exist, with blank line separation.
        Returns (buffer, insert_row) — buffer may have new section header lines.
        """
        from vimtg.editor.buffer import LineType

        section_name = _card_type_section(card.type_line)

        # Look for existing section header
        for i in range(buf.line_count()):
            bl = buf.get_line(i)
            if bl.line_type == LineType.SECTION_HEADER and section_name in bl.text:
                insert_at = i + 1
                while insert_at < buf.line_count() and buf.is_card_line(insert_at):
                    insert_at += 1
                return buf, insert_at

        # No matching section — create one before sideboard or at end
        insert_at = buf.line_count()
        for i in range(buf.line_count()):
            bl = buf.get_line(i)
            if bl.line_type == LineType.SIDEBOARD_ENTRY:
                insert_at = i
                break

        # Add blank line separator if previous line is content
        if insert_at > 0 and buf.get_line(insert_at - 1).line_type != LineType.BLANK:
            buf = buf.insert_line(insert_at, "")
            insert_at += 1

        buf = buf.insert_line(insert_at, f"// {section_name}")
        return buf, insert_at + 1

    @work(thread=True)
    def _run_search(self, query: str) -> None:
        if self.search_service:
            settings = self._state.settings
            results = self.search_service.search(
                query, limit=settings.search_limit
            )
            if settings.default_format:
                results = [
                    c
                    for c in results
                    if c.legalities.get(settings.default_format) == "legal"
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
        s.buffer = cleaned
        s.cursor = s.cursor.clamp(cleaned.line_count() - 1)
        s.modified = True
        s.history.amend(cleaned)

    def _sync_widgets(self) -> None:
        # Only clean up sections in NORMAL mode — INSERT/VISUAL have transient blanks
        if self._state.mode_mgr.is_normal():
            self._cleanup_empty_sections()

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
