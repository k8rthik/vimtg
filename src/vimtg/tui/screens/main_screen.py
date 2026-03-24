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

from vimtg.config.settings import Settings
from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import CommandRegistry
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult
from vimtg.editor.keymaps import load_remapper
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.services.history_service import HistoryService
from vimtg.tui.key_translator import translate
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


def _card_type_section(type_line: str) -> str:
    """Map a card's type_line to its singular section name."""
    for t in ("Creature", "Instant", "Sorcery", "Enchantment", "Artifact", "Planeswalker", "Land"):
        if t in type_line:
            return t
    return "Other"


class MainScreen(Screen):
    """Primary editor screen: deck view, status line, command line."""

    def __init__(
        self,
        buffer: Buffer,
        file_path: Path | None = None,
        registry: CommandRegistry | None = None,
        search_service: SearchService | None = None,
        card_repo: CardRepository | None = None,
        settings: Settings | None = None,
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

    def on_key(self, event: Key) -> None:
        # Let Ctrl+C through for emergency quit
        if event.key == "ctrl+c":
            return
        event.prevent_default()
        event.stop()
        # Translate Textual key name → canonical vim key name
        key = translate(event.key)
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
            prev_settings = s.settings
            hr = handle_command(s, action, self.registry, self.file_path)
            if s.settings is not prev_settings:
                self._on_settings_saved(s.settings)
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
        if hr.open_config_screen:
            self._open_config()
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
        cl = self.query_one("#command-line", CommandLine)
        card = sr.get_selected()
        if card:
            s = self._state
            # Check for duplicate — increment quantity instead of adding new line
            duplicate_line = self._find_card_line(card.name)
            if duplicate_line is not None:
                qty = s.buffer.quantity_at(duplicate_line) or 0
                s.buffer = s.buffer.set_line(duplicate_line, f"{qty + 1} {card.name}")
                # Remove the blank line that 'o' inserted
                if s.buffer.get_line(s.cursor.row).text.strip() == "":
                    s.buffer, _ = s.buffer.delete_lines(s.cursor.row, s.cursor.row)
                s.cursor = s.cursor.move_to(min(duplicate_line, s.buffer.line_count() - 1), 0)
            else:
                # Find or create the right type section, then insert there
                insert_row = self._find_type_section_row(card, s.buffer)
                if insert_row is not None and insert_row != s.cursor.row:
                    # Remove the blank line 'o' inserted and place card in correct section
                    if s.buffer.get_line(s.cursor.row).text.strip() == "":
                        s.buffer, _ = s.buffer.delete_lines(s.cursor.row, s.cursor.row)
                        if insert_row > s.cursor.row:
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
            if s.buffer.get_line(s.cursor.row).text.strip() == "":
                s.buffer, _ = s.buffer.delete_lines(s.cursor.row, s.cursor.row)
                s.cursor = s.cursor.clamp(s.buffer.line_count() - 1)
            cl.hide()
        sr.visible = False
        self._state.mode_mgr.force_normal()
        self.keymap.set_mode(Mode.NORMAL)

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

    def _find_card_line(self, card_name: str) -> int | None:
        """Find existing line with this card name (for duplicate detection)."""
        buf = self._state.buffer
        for i in range(buf.line_count()):
            if buf.card_name_at(i) == card_name:
                return i
        return None

    def _find_type_section_row(self, card: Card, buf: Buffer) -> int | None:
        """Find the right row to insert a card based on its primary type.

        Uses singular type names: "Creature", "Instant", "Sorcery", etc.
        Creates the section header if it doesn't exist, with blank line separation.
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
                return insert_at

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
        self._state.buffer = buf
        return insert_at + 1

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

    def _cleanup_empty_sections(self) -> None:
        """Remove section headers that have no card lines below them."""
        from vimtg.editor.buffer import LineType

        buf = self._state.buffer
        to_delete: list[int] = []
        for i in range(buf.line_count()):
            bl = buf.get_line(i)
            if bl.line_type != LineType.SECTION_HEADER:
                continue
            # Check if next non-blank line is a card
            has_cards = False
            for j in range(i + 1, buf.line_count()):
                next_bl = buf.get_line(j)
                if next_bl.line_type == LineType.BLANK:
                    break
                if next_bl.line_type in (
                    LineType.CARD_ENTRY, LineType.SIDEBOARD_ENTRY, LineType.COMMANDER_ENTRY,
                ):
                    has_cards = True
                    break
                if next_bl.line_type in (
                    LineType.SECTION_HEADER, LineType.COMMENT, LineType.METADATA,
                ):
                    break
            if not has_cards:
                to_delete.append(i)
                # Also mark trailing blank line for deletion
                if i + 1 < buf.line_count() and buf.get_line(i + 1).line_type == LineType.BLANK:
                    to_delete.append(i + 1)

        # Delete in reverse to preserve indices
        for idx in reversed(to_delete):
            if idx < buf.line_count():
                buf, _ = buf.delete_lines(idx, idx)

        # Clean up consecutive blank lines
        cleaned_lines = []
        prev_blank = False
        for i in range(buf.line_count()):
            bl = buf.get_line(i)
            is_blank = bl.line_type == LineType.BLANK
            if is_blank and prev_blank:
                continue
            cleaned_lines.append(bl.text)
            prev_blank = is_blank

        from vimtg.editor.buffer import Buffer
        self._state.buffer = Buffer.from_text("\n".join(cleaned_lines) + "\n")
        self._state.cursor = self._state.cursor.clamp(self._state.buffer.line_count() - 1)

    def _sync_widgets(self) -> None:
        # Clean up empty sections before rendering
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
