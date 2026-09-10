"""Greeter screen — shown when vimtg launches with no file argument.

Inspired by alpha-nvim: centered ASCII logo, recent files, and quick actions.
Supports four modes: menu (default), help, file browser, and recent files browser.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.events import Key, Paste
from textual.screen import Screen
from textual.widgets import Static

from vimtg import __version__
from vimtg.editor.help_text import HELP_OVERVIEW, is_section_header
from vimtg.services.deck_sources import (
    DeckSourceError,
    fetch_deck,
    is_deck_url,
    stamped_deck,
)
from vimtg.tui.key_translator import translate
from vimtg.tui.keys import PENDING, VimNav
from vimtg.tui.theme import COLORS

LOGO_LINES = [
    "       _           _        ",
    "__   _(_)_ __ ___ | |_ __ _ ",
    "\\ \\ / / | '_ ` _ \\| __/ _` |",
    " \\ V /| | | | | | | || (_| |",
    "  \\_/ |_|_| |_| |_|\\__\\__, |",
    "                      |___/ ",
]

ACTIONS = [
    ("n", "New deck"),
    ("e", "Open file"),
    ("i", "Import deck"),
    ("s", "Sync cards"),
    ("r", "Recent files"),
    ("?", "Help"),
    ("q", "Quit"),
]

_DIM = f"dim {COLORS['comment']}"
_SELECTED_STYLE = f"on {COLORS['cursor_bg']}"


class GreeterMode(Enum):
    """Greeter view modes — separate from editor modes."""

    MENU = "menu"
    HELP = "help"
    FILES = "files"
    RECENT = "recent"
    IMPORT = "import"


class GreeterView(Static):
    """Centered greeter content with mode-based rendering."""

    def __init__(
        self,
        recent_files: list[Path] | None = None,
        all_files: list[Path] | None = None,
    ) -> None:
        super().__init__()
        self._recent = recent_files or []
        self._all_files = all_files or []
        self._mode = GreeterMode.MENU
        self._cursor = 0
        self._status = ""
        self._input = ""  # import prompt text (path or URL)
        self.nav = VimNav()
        self._help_nav = VimNav()
        self._help_offset = 0

    def render(self) -> Text:
        if self._mode == GreeterMode.HELP:
            return self._render_help()
        if self._mode == GreeterMode.FILES:
            return self._render_file_list(self._all_files, "Open File")
        if self._mode == GreeterMode.RECENT:
            return self._render_file_list(self._recent, "Recent Files")
        if self._mode == GreeterMode.IMPORT:
            return self._render_import()
        return self._render_menu()

    # -- Render methods ------------------------------------------------

    def _render_menu(self) -> Text:
        t = Text()

        for line in LOGO_LINES:
            logo_line = Text(f"  {line}\n")
            logo_line.stylize(f"bold {COLORS['mana_red']}")
            t.append_text(logo_line)
        t.append("\n")

        t.append("  Vim-powered MTG deck builder\n", style=_DIM)
        t.append(f"  v{__version__}\n", style=_DIM)
        t.append("\n")

        for key, label in ACTIONS:
            t.append(f"  [{key}]", style=f"bold {COLORS['quantity']}")
            t.append(f"  {label}\n", style="")
        t.append("\n")

        if self._recent:
            t.append("  Recent\n", style=f"bold {COLORS['mana_blue']}")
            for i, path in enumerate(self._recent[:5]):
                num = i + 1
                t.append(f"  [{num}]", style=f"bold {COLORS['quantity']}")
                t.append(f"  {path.name}\n", style="dim")
            t.append("\n")

        if self._status:
            t.append(f"  {self._status}\n", style=f"bold {COLORS['mana_green']}")

        t.append("  Press a highlighted key to continue\n", style=_DIM)
        return t

    def _render_help(self) -> Text:
        t = Text()
        t.append("  vimtg Help\n", style=f"bold {COLORS['mana_blue']}")
        t.append("  " + "=" * 40 + "\n\n", style=_DIM)

        lines = HELP_OVERVIEW.split("\n")
        start = self._help_offset
        viewport = self.list_viewport() if self.size.height > 0 else len(lines)
        for line in lines[start:start + viewport]:
            if is_section_header(line):
                t.append(f"  {line}\n", style=f"bold {COLORS['mana_green']}")
            else:
                t.append(f"  {line}\n", style="")

        t.append("\n")
        t.append("  j/k scroll  gg/G top/bottom  ?/Esc/q return\n", style=_DIM)
        return t

    def _render_import(self) -> Text:
        t = Text()
        t.append("  Import Deck\n", style=f"bold {COLORS['mana_blue']}")
        t.append("  " + "-" * 40 + "\n\n", style=_DIM)
        t.append("  Paste a deck URL or type a file path:\n\n", style="")
        t.append("  > ", style=f"bold {COLORS['quantity']}")
        t.append(self._input)
        t.append("▏\n\n", style=_DIM)
        t.append(
            "  URLs: Moxfield, Archidekt, ManaBox, Deckstats,\n"
            "        TappedOut, MTGGoldfish\n",
            style=_DIM,
        )
        t.append(
            "  Files: vimtg, MTGO text/.dek, Arena, Moxfield/Archidekt CSV\n",
            style=_DIM,
        )
        t.append("\n")
        if self._status:
            style = (
                f"bold {COLORS['error']}"
                if self._status.startswith("E:")
                else f"bold {COLORS['mana_green']}"
            )
            t.append(f"  {self._status}\n\n", style=style)
        t.append("  Enter import  Escape back\n", style=_DIM)
        return t

    def _render_file_list(self, files: list[Path], title: str) -> Text:
        t = Text()
        t.append(f"  {title}\n", style=f"bold {COLORS['mana_blue']}")
        t.append("  " + "-" * 40 + "\n\n", style=_DIM)

        if not files:
            t.append("  No .deck files found\n", style=_DIM)
            t.append("\n")
            t.append("  Press n to create a new deck\n", style=_DIM)
            t.append("  Press Escape to return\n", style=_DIM)
            return t

        for i, path in enumerate(files):
            is_selected = i == self._cursor
            indicator = ">" if is_selected else " "

            line = Text()
            line.append(
                f"  {indicator} ",
                style=f"{COLORS['quantity']}" if is_selected else "",
            )
            line.append(
                f"{path.name}",
                style="bold" if is_selected else "",
            )

            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
                line.append(f"  {mtime}", style="dim")
            except OSError:
                pass

            if is_selected:
                line.stylize(_SELECTED_STYLE)

            t.append_text(line)
            t.append("\n")

        t.append("\n")
        t.append(
            "  j/k navigate  gg/G top/bottom  Enter open  n new deck  Esc/q back\n",
            style=_DIM,
        )
        return t

    # -- Cursor navigation ---------------------------------------------

    def set_mode(self, mode: GreeterMode) -> None:
        self._mode = mode
        self._cursor = 0

    def list_viewport(self) -> int:
        return max(1, (self.size.height or 24) - 8)

    def navigate(self, file_list: list[Path], step: int | str) -> None:
        """Apply a shared navigation step (line delta, "home", "end")."""
        if not file_list:
            self._cursor = 0
            return
        last = len(file_list) - 1
        if step == "home":
            self._cursor = 0
        elif step == "end":
            self._cursor = last
        else:
            self._cursor = max(0, min(self._cursor + int(step), last))

    def _active_list(self) -> list[Path]:
        if self._mode == GreeterMode.FILES:
            return self._all_files
        if self._mode == GreeterMode.RECENT:
            return self._recent
        return []

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if self._mode in (GreeterMode.FILES, GreeterMode.RECENT):
            event.stop()
            self.navigate(self._active_list(), 1)
            self.refresh()
        elif self._mode == GreeterMode.HELP:
            event.stop()
            self.scroll_help_by_key("ctrl_d")
            self.refresh()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if self._mode in (GreeterMode.FILES, GreeterMode.RECENT):
            event.stop()
            self.navigate(self._active_list(), -1)
            self.refresh()
        elif self._mode == GreeterMode.HELP:
            event.stop()
            self.scroll_help_by_key("ctrl_u")
            self.refresh()

    def scroll_help_by_key(self, key: str) -> bool:
        """Scroll the inline help overview; False when `key` is not a nav key."""
        lines = HELP_OVERVIEW.count("\n") + 1
        viewport = self.list_viewport()
        step = self._help_nav.feed(key, viewport)
        if step is None:
            return False
        if step == PENDING:
            return True
        max_offset = max(0, lines - viewport)
        if step == "home":
            self._help_offset = 0
        elif step == "end":
            self._help_offset = max_offset
        else:
            self._help_offset = max(0, min(self._help_offset + int(step), max_offset))
        return True

    def select_next(self, file_list: list[Path]) -> None:
        if file_list:
            self._cursor = min(self._cursor + 1, len(file_list) - 1)

    def select_prev(self) -> None:
        self._cursor = max(self._cursor - 1, 0)

    def get_selected(self, file_list: list[Path]) -> Path | None:
        if 0 <= self._cursor < len(file_list):
            return file_list[self._cursor]
        return None


class GreeterScreen(Screen[None]):
    """Startup screen with logo, actions, and recent files."""

    CSS = f"""
    GreeterView {{
        height: 1fr;
        content-align: center middle;
        background: {COLORS['bg']};
    }}
    """

    def __init__(self, recent_files: list[Path] | None = None) -> None:
        super().__init__()
        self._recent = recent_files or []
        self._all_files = _find_all_decks()
        self._sync_running = False

    def compose(self) -> ComposeResult:
        yield GreeterView(recent_files=self._recent, all_files=self._all_files)

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+c":
            self.app.exit()
            return
        event.prevent_default()
        event.stop()

        key = translate(event.key)
        gv = self.query_one(GreeterView)

        if gv._mode == GreeterMode.MENU:
            self._handle_menu_key(key, gv)
        elif gv._mode == GreeterMode.HELP:
            self._handle_help_key(key, gv)
        elif gv._mode == GreeterMode.IMPORT:
            self._handle_import_key(key, gv)
        elif gv._mode in (GreeterMode.FILES, GreeterMode.RECENT):
            file_list = (
                self._all_files
                if gv._mode == GreeterMode.FILES
                else self._recent
            )
            self._handle_file_list_key(key, gv, file_list)

    def _handle_menu_key(self, key: str, gv: GreeterView) -> None:
        if key == "n":
            self._open_editor(file_path=None)
        elif key == "e":
            gv.set_mode(GreeterMode.FILES)
            gv.refresh()
        elif key == "i":
            gv.set_mode(GreeterMode.IMPORT)
            gv._input = ""
            gv._status = ""
            gv.refresh()
        elif key == "s":
            self._run_sync()
        elif key == "r":
            gv.set_mode(GreeterMode.RECENT)
            gv.refresh()
        elif key == "q":
            self.app.exit()
        elif key in ("?", "f1"):
            gv.set_mode(GreeterMode.HELP)
            gv.refresh()
        elif key.isdigit() and int(key) >= 1 and int(key) <= len(self._recent):
            self._open_editor(file_path=self._recent[int(key) - 1])

    def _handle_help_key(self, key: str, gv: GreeterView) -> None:
        if key in ("escape", "q", "?", "f1"):
            gv.set_mode(GreeterMode.MENU)
            gv.refresh()
            return
        if gv.scroll_help_by_key(key):
            gv.refresh()

    def _handle_import_key(self, key: str, gv: GreeterView) -> None:
        if key == "escape":
            gv.set_mode(GreeterMode.MENU)
            gv._status = ""
            gv.refresh()
        elif key == "enter":
            self._run_import(gv._input.strip())
        elif key == "backspace":
            gv._input = gv._input[:-1]
            gv.refresh()
        elif len(key) == 1 and key.isprintable():
            gv._input += key
            gv.refresh()

    def on_paste(self, event: Paste) -> None:
        """Pasting a deck URL into the import prompt must not be typed
        out key by key — terminals deliver it as one Paste event."""
        gv = self.query_one(GreeterView)
        if gv._mode != GreeterMode.IMPORT:
            return
        gv._input += " ".join(event.text.split())
        gv.refresh()

    def _handle_file_list_key(
        self,
        key: str,
        gv: GreeterView,
        file_list: list[Path],
    ) -> None:
        step = gv.nav.feed(key, gv.list_viewport())
        if step == PENDING:
            return
        if step is not None:
            gv.navigate(file_list, step)
            gv.refresh()
        elif key in ("escape", "q"):
            gv.set_mode(GreeterMode.MENU)
            gv.refresh()
        elif key == "enter":
            selected = gv.get_selected(file_list)
            if selected is not None:
                self._open_editor(file_path=selected)
        elif key == "n":
            self._open_editor(file_path=None)

    def _open_editor(
        self, file_path: Path | None, initial_text: str | None = None
    ) -> None:
        app = self.app
        self.app.pop_screen()
        open_deck = getattr(app, "open_deck", None)
        if callable(open_deck):  # duck-typed: hosts expose open_deck
            if initial_text is not None:
                open_deck(file_path, initial_text=initial_text)
            else:
                open_deck(file_path)

    # -- Import (file or deck-site URL) ---------------------------------

    def _run_import(self, source: str) -> None:
        gv = self.query_one(GreeterView)
        if not source:
            gv._status = "E: Enter a file path or deck URL"
            gv.refresh()
            return
        if is_deck_url(source):
            gv._status = "Fetching deck..."
            gv.refresh()
            self._import_worker(source)
            return
        self._import_file(source, gv)

    def _import_file(self, source: str, gv: GreeterView) -> None:
        """Local files parse synchronously — no network, no worker."""
        from vimtg.services.import_export_service import (
            DeckFormat,
            ImportExportService,
        )

        path = Path(source).expanduser()
        if not path.is_file():
            gv._status = f"E: File not found: {source}"
            gv.refresh()
            return
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            gv._status = f"E: Cannot read {path.name}: {exc}"
            gv.refresh()
            return
        service = ImportExportService()
        deck = service.import_deck(text)
        self._open_editor(None, service.export_deck(deck, DeckFormat.VIMTG))

    @work(thread=True)
    def _import_worker(self, url: str) -> None:
        """URL fetches run off the event loop, like the card sync."""
        from vimtg.services.import_export_service import (
            DeckFormat,
            ImportExportService,
        )

        try:
            remote = fetch_deck(url)
        except DeckSourceError as exc:
            self.app.call_from_thread(self._import_failed, str(exc))
            return
        text = ImportExportService().export_deck(
            stamped_deck(remote, url), DeckFormat.VIMTG
        )
        self.app.call_from_thread(self._open_editor, None, text)

    def _import_failed(self, message: str) -> None:
        gv = self.query_one(GreeterView)
        gv._status = f"E: {message}"
        gv.refresh()

    def _run_sync(self) -> None:
        """Kick off card sync in a worker thread — the ~150 MB download
        must not freeze the UI event loop."""
        if self._sync_running:
            return
        self._sync_running = True
        gv = self.query_one(GreeterView)
        gv._status = "Syncing card data..."
        gv.refresh()
        self._sync_worker()

    @work(thread=True, exclusive=True)
    def _sync_worker(self) -> None:
        from vimtg.config.paths import cache_dir, db_path
        from vimtg.data.card_repository import CardRepository
        from vimtg.data.database import Database
        from vimtg.data.scryfall_sync import ScryfallSync

        def _set_status(text: str) -> None:
            gv = self.query_one(GreeterView)
            gv._status = text
            gv.refresh()

        def _progress(phase: str, current: int, total: int) -> None:
            if total > 0:
                pct = current * 100 // total
                self.app.call_from_thread(
                    _set_status, f"Sync: {phase} {pct}%"
                )

        # Own connection: sqlite objects must not cross threads
        db = Database(db_path())
        try:
            db.initialize()
            repo = CardRepository(db)
            sync = ScryfallSync(repo, cache_dir())
            count = sync.sync(progress=_progress)
            message = f"Synced {count} cards"
            if sync.last_skipped:
                message += f" ({sync.last_skipped} skipped)"
        except Exception as exc:  # network/parse errors -> status line
            message = f"Sync failed: {exc}"
        finally:
            db.close()
            self._sync_running = False
        self.app.call_from_thread(_set_status, message)


def _find_all_decks() -> list[Path]:
    """Find all .deck files in cwd, sorted alphabetically by name."""
    from vimtg.data.deck_repository import DeckRepository

    return DeckRepository().list_decks(Path.cwd())
