"""VimTGApp — Textual application entry point.

Creates services, loads a deck file, and pushes the appropriate screen:
- Greeter (alpha-nvim style) when launched with no file
- MainScreen when launched with a deck file path
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import httpx
from textual.app import App

from vimtg.config.paths import cache_dir, db_path
from vimtg.config.settings import Settings, load_settings
from vimtg.config.settings_writer import save_settings
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.data.deck_repository import DeckRepository
from vimtg.data.scryfall_sync import ScryfallSync, sync_is_due
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import CommandRegistry
from vimtg.services.deck_service import (
    scaffold_deck_body,
    scaffold_missing_metadata,
)
from vimtg.services.search_service import SearchService
from vimtg.tui.theme import COLORS

# How often a long-lived session re-checks whether cards are stale.
# Staleness itself is MAX_AGE_DAYS in scryfall_sync — this only bounds
# how quickly a running app notices.
AUTO_SYNC_CHECK_SECONDS = 3600


class VimTGApp(App[None]):
    """Vim-powered MTG deck editor TUI."""

    BINDINGS = [("ctrl+c", "quit", "Force quit")]

    CSS = f"""
    Screen {{ layout: vertical; }}
    #editor-area {{ height: 1fr; layout: horizontal; }}
    #deck-view {{ width: 1fr; height: 1fr; }}
    #deck-view-2 {{ width: 1fr; height: 1fr; }}
    #edhrec-panel {{ width: 1fr; height: 1fr; }}
    #analytics-panel {{ width: 1fr; height: 1fr; }}
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
            self.open_deck(self._deck_path)
        else:
            self.show_greeter()
        self._maybe_auto_sync()
        # Long-lived sessions re-check staleness periodically; the
        # worker group is exclusive so checks can never overlap.
        self.set_interval(AUTO_SYNC_CHECK_SECONDS, self._maybe_auto_sync)

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

    # ── Background card sync ─────────────────────────────────────

    def _maybe_auto_sync(self) -> None:
        """Start a background card sync when data is missing or stale.

        Gated by the auto_sync_cards setting and the VIMTG_NO_AUTOSYNC
        environment variable (set by the test suite so app tests never
        touch the network).
        """
        if os.environ.get("VIMTG_NO_AUTOSYNC"):
            return
        if not self._settings.auto_sync_cards:
            return
        if self._card_repo is not None and not sync_is_due(self._card_repo):
            return
        first_run = self._card_repo is None or self._card_repo.count() == 0
        if first_run:
            self.notify(
                "Downloading card database in background...",
                title="Card sync",
            )
        self._start_auto_sync()

    def _start_auto_sync(self) -> None:
        self.run_worker(
            self._auto_sync_worker,
            thread=True,
            group="card-sync",
            exclusive=True,
            description="Scryfall card sync",
        )

    def _auto_sync_worker(self) -> None:
        """Sync on a worker thread using its own DB connection.

        WAL mode allows this writer to run alongside the UI thread's
        reads; sharing one sqlite3 connection across threads would not
        be safe.
        """
        db = Database(db_path())
        try:
            db.initialize()
            syncer = ScryfallSync(
                card_repo=CardRepository(db), cache_dir=cache_dir()
            )
            count = syncer.sync()
        except (httpx.HTTPError, RuntimeError, OSError, sqlite3.Error) as exc:
            self.call_from_thread(
                self.notify,
                f"Card sync failed: {exc}",
                title="Card sync",
                severity="warning",
            )
            return
        finally:
            db.close()
        self.call_from_thread(self._finish_auto_sync, count)

    def _finish_auto_sync(self, count: int) -> None:
        """Adopt freshly synced card data on the UI thread."""
        from vimtg.tui.screens.main_screen import MainScreen

        if self._card_repo is None and self._db is not None:
            self._card_repo = CardRepository(self._db)
            self._search_svc = SearchService(card_repo=self._card_repo)
        screen = self.screen
        if (
            isinstance(screen, MainScreen)
            and self._card_repo is not None
            and self._search_svc is not None
        ):
            screen.attach_card_repo(self._card_repo, self._search_svc)
        self.notify(f"Card database updated ({count} cards)", title="Card sync")

    def show_greeter(self) -> None:
        """Public navigation: open the greeter screen."""
        from vimtg.tui.screens.greeter import GreeterScreen

        recent = self._find_recent_decks()
        self.push_screen(GreeterScreen(recent_files=recent))

    def open_deck(
        self, file_path: Path | None = None, initial_text: str | None = None
    ) -> None:
        """Public navigation: open a deck (or an empty buffer) in the editor.

        `initial_text` seeds the buffer with content that has no file
        yet (the greeter's import flow) — the buffer opens modified so
        quitting warns about the unsaved deck.
        """
        from vimtg.tui.screens.main_screen import MainScreen

        if initial_text is not None:
            text = scaffold_deck_body(scaffold_missing_metadata(initial_text))
        elif file_path and file_path.exists():
            try:
                text = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                # Unreadable/binary file: fail loudly instead of silently
                # presenting an empty "New Deck" over a real file.
                self.exit(message=f"vimtg: cannot open {file_path}: {exc}")
                return
            # Scaffold only fills the buffer — modified stays False, so
            # merely viewing a deck never forces a save.
            text = scaffold_deck_body(scaffold_missing_metadata(text))
        else:
            text = scaffold_deck_body(scaffold_missing_metadata(""))

        buffer = Buffer.from_text(text)
        save_fn = self._deck_repo.save if self._deck_repo else None
        screen = MainScreen(
            buffer=buffer,
            file_path=file_path,
            registry=self._cmd_registry,
            search_service=self._search_svc,
            card_repo=self._card_repo,
            save_fn=save_fn,
            settings=self._settings,
            db=self._db,
        )
        if initial_text is not None:
            screen._state.modified = True
        self.push_screen(screen)

    def _find_recent_decks(self) -> list[Path]:
        """Find .deck files in current directory, newest first."""
        repo = self._deck_repo or DeckRepository()
        return repo.list_decks(Path.cwd(), by_mtime=True)[:5]
