"""MainScreen — thin Textual wiring layer.

Connects KeyMap events to the pure key_handler functions,
then syncs updated EditorState to Textual widgets.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual import work
from textual.events import Key
from textual.screen import Screen

from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import CommandRegistry
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult
from vimtg.editor.keymaps import load_remapper
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.services.history_service import HistoryService
from vimtg.tui.screens.key_handler import (
    EditorState,
    count_cards,
    handle_command,
    handle_insert_special,
    handle_mode_switch,
    handle_motion,
    handle_normal_special,
    handle_operator,
    resolve_cards,
)
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.deck_view import DeckView
from vimtg.tui.widgets.search_results import SearchResults
from vimtg.tui.widgets.status_line import StatusLine
from vimtg.tui.widgets.which_key import WhichKey

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository
    from vimtg.services.search_service import SearchService


class MainScreen(Screen):
    """Primary editor screen: deck view, status line, command line."""

    def __init__(
        self,
        buffer: Buffer,
        file_path: Path | None = None,
        registry: CommandRegistry | None = None,
        search_service: SearchService | None = None,
        card_repo: CardRepository | None = None,
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
        )
        self._state.history.initialize(buffer)
        self.file_path = file_path
        self.registry = registry or CommandRegistry()
        self.search_service = search_service
        self.card_repo = card_repo
        self.keymap = KeyMap()
        self.remapper = load_remapper()

    def compose(self):  # noqa: ANN201
        yield DeckView(id="deck-view")
        yield SearchResults(id="search-results")
        yield WhichKey(id="which-key")
        yield StatusLine(id="status-line")
        yield CommandLine(id="command-line")

    def on_mount(self) -> None:
        if self.card_repo:
            self._state.resolved_cards = resolve_cards(
                self._state.buffer, self.card_repo,
            )
        self._sync_widgets()

    # ── Key dispatch ─────────────────────────────────────────────

    # Textual sends verbose names for symbols — normalize to what keymap expects
    _KEY_NORMALIZE: dict[str, str] = {
        "colon": ":",
        "slash": "/",
        "plus": "+",
        "minus": "-",
        "dollar_sign": "$",
        "question_mark": "?",
        "left_curly_bracket": "{",
        "right_curly_bracket": "}",
        "left_square_bracket": "[",
        "right_square_bracket": "]",
        "quotation_mark": '"',
        "apostrophe": "'",
        "full_stop": ".",
        "greater_than_sign": ">",
        "less_than_sign": "<",
        "at": "@",
        "exclamation_mark": "!",
        "underscore": "_",
    }

    def on_key(self, event: Key) -> None:
        # Let Ctrl+C through for emergency quit
        if event.key == "ctrl+c":
            return
        event.prevent_default()
        event.stop()
        # Normalize Textual's verbose key names to symbols
        key = self._KEY_NORMALIZE.get(event.key, event.key)
        # Resolve user remappings
        key = self.remapper.resolve(key, self._state.mode_mgr.current)
        result, action = self.keymap.feed(key)

        # Update which-key tooltip
        wk = self.query_one("#which-key", WhichKey)
        wk.mode = self._state.mode_mgr.current
        if result == KeyResult.PENDING:
            wk.pending_key = key
            wk.visible = True
            return
        wk.pending_key = ""
        wk.visible = self._state.mode_mgr.is_normal()

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
            hr = handle_command(s, action, self.registry, self.file_path)
            s.mode_mgr.force_normal()
            self.keymap.set_mode(Mode.NORMAL)
        elif action.action_type == "special":
            hr = self._dispatch_special(action)

        if hr:
            self._apply_handler_result(hr)
        self._sync_widgets()

    def _dispatch_special(self, action):  # noqa: ANN001, ANN202
        s = self._state
        if s.mode_mgr.is_insert():
            return handle_insert_special(s, action)
        if s.mode_mgr.is_command():
            cl = self.query_one("#command-line", CommandLine)
            cl.text = action.text or ""
            return None
        return handle_normal_special(s, action)

    def _apply_handler_result(self, hr) -> None:  # noqa: ANN001
        s = self._state
        if hr.exit_to_normal:
            s.mode_mgr.force_normal()
            self.keymap.set_mode(Mode.NORMAL)
            self.query_one("#search-results", SearchResults).visible = False
            self.query_one("#command-line", CommandLine).hide()
        if hr.enter_insert:
            s.mode_mgr.transition(Mode.INSERT)
            self.keymap.set_mode(Mode.INSERT)
            self.keymap.reset_text()
            cl = self.query_one("#command-line", CommandLine)
            cl.show("")
            cl.message = "Type card name to search..."
        if hr.enter_command:
            s.mode_mgr.transition(Mode.COMMAND)
            self.keymap.set_mode(Mode.COMMAND)
            self.keymap.reset_text()
            self.query_one("#command-line", CommandLine).show(":")
        if hr.enter_visual:
            s.mode_mgr.transition(hr.enter_visual)
            self.keymap.set_mode(hr.enter_visual)
        if hr.command_message:
            self.query_one("#command-line", CommandLine).set_message(hr.command_message)
        if hr.quit_requested:
            self.app.exit()
        if hr.search_query is not None:
            self._handle_search_action(hr.search_query)
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
            cl.prefix = "search: "
            cl.text = query
            if len(query) >= 2 and self.search_service:
                self._run_search(query)
            elif len(query) < 2:
                sr.visible = False

    def _confirm_insert(self) -> None:
        sr = self.query_one("#search-results", SearchResults)
        card = sr.get_selected()
        if card:
            s = self._state
            s.buffer = s.buffer.set_line(s.cursor.row, f"1 {card.name}")
            s.modified = True
            s.history.record(s.buffer, f"added {card.name}")
            if self.card_repo:
                s.resolved_cards = resolve_cards(s.buffer, self.card_repo)
        sr.visible = False
        self._state.mode_mgr.force_normal()
        self.keymap.set_mode(Mode.NORMAL)

    @work(thread=True)
    def _run_search(self, query: str) -> None:
        if self.search_service:
            results = self.search_service.fuzzy_search(query, limit=15)
            self.app.call_from_thread(self._update_search_results, results)

    def _update_search_results(self, results: list[Card]) -> None:
        sr = self.query_one("#search-results", SearchResults)
        sr.results = results
        sr.selected = 0
        sr.visible = bool(results)
        # Show top match as ghost completion in command line
        cl = self.query_one("#command-line", CommandLine)
        if results:
            cl.ghost = results[0].name
        else:
            cl.ghost = ""

    # ── Widget sync ──────────────────────────────────────────────

    def _sync_widgets(self) -> None:
        s = self._state
        dv = self.query_one("#deck-view", DeckView)
        dv.buffer = s.buffer
        dv.cursor = s.cursor
        dv.resolved_cards = s.resolved_cards

        sl = self.query_one("#status-line", StatusLine)
        sl.mode = s.mode_mgr.current
        sl.filename = self.file_path.name if self.file_path else "(new)"
        sl.modified = s.modified
        sl.card_count = count_cards(s.buffer)
        sl.cursor_line = s.cursor.row
        sl.total_lines = s.buffer.line_count()
