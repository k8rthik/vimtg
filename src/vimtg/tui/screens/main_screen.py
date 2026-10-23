"""MainScreen — thin Textual wiring layer.

Connects KeyMap events to the pure key_handler functions,
then syncs updated EditorState to Textual widgets.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
import traceback
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from textual import work
from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Key, Paste
from textual.screen import Screen

from vimtg.config import app_state
from vimtg.config.paths import cache_dir
from vimtg.config.settings import Settings
from vimtg.data.database import Database
from vimtg.data.deck_repository import parse_deck_text
from vimtg.data.scryfall_sync import NO_CARD_DATA, card_data_badge
from vimtg.domain.card import Card
from vimtg.domain.formats import get_format_rules
from vimtg.domain.search import SearchSyntaxError
from vimtg.domain.sideboard_plan import apply_plan, find_plan
from vimtg.editor.buffer import Buffer, LineType, insertion_zone
from vimtg.editor.card_insert import (
    discard_pending_insert,
    find_card_line,
    place_new_card,
)
from vimtg.editor.cmdline_history import CommandHistory
from vimtg.editor.command_completer import CommandCompleter
from vimtg.editor.commands import CommandRegistry
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import VIEW_MOTIONS, KeyMap, KeyResult, ParsedAction
from vimtg.editor.keymaps import is_named_key, load_remapper
from vimtg.editor.layout import follow_line
from vimtg.editor.lint import (
    EMPTY_LINT,
    LintResult,
    effective_format,
    lint_buffer,
)
from vimtg.editor.macros import paste_key, pasted_text
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.paste_deck import add_deck_entries
from vimtg.editor.plan_ops import (
    find_block,
    plan_search,
    plan_totals,
    row_deltas,
)
from vimtg.editor.registers import RegisterStore
from vimtg.editor.sections import normalize_sections
from vimtg.editor.session import (
    EditorState,
    HandlerResult,
    InsertSubmode,
    confirm_card_search,
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
from vimtg.editor.splits import (
    AnalyticsOpen,
    EdhrecOpen,
    SplitDirection,
    SplitOpen,
    WindowCommand,
)
from vimtg.services.clipboard import copy_message, copy_to_clipboard
from vimtg.services.deck_service import needs_new_deck_prompt, set_deck_identity
from vimtg.services.deck_sources import (
    DeckSourceError,
    RemoteDeck,
    fetch_deck,
)
from vimtg.services.edhrec import EdhrecClient, EdhrecError, EdhrecPage
from vimtg.services.history_service import HistoryService
from vimtg.services.recovery import (
    discard_copy,
    discard_recovery,
    new_buffer_id,
    pending_recovery,
    write_recovery,
)
from vimtg.tui.key_translator import translate
from vimtg.tui.keys import PENDING, VimNav
from vimtg.tui.screens.new_deck import NewDeckInfo, NewDeckScreen
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.analytics_panel import (
    AnalyticsPanel,
    build_analytics_data,
)
from vimtg.tui.widgets.command_line import GENERIC_HINT, CommandLine
from vimtg.tui.widgets.deck_view import DeckView
from vimtg.tui.widgets.edhrec_panel import EdhrecPanel
from vimtg.tui.widgets.help_panel import HelpPanel
from vimtg.tui.widgets.search_results import SearchResults
from vimtg.tui.widgets.status_line import StatusLine
from vimtg.tui.widgets.tips_panel import TipsPanel
from vimtg.tui.widgets.which_key import WhichKey

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository
    from vimtg.data.file_io import FileStamp
    from vimtg.domain.deck_merge import CardKey
    from vimtg.services.search_service import SearchService
    from vimtg.services.vcs_service import (
        MergeResult,
        PendingMerge,
        VersionControlService,
    )


_GENERIC_HINT = GENERIC_HINT
_CARD_HINT = "+/- quantity  |  dd delete  |  yy yank  |  p paste  |  : command"
_PLAN_HINT = "+/- copies  |  dd delete  |  o add card  |  zi/zo on a deck card boards it"
OFFLINE_SEARCH_NOTICE = "Card database not downloaded (offline?), :sync to retry"
SYNCING_SEARCH_NOTICE = "Card database is still downloading — search works once :sync finishes"

def _hint_for_cursor(buffer: Buffer, row: int) -> str:
    """Return the appropriate command-line hint for the current cursor position."""
    if buffer.is_card_line(row):
        return _CARD_HINT
    if buffer.get_line(row).line_type in (LineType.PLAN_ENTRY, LineType.PLAN_HEADER):
        return _PLAN_HINT
    return _GENERIC_HINT


# Below these sizes the screen sheds extras instead of squeezing the deck
TIPS_MIN_HEIGHT = 18  # first-run tips panel
SPLIT_MIN_WIDTH = 60  # side-by-side split
SPLIT_MIN_HEIGHT = 16  # stacked split

# Keys a focused pane leaves to the editor without giving up focus: the
# command line, and the window and leader prefixes
_PANE_PASS_KEYS = frozenset({":", "ctrl_w", " "})
# Ctrl-W h/j/k/l: the direction that reaches the pane in each layout
# (the other direction of the same axis is back to the editor)
_TOWARD_PANE = {
    SplitDirection.VERTICAL: (WindowCommand.RIGHT, WindowCommand.LEFT),
    SplitDirection.HORIZONTAL: (WindowCommand.DOWN, WindowCommand.UP),
}


@dataclass
class _SplitPane:
    """State of the split pane (second deck or EDHREC)."""

    kind: str  # "deck" | "edhrec" | "analytics"
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
        disk_stamp: FileStamp | None = None,
        prompt_new_deck: bool = False,
        recovery_id: str | None = None,
        recovery_copy: Path | None = None,
    ) -> None:
        super().__init__()
        # Normalize up front so a hand-written deck's section cleanup is
        # part of the loaded state, not an edit: opening and :q must not
        # report unsaved changes, and undo can never step "before" it
        buffer = normalize_sections(buffer)
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
            cmd_history=CommandHistory.load(),
        )
        self._state.history.initialize(buffer)
        self._state.clean_text = buffer.to_text()
        self._state.disk_stamp = disk_stamp
        # An unnamed buffer's recovery copy is keyed on this id (a copy
        # reopened from the greeter keeps its own, so a save removes it)
        self._state.recovery_id = recovery_id or new_buffer_id()
        # The recovery copy this editor owns — last written, or opened
        # from the greeter — so a save or a deliberate discard removes it
        # even after the file changed
        self._recovery_written: Path | None = recovery_copy
        # :q! / ZQ / :e! / :home! threw the changes away: leaving must
        # not save them again
        self._discarded = False
        # The buffer itself came from a recovery copy: never offer it
        self._offer_recovery = recovery_copy is None
        self.file_path = file_path
        self.registry = registry or CommandRegistry()
        self._state.cmd_completer = CommandCompleter(self.registry)
        self.search_service = search_service
        # Query of the newest card search started from the prompt.
        self._latest_search: str | None = None
        # Bumped when the search prompt is confirmed or cancelled; a worker
        # from an earlier generation may not touch the overlay
        self._search_generation = 0
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
        self._pane_nav = VimNav()
        # Bumped on every :edhrec so a stale fetch can't overwrite a
        # newer result (results deliver via call_from_thread)
        self._edhrec_generation = 0
        # Deck card names for the EDHREC ✓ marks, cached by buffer identity
        self._deck_names: frozenset[str] = frozenset()
        self._deck_names_key: Buffer | None = None
        # Analytics pane recompute cache, keyed like lint (identity)
        self._analytics_key: tuple[Buffer, dict[str, Card], str | None] | None = None
        # Active-plan row deltas for the deck view, keyed by (buffer, plan)
        self._plan_deltas_key: tuple[Buffer, str | None] | None = None
        self._plan_deltas_cache: dict[int, int] = {}
        # Bumped per :import <url> so a stale fetch can't clobber a
        # newer one (results deliver via call_from_thread)
        self._import_generation = 0
        # Nesting depth of _process_key (mappings and macros re-enter it);
        # only the outermost call catches, so a crash stops the replay
        self._key_depth = 0
        # Card database readout for the status line (text, attention)
        self._card_status: tuple[str, bool] = ("", False)
        # Ask for name/format when this opens a deck that is still blank
        self._prompt_new_deck = prompt_new_deck
        # The tips panel was closed (Esc) for this session
        self._tips_closed = False
        # Action type of the last completed key ("motion", ...); an
        # error message survives motions so it can still be read
        self._last_action_type = ""
        # Tips: turned off for good (state file), or shown on request
        # even for a deck with cards (:tips)
        self._tips_dismissed = app_state.tips_dismissed()
        self._tips_forced = False

    def compose(self) -> ComposeResult:
        yield Container(
            DeckView(id="deck-view"),
            DeckView(id="deck-view-2"),
            EdhrecPanel(id="edhrec-panel"),
            AnalyticsPanel(id="analytics-panel"),
            id="editor-area",
        )
        yield SearchResults(id="search-results")
        yield HelpPanel(id="help-panel")
        yield WhichKey(id="which-key")
        yield TipsPanel(id="tips-panel")
        yield StatusLine(id="status-line")
        yield CommandLine(id="command-line")

    def on_mount(self) -> None:
        # :messages is app-wide, as in vim: it survives :e and includes
        # pop-up notices (sync failures, database and config warnings)
        log = getattr(self.app, "message_log", None)  # duck-typed app
        if isinstance(log, deque):
            self.query_one("#command-line", CommandLine).history = log
        # Start overlay panels hidden (Textual display=False = CSS display:none)
        self.query_one("#search-results", SearchResults).display = False
        self.query_one("#help-panel", HelpPanel).display = False
        self.query_one("#which-key", WhichKey).display = False
        self.query_one("#deck-view-2", DeckView).display = False
        self.query_one("#edhrec-panel", EdhrecPanel).display = False
        self.query_one("#analytics-panel", AnalyticsPanel).display = False

        if self.card_repo:
            self._state.resolved_cards = resolve_cards(
                self._state.buffer, self.card_repo,
            )
        self._card_status = self._initial_card_status()
        self._sync_widgets()
        if (
            self._offer_recovery
            and self.file_path is not None
            and pending_recovery(self.file_path, self._state.buffer.to_text())
        ):
            self.query_one("#command-line", CommandLine).set_message(
                "Found unsaved changes from a crash: :recover to load them, "
                ":recover! to discard"
            )
        elif self._prompt_new_deck and needs_new_deck_prompt(
            self._state.buffer.to_text()
        ):
            self.open_new_deck_prompt()

    # ── New-deck wizard ──────────────────────────────────────────

    def open_new_deck_prompt(self) -> None:
        """Ask for the deck's name and format (Esc skips)."""
        deck = parse_deck_text(self._state.buffer.to_text())
        # `vimtg burn.deck` suggests "burn"
        suggested = self.file_path.stem if self.file_path is not None else ""
        self.app.push_screen(
            NewDeckScreen(
                name=deck.metadata.name,
                fmt=deck.metadata.format,
                suggested_name=suggested,
            ),
            self.apply_new_deck_info,
        )

    def apply_new_deck_info(self, info: NewDeckInfo | None) -> None:
        """Write the wizard's answers into the metadata lines as one
        undoable change (nothing changes when it was skipped)."""
        if info is None:
            return
        s = self._state
        old = s.buffer.to_text()
        new = set_deck_identity(old, info.name, info.fmt)
        if new == old:
            return
        s.buffer = Buffer.from_text(new)
        s.cursor = s.cursor.clamp(s.buffer.line_count() - 1)
        s.modified = True
        s.history.record(s.buffer, "new deck")
        message = f"New deck: {info.name or '(unnamed)'}"
        if info.fmt:
            message += f" ({info.fmt})"
        self._sync_widgets()
        self.query_one("#command-line", CommandLine).set_message(
            message + "  —  o add a card, :w save"
        )

    # ── Card data status ─────────────────────────────────────────

    def _initial_card_status(self) -> tuple[str, bool]:
        """The app's card data readout; computed here for hosts without one."""
        status = getattr(self.app, "card_data_status", None)
        if callable(status):
            text, attention = status()
            return str(text), bool(attention)
        if self.card_repo is None:
            return NO_CARD_DATA, True
        try:
            return card_data_badge(self.card_repo.count(), self.card_repo.get_last_sync())
        except sqlite3.Error:
            return NO_CARD_DATA, True

    def set_card_data_status(self, text: str, attention: bool) -> None:
        """Called by the app as card data appears, ages or syncs."""
        self._card_status = (text, attention)
        lines = self.query("#status-line").results(StatusLine)
        for sl in lines:  # none before compose; on_mount pulls the status
            sl.card_data, sl.card_data_attention = self._card_status

    def _card_data_available(self) -> bool:
        """True when card search has a populated database behind it."""
        if self.search_service is None:
            return False
        has_data = getattr(self.app, "has_card_data", None)
        return bool(has_data()) if callable(has_data) else True

    def _offline_notice(self) -> str:
        if getattr(self.app, "card_sync_running", False):
            return SYNCING_SEARCH_NOTICE
        return OFFLINE_SEARCH_NOTICE

    def show_message(self, text: str, *, error: bool = False) -> None:
        """Public: put a status message on the command line."""
        self.query_one("#command-line", CommandLine).set_message(text, error=error)

    # ── Clipboard ────────────────────────────────────────────────

    def on_paste(self, event: Paste) -> None:
        """Terminal paste (bracketed paste arrives as one event).

        In a text prompt — card search, the : line, a tag or comment —
        the text is inserted at the cursor (newlines folded to spaces).
        In normal mode it is read as a decklist and added to the deck as
        one undo step. Visual mode ignores it.
        """
        event.stop()
        event.prevent_default()
        if not event.text.strip() or self.query_one("#help-panel", HelpPanel).display:
            return
        if self._state.macros.is_recording and not self._replaying:
            self._state.macros.record_key(paste_key(event.text))
        try:
            self._handle_paste(event.text)
        except Exception as exc:  # same safety net as a keypress
            self.recover_from_crash(exc)

    def _handle_paste(self, text: str) -> None:
        s = self._state
        if s.mode_mgr.is_insert() or s.mode_mgr.is_command() or (
            s.mode_mgr.current == Mode.SEARCH
        ):
            action = self.keymap.paste(" ".join(text.split()))
            if action is None:
                return
            hr = self._dispatch_special(action)
            if hr:
                self._apply_handler_result(hr)
            self._sync_widgets()
            return
        if s.mode_mgr.is_normal():
            self.keymap.reset()  # a half-typed sequence ('2d') is dropped
            wk = self.query_one("#which-key", WhichKey)
            wk.pending_key = ""
            wk.display = False
            self.query_one("#status-line", StatusLine).pending_keys = ""
            self._paste_decklist(text)

    def _paste_decklist(self, text: str) -> None:
        """Add a pasted decklist to the deck (one undo step) and report
        how many cards went in and which lines were skipped."""
        from vimtg.services.import_export_service import ImportExportService

        s = self._state
        try:
            report = ImportExportService(card_repo=self.card_repo).import_deck_report(text)
        except ValueError as exc:
            self.show_message(f"E: Cannot read pasted text: {exc}", error=True)
            return
        deck = report.deck
        if not deck.entries:
            self.show_message(
                "E: Nothing pasted: no card lines found "
                "(expected lines like '4 Lightning Bolt')",
                error=True,
            )
            return

        def type_line(name: str) -> str | None:
            card = s.resolved_cards.get(name)
            if card is None and self.card_repo is not None:
                card = self.card_repo.get_by_name(name)
            return card.type_line if card is not None else None

        result = add_deck_entries(
            s.buffer,
            deck,
            auto_sort=s.settings.auto_sort,
            type_line=type_line,
            card_key=self._paste_card_key(),
        )
        s.buffer = result.buffer
        if result.first_row is not None:
            s.cursor = s.cursor.move_to(result.first_row, 0)
        s.modified = True
        s.history.record(s.buffer, f"paste {result.cards} cards")
        if self.card_repo:
            s.resolved_cards = resolve_cards(s.buffer, self.card_repo)
        message = f"Pasted {result.cards} cards ({len(deck.entries)} lines)"
        if report.skipped:
            first = report.skipped[0]
            message += (
                f" | {len(report.skipped)} line(s) skipped"
                f" (line {first.line_number}: {first.text[:40]})"
            )
        self._sync_widgets()
        self.show_message(message)

    def _paste_card_key(self) -> Callable[[str], str]:
        """Card identity for paste merging: the oracle id when the card
        is known (so 'Insectile Aberration' merges into 'Delver of
        Secrets'), else the normalised name. Memoised for one paste."""
        from vimtg.domain.card_names import normalize_card_name

        s = self._state
        memo: dict[str, str] = {}

        def key(name: str) -> str:
            norm = normalize_card_name(name)
            if norm not in memo:
                card = s.resolved_cards.get(name)
                if card is None and self.card_repo is not None:
                    card = self.card_repo.get_by_name(name)
                memo[norm] = (
                    f"oracle:{card.oracle_id}"
                    if card is not None and card.oracle_id
                    else normalize_card_name(card.name) if card is not None else norm
                )
            return memo[norm]

        return key

    def _copy_to_clipboard(self, text: str, label: str) -> None:
        """Copy via a native clipboard tool, else OSC 52 through Textual
        (never raw bytes on stdout while Textual owns the terminal)."""
        result = copy_to_clipboard(text, osc52=self.app.copy_to_clipboard)
        message, error = copy_message(result, label)
        self.show_message(message, error=error)

    # ── Key dispatch ─────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        # Let Ctrl+C through for emergency quit
        if event.key == "ctrl+c":
            return
        event.prevent_default()
        event.stop()

        # ── Help panel modal: ? / Escape close, scroll keys scroll,
        # everything else is swallowed so it never reaches the editor ──
        hp = self.query_one("#help-panel", HelpPanel)
        if hp.display:
            key = translate(event.key)
            if key in ("?", "escape", "q"):
                hp.display = False
            else:
                hp.scroll_by_key(key)
            return

        # F1 opens the full help screen from normal mode
        if event.key == "f1" and self._state.mode_mgr.is_normal():
            self._open_help(None)
            return

        # Translate Textual key name → canonical vim key name
        key = translate(event.key)
        if key == "escape" and self._state.mode_mgr.is_normal():
            self._tips_closed = True  # Esc closes the tips for the session
        # Clear transient messages from the previous keypress. An error
        # stays up through motions (so it can be read while moving) and
        # goes with the first other key; :messages keeps them all.
        cl = self.query_one("#command-line", CommandLine)
        if cl.message and not cl.error:
            cl.message = ""
        sticky = cl.message_serial if cl.message else None
        self._last_action_type = ""
        self._process_key(key)
        if (
            sticky is not None
            and cl.message_serial == sticky
            and self._last_action_type not in ("motion", "pending")
        ):
            cl.message = ""

    def _process_key(self, key: str, resolve: bool = True) -> None:
        """Run one canonical key through remap, keymap, and dispatch.

        Shared by live keypresses, macro replay, and mapping expansion
        (expanded keys pass resolve=False so mappings don't re-resolve).
        An unexpected error in the outermost call is caught: the buffer
        is saved for :recover and the editor keeps running.
        """
        self._key_depth += 1
        try:
            if self._key_depth > 1:
                self._handle_key(key, resolve)
                return
            try:
                self._handle_key(key, resolve)
            except Exception as exc:  # the crash safety net
                self.recover_from_crash(exc)
        finally:
            self._key_depth -= 1

    def save_recovery(self, exc: BaseException) -> Path | None:
        """Write the buffer (and the traceback) to the recovery dir."""
        log = "".join(traceback.format_exception(exc))
        return self._write_recovery(log)

    def _write_recovery(self, log: str = "") -> Path | None:
        saved = write_recovery(
            self.file_path, self._state.buffer.to_text(), log, self._state.recovery_id,
        )
        if saved is not None:
            if self._recovery_written is not None and self._recovery_written != saved:
                discard_copy(self._recovery_written)  # superseded (file renamed)
            self._recovery_written = saved
        return saved

    def preserve_unsaved(self) -> Path | None:
        """The editor is going away (quit, Ctrl-C/Ctrl-Q, :home, a closed
        terminal, SIGHUP/SIGTERM): keep unsaved changes as a recovery
        copy the next open offers. Nothing is written for a clean buffer
        or after a deliberate discard (:q!, ZQ)."""
        if self._discarded or not self._state.modified:
            return None
        return self._write_recovery()

    def _drop_recovery(self) -> None:
        """Remove this buffer's recovery copy — after a save, or when its
        changes were discarded on purpose."""
        discard_recovery(self.file_path, self._state.recovery_id)
        discard_recovery(None, self._state.recovery_id)  # from before a first :w
        if self._recovery_written is not None:
            discard_copy(self._recovery_written)
            self._recovery_written = None

    def on_unmount(self) -> None:
        # Popped (:home, :e) or torn down at exit: nothing unsaved is lost
        with contextlib.suppress(Exception):
            self.preserve_unsaved()

    def recover_from_crash(self, exc: Exception) -> None:
        """Save the buffer, reset to a sane normal-mode state, and report
        the error on the command line instead of taking the app down."""
        saved = self.save_recovery(exc)
        s = self._state
        s.mode_mgr.force_normal()
        self.keymap.set_mode(Mode.NORMAL)
        self.keymap.reset_text()
        s.visual_anchor = None
        s.pending_insert = None
        s.line_edit_original = None
        s.line_edit_row = None
        s.line_edit_prefix = ""
        s.insert_submode = InsertSubmode.CARD_SEARCH
        s.cursor = s.cursor.clamp(max(0, s.buffer.line_count() - 1))
        where = f"; buffer saved to {saved}" if saved else ""
        message = f"E: internal error ({type(exc).__name__}: {exc}){where}"
        try:
            self.query_one("#search-results", SearchResults).display = False
            cl = self.query_one("#command-line", CommandLine)
            cl.hide()
            self._sync_widgets()
            cl.set_message(message, error=True)
        except Exception:  # never re-raise from the net
            pass

    def _handle_key(self, key: str, resolve: bool) -> None:
        pasted = pasted_text(key)
        if pasted is not None:  # a paste recorded in a macro
            self._handle_paste(pasted)
            return
        # Split pane focused: navigation keys drive the pane; ':', Ctrl-W
        # and Space sequences pass through; any other key refocuses the editor
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
            if key not in _PANE_PASS_KEYS:
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
        # Vim matches mappings only where a command starts: never on the
        # second key of zs, a register name, or an operator's motion
        if resolve and not self.keymap.awaiting_more_keys:
            resolved = self.remapper.resolve(key, self._state.mode_mgr.current)
            if resolved != key and len(resolved) > 1 and not is_named_key(resolved):
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
            self._last_action_type = "pending"
            wk.pending_key = self.keymap.pending_menu
            wk.display = self._state.settings.show_which_key
            return
        wk.pending_key = ""
        wk.display = False

        if result != KeyResult.COMPLETE or action is None:
            return

        self._last_action_type = action.action_type
        s = self._state
        hr = None
        if action.action_type == "motion":
            if action.action in VIEW_MOTIONS:
                s.view_band = self.query_one("#deck-view", DeckView).cursor_band()
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
            s.visual_anchor = None  # :'<,'> consumed the selection
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
        if s.mode_mgr.is_command() or s.mode_mgr.current == Mode.SEARCH:
            # `/` search shares the command line and its key handling
            cl = self.query_one("#command-line", CommandLine)
            cl.text = action.text or ""
            cl.cursor_pos = action.cursor_pos if action.cursor_pos is not None else len(cl.text)
            hr = handle_command_special(s, action)
            if hr.command_replace is not None:
                # Up/Down history recall
                cl.text = hr.command_replace
                cl.cursor_pos = len(hr.command_replace)
                self.keymap.set_command_text(hr.command_replace)
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
        # Cancelling an o/O card search takes its scratch blank with it
        discard_pending_insert(s)
        s.mode_mgr.force_normal()
        # Leaving visual mode by any route ends the selection — a stale
        # anchor would make the next dd delete every line up to it
        s.visual_anchor = None
        self._latest_search = None
        self._search_generation += 1
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
        # Entering insert from visual (the c operator) ends the selection
        s.visual_anchor = None
        s.insert_submode = InsertSubmode.CARD_SEARCH
        s.mode_mgr.transition(Mode.INSERT)
        self.keymap.set_mode(Mode.INSERT)
        self.keymap.reset_text()
        self._latest_search = None
        self._update_search_results([])  # never confirm a stale result
        cl = self.query_one("#command-line", CommandLine)
        cl.show("")
        cl.message = (
            "Type card name to search..."
            if self._card_data_available() or self._in_plan_zone()
            else f"{self._offline_notice()} — Esc to cancel"
        )

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
            self.query_one("#command-line", CommandLine).show(
                "?" if s.search_backward else "/"
            )
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
                # unsaved deck, which had no history).
                self._vcs_service = None
            self.file_path = hr.file_path
        if hr.file_saved:
            # The deck is safely on disk: its crash copy is obsolete
            self._drop_recovery()
            # Only an actual save auto-snapshots — every ex command carries
            # file_path, and committing on each one would defeat the
            # uncommitted-changes guard on merge/rebase/switch.
            self._vcs_auto_snapshot()
        if hr.discard_changes:
            self._discarded = True
            self._drop_recovery()
        if hr.help_requested:
            hp = self.query_one("#help-panel", HelpPanel)
            if hp.display:
                hp.display = False
            else:
                hp.open()
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
        if hr.analytics_open is not None:
            self._open_analytics(hr.analytics_open)
        if hr.hand_open is not None:
            from vimtg.tui.screens.hand_screen import HandScreen

            self.app.push_screen(HandScreen(hr.hand_open))
        if hr.import_url:
            self._start_url_import(hr.import_url)
        if hr.clipboard_text is not None:
            self._copy_to_clipboard(hr.clipboard_text, hr.clipboard_label)
        if hr.card_sync:
            self._start_card_sync(force=hr.card_sync == "force")
        if hr.window is not None:
            self._window_command(hr.window)
        if hr.toggle_pane:
            self._toggle_pane(hr.toggle_pane)
        if hr.run_ex_command:
            self._execute_ex(hr.run_ex_command)
        if hr.scroll_view:
            self.query_one("#deck-view", DeckView).scroll_cursor_to(hr.scroll_view)
        if hr.ui_request:
            self._handle_ui_request(hr.ui_request)
        if hr.search_open is not None:
            self._open_card_search(hr.search_open)
        if hr.edit_file is not None:
            self._edit_file(hr.edit_file)

    def _edit_file(self, path: Path) -> None:
        """:e — replace this editor with one on `path` (registers carry
        over, as in vim)."""
        app = self.app
        open_deck = getattr(app, "open_deck", None)  # duck-typed navigation
        if not callable(open_deck):
            return
        registers = self._state.registers
        app.pop_screen()
        open_deck(path)
        new_screen = app.screen
        if isinstance(new_screen, MainScreen):
            new_screen._state.registers = registers

    def _open_card_search(self, query: str) -> None:
        """:search — open the card search exactly as `o` does (ignoring any
        :map of o), then type the query into it."""
        for key in ("o", *query):
            self._process_key(key, resolve=False)

    def _handle_ui_request(self, request: str) -> None:
        """:messages and :tips — screen-level views with no buffer change."""
        cl = self.query_one("#command-line", CommandLine)
        if request == "messages":
            body = "\n".join(text for _error, text in cl.history) or "(no messages)"
            from vimtg.tui.screens.help_screen import HelpScreen

            self.app.push_screen(HelpScreen(body=body, title="Messages"))
        elif request == "messages_clear":
            cl.history.clear()
        elif request == "tips_show":
            self._tips_closed = False
            self._tips_forced = True
        elif request in ("tips_on", "tips_off"):
            self._tips_dismissed = request == "tips_off"
            self._tips_closed = False
            self._tips_forced = False
            app_state.set_tips_dismissed(self._tips_dismissed)
            cl.set_message(
                "Tips off (:tips on brings them back)" if self._tips_dismissed
                else "Tips on: shown while the deck is empty"
            )
        if request.startswith("tips"):
            self._update_tips(count_cards(self._state.buffer))

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
            s = self._state
            if len(query) >= 2 and insertion_zone(s.buffer, s.cursor.row) == (
                LineType.PLAN_ENTRY
            ):
                # A plan line names a card the deck already has — search
                # the deck itself, not the whole card database
                self._update_search_results(
                    plan_search(s.buffer, s.resolved_cards, query)
                )
            elif len(query) >= 2 and not self._card_data_available():
                # Say why nothing can match instead of an empty overlay
                sr.results = []
                sr.error = ""
                sr.notice = self._offline_notice()
                sr.display = True
            elif len(query) >= 2 and self.search_service:
                self._latest_search = query
                self._run_search(query)
            elif len(query) < 2:
                sr.display = False

    def _confirm_insert(self) -> None:
        sr = self.query_one("#search-results", SearchResults)
        cl = self.query_one("#command-line", CommandLine)
        self._latest_search = None
        self._search_generation += 1
        card = sr.get_selected() if sr.display else None
        if card:
            s = self._state
            cl.set_message(confirm_card_search(s, card))
            if self.card_repo:
                s.resolved_cards = resolve_cards(s.buffer, self.card_repo)
        else:
            # No card selected — the o/O scratch blank is discarded
            discard_pending_insert(self._state)
            cl.hide()
            if not self._card_data_available() and not self._in_plan_zone():
                cl.set_message(f"Nothing added: {self._offline_notice()}", error=True)
        sr.display = False
        self._state.mode_mgr.force_normal()
        self.keymap.set_mode(Mode.NORMAL)

    def _place_new_card(
        self, card: Card | None, name: str, qty: int, open_row: int | None
    ) -> int:
        """Write a fresh mainboard line where the placement policy says
        and return its row (see editor.card_insert.place_new_card)."""
        return place_new_card(self._state, card, name, qty, open_row)

    # ── Split panes and EDHREC ───────────────────────────────────

    def _execute_ex(self, text: str) -> None:
        """Run an ex command as if the user typed :text<Enter>."""
        s = self._state
        prev_settings = s.settings
        hr = handle_command(
            s, ParsedAction("command_submit", "enter", text=text),
            self.registry, self.file_path, self.save_fn, record_history=False,
        )
        if s.settings is not prev_settings:
            self._on_settings_saved(s.settings)
        s.mode_mgr.force_normal()
        self.keymap.set_mode(Mode.NORMAL)
        if hr:
            self._apply_handler_result(hr)

    def on_deck_view_cursor_request(self, message: DeckView.CursorRequest) -> None:
        """A wheel scroll pushed the cursor off screen; move it to the row
        the view asked for. Only in normal/visual mode — an insert or
        command in progress owns the cursor."""
        if not message.view.is_current_request(message.row):
            return  # superseded by a later wheel event
        s = self._state
        comp = self._split_pane
        if comp is not None and message.view.id == "deck-view-2":
            if comp.buffer is not None:
                comp.cursor_row = max(0, min(message.row, comp.buffer.line_count() - 1))
                self._sync_widgets()
            return
        if not (s.mode_mgr.is_normal() or s.mode_mgr.is_visual()):
            return
        s.cursor = s.cursor.move_to(
            max(0, min(message.row, s.buffer.line_count() - 1)), 0
        )
        self._sync_widgets()

    def _split_pane_widget(self) -> DeckView | EdhrecPanel | AnalyticsPanel:
        if self._split_pane is not None and self._split_pane.kind == "edhrec":
            return self.query_one("#edhrec-panel", EdhrecPanel)
        if self._split_pane is not None and self._split_pane.kind == "analytics":
            return self.query_one("#analytics-panel", AnalyticsPanel)
        return self.query_one("#deck-view-2", DeckView)

    def _apply_split_layout(self) -> None:
        """Show the split-pane widget in the requested direction."""
        comp = self._split_pane
        if comp is None:
            return
        area = self.query_one("#editor-area", Container)
        side_by_side = comp.direction is SplitDirection.VERTICAL
        area.styles.layout = "horizontal" if side_by_side else "vertical"
        show: DeckView | EdhrecPanel | AnalyticsPanel | None = self._split_pane_widget()
        if not self._split_fits(side_by_side):
            # No room for two panes: show the deck alone (the split
            # stays open and comes back when the terminal grows)
            show = None
            comp.focused = False
        for widget in (
            self.query_one("#deck-view-2", DeckView),
            self.query_one("#edhrec-panel", EdhrecPanel),
            self.query_one("#analytics-panel", AnalyticsPanel),
        ):
            widget.display = widget is show
        self._sync_pane_focus()

    def _split_fits(self, side_by_side: bool) -> bool:
        """True when the terminal has room for the split pane (unknown
        size — before the first layout — counts as room)."""
        width, height = self.size
        if not width or not height:
            return True
        if side_by_side:
            return width >= SPLIT_MIN_WIDTH
        return height >= SPLIT_MIN_HEIGHT

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
        ap = self.query_one("#analytics-panel", AnalyticsPanel)
        ap.focused_panel = comp.kind == "analytics" and comp.focused

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
            f"Split: {spec.path.name}  (Ctrl-W w switch pane, :close to close)"
        )

    def _start_url_import(self, url: str) -> None:
        """:import <url> — fetch the deck from any site in
        services.deck_sources off the UI thread, then replace the buffer
        with the result."""
        host = urlparse(url).hostname or url
        self.query_one("#command-line", CommandLine).set_message(
            f"Fetching deck from {host}..."
        )
        self._import_generation += 1
        self._run_url_import(url, self._import_generation)

    @work(thread=True)
    def _run_url_import(self, url: str, generation: int) -> None:
        try:
            remote = fetch_deck(url)
        except DeckSourceError as exc:
            self.app.call_from_thread(
                self._url_import_failed, str(exc), generation
            )
            return
        self.app.call_from_thread(
            self._url_import_loaded, remote, url, generation
        )

    def _url_import_failed(self, message: str, generation: int) -> None:
        if generation != self._import_generation:
            return
        self.query_one("#command-line", CommandLine).set_message(
            f"E: {message}", error=True
        )

    def _url_import_loaded(
        self, remote: RemoteDeck, url: str, generation: int
    ) -> None:
        if generation != self._import_generation:
            return
        from vimtg.services.deck_sources import stamped_deck
        from vimtg.services.import_export_service import (
            NO_FORMAT_NOTE,
            ImportExportService,
            canonicalize_names,
            merge_duplicate_entries,
            structured_deck_text,
        )

        s = self._state
        service = ImportExportService(card_repo=self.card_repo)
        deck = stamped_deck(remote, url)
        resolution = service.resolve_cards(deck)
        deck = merge_duplicate_entries(canonicalize_names(deck, resolution.resolved))
        s.buffer = Buffer.from_text(structured_deck_text(deck, resolution.resolved))
        s.cursor = Cursor()
        s.modified = True
        s.history.record(s.buffer, f"import {remote.name or url}")
        if self.card_repo:
            s.resolved_cards = resolve_cards(s.buffer, self.card_repo)
        message = f"Imported {deck.total_cards()} cards"
        if remote.name:
            message += f" — {remote.name}"
        if resolution.unresolved:
            from vimtg.domain.errors import CardsNotFoundWarning

            message += f" | {CardsNotFoundWarning(len(resolution.unresolved))}"
        if not deck.metadata.format:
            message += f" | {NO_FORMAT_NOTE}"
        self.query_one("#command-line", CommandLine).set_message(message)
        self._sync_widgets()

    def _open_analytics(self, req: AnalyticsOpen) -> None:
        # Focus stays in the editor: the pane is a live readout that
        # updates as the deck is edited, not a list to navigate
        self._split_pane = _SplitPane(
            kind="analytics", direction=req.direction,
        )
        self._analytics_key = None  # force a fresh compute
        self._apply_split_layout()
        self._sync_widgets()
        self.query_one("#command-line", CommandLine).set_message(
            "Analytics pane open  (Ctrl-W w focus to scroll, Space a to close)"
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
        self.query_one("#analytics-panel", AnalyticsPanel).display = False

    def _window_command(self, command: WindowCommand) -> None:
        """Ctrl-W: move focus between the editor and the pane, or close
        the pane. With no pane, Ctrl-W q is :quit and the rest say why
        nothing happened, as in vim."""
        comp = self._split_pane
        cl = self.query_one("#command-line", CommandLine)
        if command in (WindowCommand.CLOSE, WindowCommand.QUIT, WindowCommand.ONLY):
            if comp is not None:
                self._close_split()
            elif command is WindowCommand.QUIT:
                self._execute_ex("quit")
            elif command is WindowCommand.CLOSE:
                cl.set_message("E444: Cannot close last window", error=True)
            else:
                cl.set_message("Already only one window")
            return
        if comp is None:
            cl.set_message("E: No split open (Ctrl-W v / Ctrl-W s or :vsplit)", error=True)
            return
        if not self._split_pane_widget().display:
            cl.set_message("E: Terminal too small to show the split", error=True)
            return
        toward, back = _TOWARD_PANE[comp.direction]
        if command is WindowCommand.NEXT:
            comp.focused = not comp.focused
        elif command in (toward, back):
            comp.focused = command is toward
        self._pane_nav.reset()
        self._sync_pane_focus()

    def _toggle_pane(self, kind: str) -> None:
        """Space a / Space r: close the pane when it is the one open,
        else open it (in place of any other pane)."""
        if self._split_pane is not None and self._split_pane.kind == kind:
            self._close_split()
            return
        self._execute_ex(kind)

    def _handle_split_pane_key(self, key: str) -> bool:
        """Drive the focused split pane; True when the key was consumed.

        Every pane shares the navigation vocabulary (j/k, Ctrl-D/U, gg/G,
        Home/End); the EDHREC pane adds tab switching and Enter.
        """
        comp = self._split_pane
        assert comp is not None
        if key == "escape":
            comp.focused = False
            self._pane_nav.reset()
            self._sync_pane_focus()
            return True
        step = self._pane_nav.feed(key, self._pane_viewport(comp))
        if step == PENDING:
            return True
        if step is not None:
            self._pane_navigate(comp, step)
            return True
        if comp.kind == "edhrec":
            return self._split_edhrec_key(key)
        return False

    def _pane_viewport(self, comp: _SplitPane) -> int:
        if comp.kind == "deck":
            return self.query_one("#deck-view-2", DeckView).size.height
        if comp.kind == "analytics":
            return self.query_one("#analytics-panel", AnalyticsPanel).viewport_rows()
        return self.query_one("#edhrec-panel", EdhrecPanel).viewport_rows()

    def _pane_navigate(self, comp: _SplitPane, step: int | str) -> None:
        """Apply a shared navigation step to whichever pane is focused."""
        if comp.kind == "deck":
            if comp.buffer is None:
                return
            last = comp.buffer.line_count() - 1
            if step == "home":
                comp.cursor_row = 0
            elif step == "end":
                comp.cursor_row = last
            else:
                comp.cursor_row = max(0, min(comp.cursor_row + int(step), last))
            return
        if comp.kind == "analytics":
            panel = self.query_one("#analytics-panel", AnalyticsPanel)
            if step == "home":
                panel.scroll_to_top()
            elif step == "end":
                panel.scroll_to_bottom()
            else:
                panel.scroll_by(int(step))
            return
        edh = self.query_one("#edhrec-panel", EdhrecPanel)
        if step == "home":
            edh.select_first()
        elif step == "end":
            edh.select_last()
        else:
            edh.select_by(int(step))

    def _split_edhrec_key(self, key: str) -> bool:
        panel = self.query_one("#edhrec-panel", EdhrecPanel)
        if key in ("l", "right", "tab"):
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
            row = self._place_new_card(card, rec.name, 1, None)
            if self.card_repo:
                s.resolved_cards = resolve_cards(s.buffer, self.card_repo)
        s.cursor = s.cursor.move_to(min(row, s.buffer.line_count() - 1), 0)
        s.modified = True
        s.history.record(s.buffer, f"added {rec.name} (EDHREC)")
        cl.set_message(f"Added {rec.name}")

    def _in_plan_zone(self) -> bool:
        """Card search inside a VS: block searches the deck, not the DB."""
        s = self._state
        return insertion_zone(s.buffer, s.cursor.row) == LineType.PLAN_ENTRY

    def _start_card_sync(self, force: bool) -> None:
        start = getattr(self.app, "start_card_sync", None)
        if not callable(start):
            self.show_message("E: Card sync is not available here", error=True)
            return
        self.show_message(str(start(force=force)))

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
        from vimtg.config.settings_writer import SettingsWriteError
        from vimtg.tui.app import VimTGApp
        app = self.app
        error = ""
        if isinstance(app, VimTGApp):
            try:
                app.update_settings(new_settings)
            except (SettingsWriteError, OSError) as exc:
                error = f"E: Settings applied but not saved: {exc}"
        self._sync_widgets()
        cl = self.query_one("#command-line", CommandLine)
        if error:
            cl.set_message(error, error=True)
            self.notify(error, title="Settings", severity="error", timeout=10)
        else:
            cl.set_message("Settings saved")

    # ── VCS integration ─────────────────────────────────────

    def _get_vcs_service(self) -> VersionControlService | None:
        """Lazily initialize VCS service on first use. History is keyed
        by the deck's path, so a deck with no file yet has none."""
        if self._vcs_service is not None:
            return self._vcs_service
        if self._db is None or self.file_path is None:
            return None
        from vimtg.data.snapshot_repository import SnapshotRepository
        from vimtg.services.vcs_service import VersionControlService
        repo = SnapshotRepository(self._db)
        self._vcs_service = VersionControlService(repo, str(self.file_path.resolve()))
        return self._vcs_service

    def _vcs_or_report(self) -> VersionControlService | None:
        """The VCS service, or None after saying on the command line why
        there is none (an unsaved deck, or no database)."""
        vcs = self._get_vcs_service()
        if vcs is None:
            cl = self.query_one("#command-line", CommandLine)
            if self.file_path is None:
                cl.set_message("E32: No file name (:w the deck first)", error=True)
            else:
                cl.set_message("VCS unavailable (no database)")
        return vcs

    def _open_history(self) -> None:
        from vimtg.services.deck_diff_service import DeckDiffService
        from vimtg.tui.screens.history_screen import HistoryScreen
        vcs = self._vcs_or_report()
        if vcs is None:
            return
        diff_svc = DeckDiffService(card_repo=self.card_repo)
        self.app.push_screen(HistoryScreen(
            vcs_service=vcs,
            diff_service=diff_svc,
            current_deck_state=self._state.buffer.to_text(),
            deck_name=self.file_path.name if self.file_path else "(new)",
            on_restore=self._on_restore,
            price_source=self._state.settings.price_source,
            on_apply_state=self._on_vcs_state,
        ))

    def _on_restore(self, deck_state: str) -> None:
        """Callback from HistoryScreen when user restores a snapshot."""
        self._on_vcs_state(deck_state, "restore from VCS")

    def _on_vcs_state(self, deck_state: str, reason: str) -> None:
        """Adopt a VCS result (restore, merge, rebase, switch, cherry-pick)
        into the editor. The cursor keeps its row, clamped to the new
        buffer, and the undo entry is labelled with `reason`."""
        self._state.buffer = Buffer.from_text(deck_state)
        row = min(self._state.cursor.row, max(0, self._state.buffer.line_count() - 1))
        self._state.cursor = Cursor(row=row)
        clean = self._state.clean_text
        self._state.modified = clean is None or self._state.buffer.to_text() != clean
        self._state.history.record(self._state.buffer, reason)
        if self.card_repo:
            self._state.resolved_cards = resolve_cards(
                self._state.buffer, self.card_repo,
            )
        self._sync_widgets()

    def _vcs_commit(self, description: str) -> None:
        """Create a VCS snapshot with the given description."""
        vcs = self._vcs_or_report()
        if vcs is None:
            return
        cl = self.query_one("#command-line", CommandLine)
        try:
            snap = vcs.commit(self._state.buffer.to_text(), description)
        except sqlite3.Error as exc:
            cl.set_message(f"E: Snapshot failed: {exc}", error=True)
            return
        cl.set_message(f"Snapshot: {snap.description}")
        self._sync_widgets()

    def _vcs_checkpoint(self, name: str) -> None:
        """Commit the current deck state and tag the snapshot with name."""
        vcs = self._vcs_or_report()
        if vcs is None:
            return
        cl = self.query_one("#command-line", CommandLine)
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
        vcs = self._vcs_or_report()
        if vcs is None:
            return
        cl = self.query_one("#command-line", CommandLine)
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
        vcs = self._vcs_or_report()
        if vcs is None:
            return
        cl = self.query_one("#command-line", CommandLine)
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
        vcs = self._vcs_or_report()
        if vcs is None:
            return
        cl = self.query_one("#command-line", CommandLine)
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
        vcs = self._vcs_or_report()
        if vcs is None:
            return
        cl = self.query_one("#command-line", CommandLine)
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
                on_abort=lambda: cl.set_message("Merge aborted — nothing committed"),
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

        vcs = self._vcs_or_report()
        if vcs is None:
            return
        cl = self.query_one("#command-line", CommandLine)
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
        """Find an existing line with this card name in `zone` (default
        the mainboard) — see editor.card_insert.find_card_line."""
        return find_card_line(self._state.buffer, card_name, zone)

    @work(thread=True)
    def _run_search(self, query: str) -> None:
        if self.search_service:
            generation = self._search_generation
            settings = self._state.settings
            # Same format resolution as lint: the deck's declared
            # "// Format:" wins over the global default. Only filter on
            # formats we actually know — an unknown or misspelled format
            # must not silently empty the results. Restricted cards are
            # playable (1 copy), so they stay. Filtering happens in the
            # query, before search_limit, so it never truncates results.
            deck = parse_deck_text(self._state.buffer.to_text())
            fmt = effective_format(deck, settings.default_format)
            rules = get_format_rules(fmt) if fmt else None
            try:
                results = self.search_service.search(
                    query,
                    limit=settings.search_limit,
                    legal_in=rules.name if rules is not None else None,
                )
            except SearchSyntaxError as exc:
                self.app.call_from_thread(
                    self._show_search_error, query, str(exc), generation
                )
                return
            self.app.call_from_thread(
                self._apply_search_results, query, results, generation
            )

    def _search_is_current(self, query: str) -> bool:
        """Workers finish out of order under fast typing; only the one
        for the latest query typed may update the overlay."""
        return self._latest_search is None or self._latest_search == query

    def _apply_search_results(
        self, query: str, results: list[Card], generation: int | None = None
    ) -> None:
        if self._search_is_current(query) and self._search_is_live(generation):
            self._update_search_results(results)

    def _search_is_live(self, generation: int | None) -> bool:
        """False for a worker started before the search prompt was last
        confirmed or cancelled: its result must not reopen the overlay
        over the deck (None: a caller outside the worker path)."""
        return generation is None or generation == self._search_generation

    def _show_search_error(
        self, query: str, message: str, generation: int | None = None
    ) -> None:
        if not self._search_is_current(query) or not self._search_is_live(generation):
            return
        self._update_search_results([])
        sr = self.query_one("#search-results", SearchResults)
        sr.error = message
        sr.display = True

    def _update_search_results(self, results: list[Card]) -> None:
        sr = self.query_one("#search-results", SearchResults)
        sr.error = ""
        sr.notice = ""
        sr.results = results
        sr.selected = 0
        # An empty result says so instead of silently hiding the overlay
        sr.notice = "" if results else "No matches"
        sr.display = True
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
        new_row = follow_line(s.buffer, cleaned, s.cursor.row)
        s.buffer = cleaned
        s.cursor = s.cursor.move_to(new_row).clamp(cleaned.line_count() - 1)
        # Modified follows the text, as after u: cleanup can bring an
        # edit (:t$ of the trailing blank) back to the saved deck
        s.modified = cleaned.to_text() != s.clean_text
        s.history.amend(cleaned)

    def _sync_analytics_pane(self) -> None:
        """Feed the analytics pane: recompute on buffer/resolution
        change (identity compare, like lint), cursor odds every sync."""
        s = self._state
        panel = self.query_one("#analytics-panel", AnalyticsPanel)
        key = self._analytics_key
        if (
            key is None
            or key[0] is not s.buffer
            or key[1] is not s.resolved_cards
            or key[2] != s.active_plan
        ):
            deck = parse_deck_text(s.buffer.to_text())
            # With a plan active the pane shows the post-board deck
            plan = find_plan(deck, s.active_plan) if s.active_plan else None
            if plan is not None:
                deck = apply_plan(deck, plan)
            panel.plan_name = plan.name if plan is not None else ""
            panel.data = build_analytics_data(
                deck, s.resolved_cards, s.settings.price_source
            )
            self._analytics_key = (s.buffer, s.resolved_cards, s.active_plan)
        # Draw odds follow the cursor — mainboard cards only (the odds
        # population is the mainboard)
        row = s.cursor.row
        name = s.buffer.card_name_at(row)
        if (
            name is not None
            and s.buffer.get_line(row).line_type == LineType.CARD_ENTRY
        ):
            panel.cursor_card = (name, s.buffer.quantity_at(row) or 0)
        else:
            panel.cursor_card = None

    def _plan_deltas(self) -> dict[int, int]:
        """Row deltas of the active plan, cached per (buffer, plan)."""
        s = self._state
        key = (s.buffer, s.active_plan)
        if self._plan_deltas_key != key:
            self._plan_deltas_cache = (
                row_deltas(s.buffer, s.active_plan) if s.active_plan else {}
            )
            self._plan_deltas_key = key
        return self._plan_deltas_cache

    def _plan_status(self) -> tuple[str, bool]:
        """('vs Tron -4/+4', unbalanced) for the status line; ('', False)
        when no plan is active or its block is gone."""
        s = self._state
        if not s.active_plan:
            return "", False
        block = find_block(s.buffer, s.active_plan)
        if block is None:
            return "", False
        outs, ins = plan_totals(s.buffer, block)
        return f"vs {block.name} -{outs}/+{ins}", outs != ins

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
        dv.plan_deltas = self._plan_deltas()

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
            elif comp.kind == "analytics":
                self._sync_analytics_pane()

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
        sl.plan_status, sl.plan_unbalanced = self._plan_status()
        sl.card_data, sl.card_data_attention = self._card_status

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
        self._update_tips(sl.card_count)

    def _update_tips(self, card_count: int) -> None:
        """Show the first-run tips under an empty deck (normal mode,
        room to spare) unless turned off or closed with Esc."""
        wanted = self._tips_forced or (card_count == 0 and not self._tips_dismissed)
        self.query_one("#tips-panel", TipsPanel).display = (
            wanted
            and not self._tips_closed
            and self._state.mode_mgr.is_normal()
            and self.size.height >= TIPS_MIN_HEIGHT
        )

    def on_resize(self) -> None:
        """Small terminals: drop the tips and any split pane that no
        longer fits, and bring them back when there is room again."""
        self._update_tips(count_cards(self._state.buffer))
        if self._split_pane is not None:
            self._apply_split_layout()
