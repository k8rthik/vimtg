"""VimTGApp — Textual application entry point.

Creates services, loads a deck file, and pushes the appropriate screen:
- Greeter (alpha-nvim style) when launched with no file
- MainScreen when launched with a deck file path
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from vimtg.config.paths import db_path
from vimtg.config.settings import Settings, load_settings
from vimtg.config.settings_writer import save_settings
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.data.deck_repository import DeckRepository
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import CommandRegistry
from vimtg.services.search_service import SearchService
from vimtg.tui.theme import COLORS


class VimTGApp(App[None]):
    """Vim-powered MTG deck editor TUI."""

    BINDINGS = [("ctrl+c", "quit", "Force quit")]

    CSS = f"""
    Screen {{ layout: vertical; }}
    #deck-view {{ height: 1fr; }}
    #search-results {{ height: auto; max-height: 20; dock: bottom; }}
    #help-panel {{ height: auto; max-height: 24; dock: bottom; }}
    #which-key {{ height: auto; max-height: 6; dock: bottom; }}
    #status-line {{ height: 1; dock: bottom; background: {COLORS['bg']}; }}
    #command-line {{ height: 1; dock: bottom; background: {COLORS['bg']}; }}
    """
    TITLE = "vimtg"

    def __init__(self, deck_path: Path | None = None) -> None:
        super().__init__()
        self._deck_path = deck_path
        self._settings = load_settings()
        self._cmd_registry: CommandRegistry | None = None
        self._search_svc: SearchService | None = None
        self._card_repo: CardRepository | None = None
        self._deck_repo: DeckRepository | None = None
        self._db: Database | None = None

    @property
    def settings(self) -> Settings:
        return self._settings

    def update_settings(self, new_settings: Settings) -> None:
        """Persist settings and update runtime state."""
        save_settings(new_settings)
        self._settings = new_settings

    def on_mount(self) -> None:
        self._init_services()
        if self._deck_path and self._deck_path.exists():
            self._launch_editor(self._deck_path)
        else:
            self._launch_greeter()

    def on_unmount(self) -> None:
        """Release the database connection when the app shuts down."""
        if self._db is not None:
            self._db.close()
            self._db = None

    def _init_services(self) -> None:
        self._cmd_registry = CommandRegistry()
        register_all_commands(self._cmd_registry)
        self._deck_repo = DeckRepository()

        db_file = db_path()
        if db_file.exists():
            self._db = Database(db_file)
            self._db.initialize()
            self._card_repo = CardRepository(self._db)
            self._search_svc = SearchService(card_repo=self._card_repo)
        else:
            # Create DB for VCS even without card data
            db_file.parent.mkdir(parents=True, exist_ok=True)
            self._db = Database(db_file)
            self._db.initialize()

    def _launch_greeter(self) -> None:
        from vimtg.tui.screens.greeter import GreeterScreen

        recent = self._find_recent_decks()
        self.push_screen(GreeterScreen(recent_files=recent))

    def _launch_editor(self, file_path: Path | None = None) -> None:
        from vimtg.tui.screens.main_screen import MainScreen

        if file_path and file_path.exists():
            try:
                text = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                # Unreadable/binary file: fail loudly instead of silently
                # presenting an empty "New Deck" over a real file.
                self.exit(message=f"vimtg: cannot open {file_path}: {exc}")
                return
        else:
            text = "// New Deck\n\n"

        buffer = Buffer.from_text(text)
        save_fn = self._deck_repo.save if self._deck_repo else None
        self.push_screen(
            MainScreen(
                buffer=buffer,
                file_path=file_path,
                registry=self._cmd_registry,
                search_service=self._search_svc,
                card_repo=self._card_repo,
                save_fn=save_fn,
                settings=self._settings,
                db=self._db,
            )
        )

    def _find_recent_decks(self) -> list[Path]:
        """Find .deck files in current directory, sorted by modification time."""

        def _mtime(p: Path) -> float:
            try:
                return p.stat().st_mtime
            except OSError:  # deleted between glob and stat
                return 0.0

        decks = sorted(Path.cwd().glob("*.deck"), key=_mtime, reverse=True)
        return decks[:5]
