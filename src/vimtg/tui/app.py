"""VimTGApp — Textual application entry point.

Creates services, loads a deck file, and pushes the MainScreen.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.buffer_cmds import register_buffer_commands
from vimtg.editor.command_handlers.deck_cmds import register_deck_commands
from vimtg.editor.command_handlers.help_cmd import register_help_commands
from vimtg.editor.command_handlers.sort import register_sort_commands
from vimtg.editor.commands import CommandRegistry
from vimtg.services.search_service import SearchService
from vimtg.tui.theme import COLORS


class VimTGApp(App):
    """Vim-powered MTG deck editor TUI."""

    CSS = f"""
    Screen {{ layout: vertical; }}
    #deck-view {{ height: 1fr; }}
    #search-results {{ height: auto; max-height: 20; dock: bottom; }}
    #status-line {{ height: 1; dock: bottom; background: {COLORS['bg']}; }}
    #command-line {{ height: 1; dock: bottom; background: {COLORS['bg']}; }}
    """
    TITLE = "vimtg"

    def __init__(self, deck_path: Path | None = None) -> None:
        super().__init__()
        self._deck_path = deck_path

    def on_mount(self) -> None:
        if self._deck_path and self._deck_path.exists():
            text = self._deck_path.read_text(encoding="utf-8")
        else:
            text = "// New Deck\n\n"

        buffer = Buffer.from_text(text)

        registry = CommandRegistry()
        register_buffer_commands(registry)
        register_sort_commands(registry)
        register_deck_commands(registry)
        register_help_commands(registry)

        search_svc = None
        card_repo = None
        db_file = db_path()
        if db_file.exists():
            db = Database(db_file)
            db.initialize()
            card_repo = CardRepository(db)
            search_svc = SearchService(card_repo=card_repo)

        from vimtg.tui.screens.main_screen import MainScreen

        self.push_screen(
            MainScreen(
                buffer=buffer,
                file_path=self._deck_path,
                registry=registry,
                search_service=search_svc,
                card_repo=card_repo,
            )
        )
