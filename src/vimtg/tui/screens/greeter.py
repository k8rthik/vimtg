"""Greeter screen — shown when vimtg launches with no file argument.

Inspired by alpha-nvim: centered ASCII logo, recent files, and quick actions.
Supports four modes: menu (default), help, file browser, and recent files browser.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from rich.text import Text
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Static

from vimtg.tui.key_translator import translate
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
    ("n", "New deck", ":new"),
    ("e", "Open file", ":e"),
    ("s", "Sync cards", ":sync"),
    ("r", "Recent files", ""),
    ("?", "Help", ":help"),
    ("q", "Quit", ":q"),
]

_DIM = f"dim {COLORS['comment']}"
_SELECTED_STYLE = f"on {COLORS['cursor_bg']}"


class GreeterMode(Enum):
    """Greeter view modes — separate from editor modes."""

    MENU = "menu"
    HELP = "help"
    FILES = "files"
    RECENT = "recent"


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

    def render(self) -> Text:
        if self._mode == GreeterMode.HELP:
            return self._render_help()
        if self._mode == GreeterMode.FILES:
            return self._render_file_list(self._all_files, "Open File")
        if self._mode == GreeterMode.RECENT:
            return self._render_file_list(self._recent, "Recent Files")
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
        t.append("  v0.1.0\n", style=_DIM)
        t.append("\n")

        for key, label, _cmd in ACTIONS:
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

        t.append("  Press a key or type :command\n", style=_DIM)
        return t

    def _render_help(self) -> Text:
        from vimtg.editor.help_text import HELP_OVERVIEW

        t = Text()
        t.append("  vimtg Help\n", style=f"bold {COLORS['mana_blue']}")
        t.append("  " + "=" * 40 + "\n\n", style=_DIM)

        for line in HELP_OVERVIEW.split("\n"):
            stripped = line.strip()
            if stripped and stripped == stripped.upper() and stripped.isalpha():
                # Section headers: NAVIGATION, EDITING, COMMANDS
                t.append(f"  {line}\n", style=f"bold {COLORS['mana_green']}")
            else:
                t.append(f"  {line}\n", style="")

        t.append("\n")
        t.append("  Press Escape or q to return\n", style=_DIM)
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
            indicator = " "

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
        t.append("  j/k navigate  Enter open  Escape back\n", style=_DIM)
        return t

    # -- Cursor navigation ---------------------------------------------

    def set_mode(self, mode: GreeterMode) -> None:
        self._mode = mode
        self._cursor = 0

    def select_next(self, file_list: list[Path]) -> None:
        if file_list:
            self._cursor = min(self._cursor + 1, len(file_list) - 1)

    def select_prev(self) -> None:
        self._cursor = max(self._cursor - 1, 0)

    def get_selected(self, file_list: list[Path]) -> Path | None:
        if 0 <= self._cursor < len(file_list):
            return file_list[self._cursor]
        return None


class GreeterScreen(Screen):
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

    def compose(self):  # noqa: ANN201
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
        elif key == "s":
            self._run_sync()
        elif key == "r":
            gv.set_mode(GreeterMode.RECENT)
            gv.refresh()
        elif key in ("q", "escape"):
            self.app.exit()
        elif key == "?":
            gv.set_mode(GreeterMode.HELP)
            gv.refresh()
        elif key == ":":
            gv.set_mode(GreeterMode.HELP)
            gv.refresh()
        elif key.isdigit() and int(key) >= 1 and int(key) <= len(self._recent):
            self._open_editor(file_path=self._recent[int(key) - 1])

    def _handle_help_key(self, key: str, gv: GreeterView) -> None:
        if key in ("escape", "q", "?"):
            gv.set_mode(GreeterMode.MENU)
            gv.refresh()

    def _handle_file_list_key(
        self,
        key: str,
        gv: GreeterView,
        file_list: list[Path],
    ) -> None:
        if key == "j":
            gv.select_next(file_list)
            gv.refresh()
        elif key == "k":
            gv.select_prev()
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
        elif key == "g":
            gv._cursor = 0
            gv.refresh()
        elif key == "G":
            if file_list:
                gv._cursor = len(file_list) - 1
            gv.refresh()

    def _open_editor(self, file_path: Path | None) -> None:
        self.app.pop_screen()
        self.app._launch_editor(file_path)  # type: ignore[attr-defined]

    def _run_sync(self) -> None:
        """Run card sync inline — show progress in the greeter."""
        from vimtg.config.paths import cache_dir, db_path
        from vimtg.data.card_repository import CardRepository
        from vimtg.data.database import Database
        from vimtg.data.scryfall_sync import ScryfallSync

        try:
            db = Database(db_path())
            db.initialize()
            repo = CardRepository(db)
            sync = ScryfallSync(repo, cache_dir())
            gv = self.query_one(GreeterView)
            count = sync.sync()
            gv._status = f"Synced {count} cards"  # type: ignore[attr-defined]
            gv.refresh()
        except Exception as exc:
            gv = self.query_one(GreeterView)
            gv._status = f"Sync failed: {exc}"  # type: ignore[attr-defined]
            gv.refresh()


def _find_all_decks() -> list[Path]:
    """Find all .deck files in cwd, sorted alphabetically by name."""
    cwd = Path.cwd()
    return sorted(cwd.glob("*.deck"), key=lambda p: p.name.lower())
