"""VimTGApp — Textual application entry point.

Creates services, loads a deck file, and pushes the appropriate screen:
- Greeter (alpha-nvim style) when launched with no file
- MainScreen when launched with a deck file path
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.buffer_cmds import register_buffer_commands
from vimtg.editor.command_handlers.config_cmds import register_config_commands
from vimtg.editor.command_handlers.deck_cmds import register_deck_commands
from vimtg.editor.command_handlers.help_cmd import register_help_commands
from vimtg.editor.command_handlers.sort import register_sort_commands
from vimtg.editor.commands import CommandRegistry
from vimtg.services.search_service import SearchService
from vimtg.tui.theme import COLORS


class VimTGApp(App):
    """Vim-powered MTG deck editor TUI."""

    BINDINGS = [("ctrl+c", "quit", "Force quit")]

    CSS = f"""
    Screen {{ layout: vertical; }}
    #deck-view {{ height: 1fr; }}
    #search-results {{ height: auto; max-height: 20; dock: bottom; }}
    #which-key {{ height: auto; max-height: 6; dock: bottom; }}
    #status-line {{ height: 1; dock: bottom; background: {COLORS['bg']}; }}
    #command-line {{ height: 1; dock: bottom; background: {COLORS['bg']}; }}
    """
    TITLE = "vimtg"

    def __init__(self, deck_path: Path | None = None) -> None:
        super().__init__()
        self._deck_path = deck_path
        self._cmd_registry: CommandRegistry | None = None
        self._search_svc: SearchService | None = None
        self._card_repo: CardRepository | None = None

    def on_mount(self) -> None:
        self._init_services()
        if self._deck_path and self._deck_path.exists():
            self._launch_editor(self._deck_path)
        else:
            self._launch_greeter()

    def _init_services(self) -> None:
        self._cmd_registry = CommandRegistry()
        register_buffer_commands(self._cmd_registry)
        register_sort_commands(self._cmd_registry)
        register_deck_commands(self._cmd_registry)
        register_help_commands(self._cmd_registry)
        register_config_commands(self._cmd_registry)

        db_file = db_path()
        if db_file.exists():
            db = Database(db_file)
            db.initialize()
            self._card_repo = CardRepository(db)
            self._search_svc = SearchService(card_repo=self._card_repo)

    def _launch_greeter(self) -> None:
        from vimtg.tui.screens.greeter import GreeterScreen

        recent = self._find_recent_decks()
        self.push_screen(GreeterScreen(recent_files=recent))

    def _launch_editor(self, file_path: Path | None = None) -> None:
        from vimtg.tui.screens.main_screen import MainScreen

        if file_path and file_path.exists():
            text = file_path.read_text(encoding="utf-8")
        else:
            text = "// New Deck\n\n"

        buffer = Buffer.from_text(text)
        self.push_screen(
            MainScreen(
                buffer=buffer,
                file_path=file_path,
                registry=self._cmd_registry,
                search_service=self._search_svc,
                card_repo=self._card_repo,
            )
        )

    def _find_recent_decks(self) -> list[Path]:
        """Find .deck files in current directory, sorted by modification time."""
        cwd = Path.cwd()
        decks = sorted(cwd.glob("*.deck"), key=lambda p: p.stat().st_mtime, reverse=True)
        return decks[:5]
