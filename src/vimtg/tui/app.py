"""VimTGApp — Textual application entry point.

Creates services, loads a deck file, and pushes the appropriate screen:
- Greeter (alpha-nvim style) when launched with no file
- MainScreen when launched with a deck file path
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import signal
from collections import deque
from collections.abc import Callable
from functools import partial
from pathlib import Path
from types import FrameType
from typing import Any

from rich.console import RenderableType
from textual.app import App
from textual.events import Resize
from textual.notifications import SeverityLevel

from vimtg.config import app_state
from vimtg.config.paths import cache_dir, db_path
from vimtg.config.settings import Settings, load_settings_checked
from vimtg.config.settings_writer import save_settings
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.data.db_recovery import open_database
from vimtg.data.deck_repository import DeckRepository
from vimtg.data.file_io import ABSENT, FileStamp, file_stamp
from vimtg.data.scryfall_sync import (
    NO_CARD_DATA,
    ScryfallSync,
    card_data_badge,
    describe_sync_error,
    sync_is_due,
)
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import CommandRegistry
from vimtg.services.deck_service import (
    Scaffold,
    scaffold_deck_body,
    scaffold_metadata,
    strip_unused_scaffold,
)
from vimtg.services.recovery import RecoveryCopy
from vimtg.services.search_service import SearchService
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.command_line import MESSAGE_HISTORY

# How often a long-lived session re-checks whether cards are stale.
# Staleness itself is MAX_AGE_DAYS in scryfall_sync — this only bounds
# how quickly a running app notices.
AUTO_SYNC_CHECK_SECONDS = 3600

# Decks offered by the greeter's Recent section and `r` list
RECENT_LIMIT = 9

SignalHandler = Callable[[int, FrameType | None], Any] | int | None

# Signals that end the session from outside: a closed terminal or a
# dropped SSH connection (SIGHUP), or a polite kill (SIGTERM). Each
# saves unsaved work as a recovery copy before the app exits.
TERMINATING_SIGNALS: tuple[signal.Signals, ...] = tuple(
    sig for name in ("SIGHUP", "SIGTERM")
    if (sig := getattr(signal, name, None)) is not None
)

_NOTIFY_TAKES_MARKUP = "markup" in inspect.signature(App.notify).parameters


class VimTGApp(App[None]):
    """Vim-powered MTG deck editor TUI."""

    CSS = f"""
    Screen {{ layout: vertical; }}
    #editor-area {{ height: 1fr; layout: horizontal; }}
    #deck-view {{ width: 1fr; height: 1fr; }}
    #edhrec-panel {{ width: 1fr; height: 1fr; }}
    #analytics-panel {{ width: 1fr; height: 1fr; }}
    #search-results {{ height: auto; max-height: 50%; dock: bottom; }}
    #help-panel {{ height: auto; max-height: 60%; dock: bottom; }}
    #tips-panel {{ height: auto; dock: bottom; background: {COLORS['cursor_bg']}; }}
    #which-key {{ height: auto; max-height: 6; dock: bottom; }}
    #status-line {{ height: 1; dock: bottom; background: {COLORS['bg']}; }}
    #command-line {{ height: 1; dock: bottom; background: {COLORS['bg']}; }}
    """
    TITLE = "vimtg"

    def __init__(self, deck_path: Path | None = None) -> None:
        super().__init__()
        self._deck_path = deck_path
        self._settings, self._config_warning = load_settings_checked()
        self._cmd_registry: CommandRegistry | None = None
        self._search_svc: SearchService | None = None
        self._card_repo: CardRepository | None = None
        self._deck_repo: DeckRepository | None = None
        self._db: Database | None = None
        self._sync_running = False
        self._sync_progress = ""  # status-line text while a sync runs
        self._card_badge: tuple[str, bool] = (NO_CARD_DATA, True)
        self._db_warning = ""  # set when the database had to be recovered
        # (signal, the handler it had before) for each one routed here
        self._signals_installed: list[tuple[signal.Signals, SignalHandler]] = []
        # (is_error, text) of every message and pop-up notice this session,
        # oldest first: shared by every editor's command line for :messages
        self.message_log: deque[tuple[bool, str]] = deque(maxlen=MESSAGE_HISTORY)

    @property
    def settings(self) -> Settings:
        return self._settings

    def update_settings(self, new_settings: Settings) -> None:
        """Update runtime state, then persist settings.

        Raises SettingsWriteError / OSError when config.toml cannot be
        written; the new settings still apply for this session.
        """
        self._settings = new_settings
        save_settings(new_settings)

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: SeverityLevel = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        """Show a pop-up notice and keep it for :messages."""
        # A notice repeating the message just put on the command line
        # (which recorded it already) is not logged twice
        last = self.message_log[-1][1] if self.message_log else ""
        if last.removeprefix("E: ") != message.removeprefix("E: "):
            text = f"{title}: {message}" if title else message
            self.message_log.append((severity == "error", text))
        if _NOTIFY_TAKES_MARKUP:
            super().notify(
                message, title=title, severity=severity, timeout=timeout, markup=markup,
            )
        else:  # Textual < 2.1 has no markup parameter
            super().notify(message, title=title, severity=severity, timeout=timeout)

    def on_mount(self) -> None:
        self._install_signal_handlers()
        self._init_services()
        if self._db_warning:
            self.notify(
                self._db_warning, title="Card database", severity="error",
                timeout=30,
            )
        if self._config_warning:
            self.notify(
                self._config_warning, title="Config", severity="warning", timeout=15,
            )
        if self._deck_path is not None:
            # A path that does not exist yet opens an empty deck bound
            # to it, created on the first :w (like `vim newfile`).
            self.open_deck(self._deck_path)
        else:
            self.show_greeter()
        self._check_terminal_size(*self.size)
        self._maybe_auto_sync()
        # Long-lived sessions re-check staleness periodically; the
        # worker group is exclusive so checks can never overlap.
        self.set_interval(AUTO_SYNC_CHECK_SECONDS, self._maybe_auto_sync)

    def on_resize(self, event: Resize) -> None:
        # self.size lags the event by a timer tick; the event is current
        self._check_terminal_size(event.size.width, event.size.height)

    def _check_terminal_size(self, width: int, height: int) -> None:
        """Below MIN_WIDTH x MIN_HEIGHT nothing is drawn but a notice:
        squeezed layouts garble, and keys typed blind do damage."""
        from vimtg.tui.screens.too_small import TooSmallScreen, fits

        top = self.screen_stack[-1] if self.screen_stack else None
        if not fits(width, height):
            if isinstance(top, TooSmallScreen):
                top.show_size(width, height)
            else:
                self.push_screen(TooSmallScreen(width, height))
        elif isinstance(top, TooSmallScreen):
            self.pop_screen()

    def _handle_exception(self, error: Exception) -> None:
        """Last-resort net for errors outside the editor's key path.

        Textual exits on an unhandled exception; before it does, every
        open editor's buffer is written to the recovery dir so the next
        open of that deck can offer :recover.
        """
        from vimtg.tui.screens.main_screen import MainScreen

        for screen in self.screen_stack:
            if isinstance(screen, MainScreen):
                # never mask the original error
                with contextlib.suppress(Exception):
                    screen.save_recovery(error)
        super()._handle_exception(error)

    # ── Unsaved work at exit ─────────────────────────────────────

    def preserve_unsaved(self) -> None:
        """Save every open editor's unsaved changes as a recovery copy.

        Runs on every way out — :q (with confirm_quit off), Ctrl-Q,
        SIGHUP, SIGTERM — and never raises: leaving must not
        fail because a copy could not be written.
        """
        from vimtg.tui.screens.main_screen import MainScreen

        for screen in self.screen_stack:
            if isinstance(screen, MainScreen):
                with contextlib.suppress(Exception):
                    screen.preserve_unsaved()

    def exit(
        self,
        result: None = None,
        return_code: int = 0,
        message: RenderableType | None = None,
    ) -> None:
        self.preserve_unsaved()
        super().exit(result, return_code, message)

    def _install_signal_handlers(self) -> None:
        """Route SIGHUP/SIGTERM through the event loop to a clean exit
        that saves first. Unsupported platforms (Windows) skip it."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        for sig in TERMINATING_SIGNALS:
            previous = signal.getsignal(sig)
            try:
                loop.add_signal_handler(sig, self.handle_terminate_signal, sig)
            except (NotImplementedError, RuntimeError, ValueError):
                continue
            self._signals_installed.append((sig, previous))

    def _remove_signal_handlers(self) -> None:
        """Put back the handlers the process had before the app ran."""
        with contextlib.suppress(RuntimeError):
            loop = asyncio.get_running_loop()
            for sig, _previous in self._signals_installed:
                with contextlib.suppress(Exception):
                    loop.remove_signal_handler(sig)
        for sig, previous in self._signals_installed:
            if previous is not None:
                with contextlib.suppress(Exception):
                    signal.signal(sig, previous)
        self._signals_installed = []

    def handle_terminate_signal(self, sig: int) -> None:
        """SIGHUP / SIGTERM: keep unsaved work, then exit (128 + signal,
        the shell's convention for a signal death)."""
        self.preserve_unsaved()
        self.exit(return_code=128 + int(sig))

    def on_unmount(self) -> None:
        """Release the database connection when the app shuts down."""
        self._remove_signal_handlers()
        if self._db is not None:
            self._db.close()
            self._db = None

    def _init_services(self) -> None:
        self._cmd_registry = CommandRegistry()
        register_all_commands(self._cmd_registry)
        self._deck_repo = DeckRepository()

        db_file = db_path()
        had_db = db_file.exists()
        # Integrity-checked open: a damaged file is backed up and rebuilt
        # (deck history salvaged) instead of blocking the launch
        opened = open_database(db_file)
        self._db = opened.db
        self._db_warning = opened.warning
        if had_db and not opened.warning:
            self._card_repo = CardRepository(self._db)
            self._search_svc = SearchService(card_repo=self._card_repo)
        elif opened.recovered is not None:
            # Rebuilt without cards: searchable as soon as a :sync lands
            self._card_repo = CardRepository(self._db)
            self._search_svc = SearchService(card_repo=self._card_repo)
        self._card_badge = self._compute_card_badge()

    # ── Card data status ─────────────────────────────────────────

    def _compute_card_badge(self) -> tuple[str, bool]:
        if self._card_repo is None:
            return NO_CARD_DATA, True
        try:
            return card_data_badge(
                self._card_repo.count(), self._card_repo.get_last_sync()
            )
        except Exception:  # noqa: BLE001 — a status readout must not crash
            return NO_CARD_DATA, True

    def card_data_status(self) -> tuple[str, bool]:
        """(status-line text, needs attention) for the card data: sync
        progress while a sync runs, else what the database holds."""
        if self._sync_running:
            return f"syncing card data{self._sync_progress}", False
        return self._card_badge

    def has_card_data(self) -> bool:
        return self._card_badge[0] != NO_CARD_DATA

    @property
    def card_sync_running(self) -> bool:
        return self._sync_running

    @property
    def card_sync_progress(self) -> str:
        """How far the running sync is ('downloading 40%'), '' when unknown."""
        return self._sync_progress.strip() if self._sync_running else ""

    def _refresh_card_status(self) -> None:
        """Push the card data status to every open editor and greeter."""
        from vimtg.tui.screens.greeter import GreeterScreen
        from vimtg.tui.screens.main_screen import MainScreen

        status = self.card_data_status()
        for screen in self.screen_stack:
            if isinstance(screen, MainScreen | GreeterScreen):
                screen.set_card_data_status(*status)

    # ── Background card sync ─────────────────────────────────────

    def _maybe_auto_sync(self) -> None:
        """Start a background card sync when data is missing or stale.

        Gated by the auto_sync_cards setting and the VIMTG_NO_AUTOSYNC
        environment variable (set by the test suite so app tests never
        touch the network).
        """
        if os.environ.get("VIMTG_NO_AUTOSYNC"):
            return
        if not self._settings.auto_sync_cards or self._sync_running:
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

    def start_card_sync(self, force: bool = False) -> str:
        """:sync — start a background sync; returns the status message."""
        if self._sync_running:
            return "Card sync already running (progress in the status line)"
        self._start_auto_sync(force)
        return "Syncing card data in the background (progress in the status line)"

    def _start_auto_sync(self, force: bool = False) -> None:
        self._sync_running = True
        self._sync_progress = ""
        self._refresh_card_status()
        self.run_worker(
            partial(self._auto_sync_worker, force),
            thread=True,
            group="card-sync",
            description="Scryfall card sync",
        )

    def _auto_sync_worker(self, force: bool = False) -> None:
        """Sync on a worker thread using its own DB connection.

        WAL mode allows this writer to run alongside the UI thread's
        reads; sharing one sqlite3 connection across threads would not
        be safe. Progress reaches the status line only when its text
        changes, so the UI thread is not flooded.
        """
        shown = [""]

        def _progress(phase: str, current: int, total: int) -> None:
            text = sync_progress_text(phase, current, total)
            if text != shown[0]:
                shown[0] = text
                self.call_from_thread(self._set_sync_progress, text)

        db = Database(db_path())
        try:
            db.initialize()
            syncer = ScryfallSync(
                card_repo=CardRepository(db), cache_dir=cache_dir()
            )
            count = syncer.sync(force=force, progress=_progress)
        except Exception as exc:  # noqa: BLE001 — any failure is reported, never fatal
            self.call_from_thread(
                self._fail_auto_sync,
                describe_sync_error(exc, retry="run :sync to retry"),
            )
            return
        finally:
            db.close()
        tags_note = (
            describe_sync_error(syncer.tags_error, retry="run :sync to retry")
            if syncer.tags_error is not None else ""
        )
        self.call_from_thread(self._finish_auto_sync, count, tags_note)

    def _set_sync_progress(self, text: str) -> None:
        self._sync_progress = f" {text}" if text else ""
        self._refresh_card_status()

    def _fail_auto_sync(self, message: str) -> None:
        from vimtg.tui.screens.main_screen import MainScreen

        self._sync_running = False
        self._sync_progress = ""
        self._refresh_card_status()
        if isinstance(self.screen, MainScreen):
            self.screen.show_message(f"E: Card sync failed: {message}", error=True)
        self.notify(
            f"Card sync failed: {message}", title="Card sync",
            severity="warning", timeout=10,
        )

    @property
    def card_repo(self) -> CardRepository | None:
        """The card database, or None before one exists (the greeter's
        imports resolve names against it)."""
        return self._card_repo

    def adopt_card_data(self) -> None:
        """Use freshly synced card data everywhere (the UI thread's own
        connection sees the worker's committed rows)."""
        from vimtg.tui.screens.main_screen import MainScreen

        if self._card_repo is None and self._db is not None:
            self._card_repo = CardRepository(self._db)
            self._search_svc = SearchService(card_repo=self._card_repo)
        if self._card_repo is not None and self._search_svc is not None:
            for screen in self.screen_stack:
                if isinstance(screen, MainScreen):
                    screen.attach_card_repo(self._card_repo, self._search_svc)
        self._card_badge = self._compute_card_badge()
        self._refresh_card_status()

    def _finish_auto_sync(self, count: int, tags_note: str = "") -> None:
        """Adopt freshly synced card data on the UI thread. ``tags_note``
        says why the oracle tags were skipped, when they were."""
        self._sync_running = False
        self._sync_progress = ""
        self.adopt_card_data()
        message = f"Card database updated ({count} cards)"
        if tags_note:
            message += f"; oracle tags skipped: {tags_note}"
        self.notify(message, title="Card sync")

    def show_greeter(self) -> None:
        """Public navigation: open the greeter screen."""
        from vimtg.tui.screens.greeter import GreeterScreen

        recent = self._find_recent_decks()
        self.push_screen(GreeterScreen(recent_files=recent))

    def open_deck(
        self,
        file_path: Path | None = None,
        initial_text: str | None = None,
        recovery: RecoveryCopy | None = None,
        message: str = "",
    ) -> None:
        """Public navigation: open a deck (or an empty buffer) in the editor.

        `initial_text` seeds the buffer with content that has no file
        yet (the greeter's import flow) — the buffer opens modified so
        quitting warns about the unsaved deck. With `recovery`, the text
        is that recovery copy's: the editor takes the copy over (a save
        or :q! removes it) instead of offering it again. `message` is
        shown on the editor's command line once it opens (an import's
        summary).
        """
        from vimtg.tui.screens.main_screen import MainScreen

        stamp: FileStamp | None = None
        if initial_text is not None:
            text, added = scaffold_metadata(initial_text)
            if file_path is not None:
                stamp = file_stamp(file_path)  # ABSENT when it is gone
        elif file_path and file_path.exists():
            # Stamp before reading: a write racing the read then shows
            # up as a change (a spurious warning, never a lost edit).
            stamp = file_stamp(file_path)
            try:
                raw = file_path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as exc:
                # Unreadable/binary file: fail loudly instead of silently
                # presenting an empty "New Deck" over a real file.
                self.exit(message=f"vimtg: cannot open {file_path}: {exc}")
                return
            # Scaffold only fills the buffer — modified stays False, so
            # merely viewing a deck never forces a save.
            text, added = scaffold_metadata(raw)
            app_state.remember_deck(file_path)
        else:
            text, added = scaffold_metadata("")
            if file_path is not None:
                stamp = ABSENT  # a file appearing before :w is a change too
        text = scaffold_deck_body(text)

        buffer = Buffer.from_text(text)
        screen = MainScreen(
            buffer=buffer,
            file_path=file_path,
            registry=self._cmd_registry,
            search_service=self._search_svc,
            card_repo=self._card_repo,
            save_fn=self._make_save_fn(added),
            settings=self._settings,
            db=self._db,
            disk_stamp=stamp,
            # An import arrives with its cards; anything else that is
            # still an empty, unnamed/format-less deck asks for both
            prompt_new_deck=initial_text is None,
            recovery_id=recovery.buffer_id if recovery is not None else None,
            recovery_copy=recovery.copy if recovery is not None else None,
        )
        if initial_text is not None:
            screen._state.modified = True
            screen._state.clean_text = None  # never saved: undo stays dirty
        self.push_screen(screen)
        if message:
            self.call_after_refresh(screen.show_message, message)

    def _make_save_fn(self, added: Scaffold) -> Callable[[Path, str], None] | None:
        """The editor's writer: drops scaffold lines still empty (the
        file never had them), then remembers the deck as recent."""
        repo = self._deck_repo
        if repo is None:
            return None

        def save(path: Path, text: str) -> None:
            repo.save(path, strip_unused_scaffold(text, added))
            app_state.remember_deck(path)

        return save

    def _find_recent_decks(self) -> list[Path]:
        """Recently opened decks from any directory, then the newest
        .deck files in the current directory — no duplicates."""
        repo = self._deck_repo or DeckRepository()
        local = repo.list_decks(Path.cwd(), by_mtime=True)
        seen: set[Path] = set()
        recent: list[Path] = []
        for path in [*app_state.recent_decks(), *local]:
            key = path.resolve()
            if key not in seen:
                seen.add(key)
                recent.append(path)
        return recent[:RECENT_LIMIT]


def sync_progress_text(phase: str, current: int, total: int) -> str:
    """Short status-line text for a sync progress callback."""
    label = "downloading" if phase.startswith("download") else "loading"
    if phase.endswith("_tags"):
        label += " tags"
    if total > 0:
        return f"{label} {min(100, current * 100 // total)}%"
    return f"{label}..."
