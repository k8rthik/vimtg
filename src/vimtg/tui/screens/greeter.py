"""Greeter screen — shown when vimtg launches with no file argument.

Inspired by alpha-nvim: centered ASCII logo, recent files, and quick actions.
Supports menu (default), help, file browser, recent files browser, import,
and the list of unsaved buffers left by an earlier session (recovery).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

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
from vimtg.services.recovery import (
    RecoveryCopy,
    discard_copy,
    orphaned_recoveries,
    read_copy,
)
from vimtg.tui.key_translator import translate
from vimtg.tui.keys import PENDING, VimNav
from vimtg.tui.theme import COLORS

if TYPE_CHECKING:
    from vimtg.domain.deck import Deck
    from vimtg.services.import_export_service import ImportExportService

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

LOGO_WIDTH = max(len(line) for line in LOGO_LINES)
MENU_RECENT = 5  # recent decks listed on the menu (all of them under `r`)
# Ctrl-C on the menu: the greeter quits with q (it has no : line)
EXIT_HINT = "Press q to exit vimtg"

_DIM = f"dim {COLORS['comment']}"


def _where(path: Path) -> str:
    """Where a recent deck lives, '' for the current directory."""
    try:
        parent = path.parent.resolve()
        if parent == Path.cwd().resolve():
            return ""
        home = Path.home().resolve()
        if parent.is_relative_to(home):
            return "~/" + str(parent.relative_to(home)) if parent != home else "~"
        return str(parent)
    except (OSError, RuntimeError):
        return ""
_SELECTED_STYLE = f"on {COLORS['cursor_bg']}"


class GreeterMode(Enum):
    """Greeter view modes — separate from editor modes."""

    MENU = "menu"
    HELP = "help"
    FILES = "files"
    RECENT = "recent"
    IMPORT = "import"
    RECOVER = "recover"


class GreeterView(Static):
    """Centered greeter content with mode-based rendering."""

    def __init__(
        self,
        recent_files: list[Path] | None = None,
        all_files: list[Path] | None = None,
        recoveries: list[RecoveryCopy] | None = None,
    ) -> None:
        super().__init__()
        self._recent = recent_files or []
        self._all_files = all_files or []
        # Recovery copies no deck open will offer (unnamed, or file gone)
        self._recoveries = recoveries or []
        self._mode = GreeterMode.MENU
        self._cursor = 0
        self._status = ""
        self._card_note = ""  # card database readout (no data, age, sync)
        self._card_note_attention = False
        self._input = ""  # import prompt text (path or URL)
        self.nav = VimNav()
        self._help_nav = VimNav()
        self._help_offset = 0
        self._shown_recent = min(len(self._recent), MENU_RECENT)

    def render(self) -> Text:
        if self._mode == GreeterMode.HELP:
            return self._render_help()
        if self._mode == GreeterMode.FILES:
            return self._render_file_list(self._all_files, "Open File")
        if self._mode == GreeterMode.RECENT:
            return self._render_file_list(self._recent, "Recent Files")
        if self._mode == GreeterMode.IMPORT:
            return self._render_import()
        if self._mode == GreeterMode.RECOVER:
            return self._render_recoveries()
        return self._render_menu()

    # -- Render methods ------------------------------------------------

    def _render_menu(self) -> Text:
        """The menu, shedding extras to fit the terminal: the logo goes
        first, then the tagline, then recent decks; on very short
        terminals the actions pack two to a line."""
        width = self.size.width or 80
        height = self.size.height or 40
        # The card-database note matters (no data, sync failing): it is
        # kept with the status line rather than shed with the tagline
        status_lines = (
            (1 if self._status else 0) + (1 if self._card_note else 0)
            + (1 if self._recoveries else 0)
        )
        # Always shown: the actions (one per line plus a blank, or two
        # per line when that does not fit), any status, and the hint
        compact = height < len(ACTIONS) + 1 + status_lines + 1
        action_lines = (len(ACTIONS) + 1) // 2 if compact else len(ACTIONS) + 1
        room = height - action_lines - status_lines - 1
        show_logo = width >= LOGO_WIDTH + 2 and room >= len(LOGO_LINES) + 1 + 3
        if show_logo:
            room -= len(LOGO_LINES) + 1
        show_tagline = room >= 3
        if show_tagline:
            room -= 3
        shown_recent = min(len(self._recent), MENU_RECENT, max(0, room - 2))

        t = Text()
        if show_logo:
            for line in LOGO_LINES:
                logo_line = Text(f"  {line}\n")
                logo_line.stylize(f"bold {COLORS['mana_red']}")
                t.append_text(logo_line)
            t.append("\n")

        if show_tagline:
            t.append("  Vim-powered MTG deck builder\n", style=_DIM)
            t.append(f"  v{__version__}\n", style=_DIM)
        if self._card_note:
            style = f"bold {COLORS['warning']}" if self._card_note_attention else _DIM
            note = self._card_note
            if len(note) > width - 2:  # one line, even at 30 columns
                note = note[: max(1, width - 3)] + "…"
            t.append(f"  {note}\n", style=style)
        if show_tagline:
            t.append("\n")

        if compact:
            for i in range(0, len(ACTIONS), 2):
                for key, label in ACTIONS[i:i + 2]:
                    # First word only ("Recent"), so two fit in 30 columns
                    t.append(f" [{key}]", style=f"bold {COLORS['quantity']}")
                    t.append(f" {label.split()[0]:<7}")
                t.append("\n")
        else:
            for key, label in ACTIONS:
                t.append(f"  [{key}]", style=f"bold {COLORS['quantity']}")
                t.append(f"  {label}\n", style="")
            t.append("\n")

        if shown_recent:
            t.append("  Recent\n", style=f"bold {COLORS['mana_blue']}")
            for i, path in enumerate(self._recent[:shown_recent]):
                t.append(f"  [{i + 1}]", style=f"bold {COLORS['quantity']}")
                t.append(f"  {path.name}", style="dim")
                where = _where(path)
                if where:
                    t.append(f"  {where}", style=_DIM)
                t.append("\n")
            t.append("\n")
        self._shown_recent = shown_recent

        if self._recoveries:
            n = len(self._recoveries)
            t.append("  [R]", style=f"bold {COLORS['quantity']}")
            t.append(
                f" {n} unsaved buffer{'s' if n != 1 else ''} from an earlier session\n",
                style=f"bold {COLORS['warning']}",
            )
        if self._status:
            t.append(f"  {self._status}\n", style=f"bold {COLORS['mana_green']}")

        t.append("  Press a highlighted key\n" if compact
                 else "  Press a highlighted key to continue\n", style=_DIM)
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
        t.append(
            "  Paste a deck URL or a decklist, or type a file path:\n\n", style=""
        )
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
            where = _where(path)
            if where:
                line.append(f"  {where}", style="dim")

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

    def _render_recoveries(self) -> Text:
        t = Text()
        t.append("  Unsaved buffers\n", style=f"bold {COLORS['mana_blue']}")
        t.append("  " + "-" * 40 + "\n\n", style=_DIM)
        if not self._recoveries:
            t.append("  Nothing left to recover\n\n", style=_DIM)
            if self._status:
                t.append(f"  {self._status}\n", style=f"bold {COLORS['warning']}")
            t.append("  Press Escape to return\n", style=_DIM)
            return t
        for i, copy in enumerate(self._recoveries):
            is_selected = i == self._cursor
            line = Text()
            line.append(
                f"  {'>' if is_selected else ' '} ",
                style=f"{COLORS['quantity']}" if is_selected else "",
            )
            line.append(copy.label, style="bold" if is_selected else "")
            if copy.original is not None:
                where = _where(copy.original)
                line.append(f"  {where or '.'} (file no longer exists)", style="dim")
            saved = datetime.fromtimestamp(copy.mtime).strftime("%Y-%m-%d %H:%M")
            line.append(f"  {saved}", style="dim")
            if is_selected:
                line.stylize(_SELECTED_STYLE)
            t.append_text(line)
            t.append("\n")
        t.append("\n")
        if self._status:
            t.append(f"  {self._status}\n", style=f"bold {COLORS['warning']}")
        t.append(
            "  j/k navigate  Enter open  d discard  Esc/q back\n", style=_DIM,
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
        if self._mode == GreeterMode.RECOVER:
            return [c.copy for c in self._recoveries]
        return []

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if self._mode in (GreeterMode.FILES, GreeterMode.RECENT, GreeterMode.RECOVER):
            event.stop()
            self.navigate(self._active_list(), 1)
            self.refresh()
        elif self._mode == GreeterMode.HELP:
            event.stop()
            self.scroll_help_by_key("ctrl_d")
            self.refresh()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if self._mode in (GreeterMode.FILES, GreeterMode.RECENT, GreeterMode.RECOVER):
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

    def compose(self) -> ComposeResult:
        yield GreeterView(
            recent_files=self._recent, all_files=self._all_files,
            recoveries=orphaned_recoveries(),
        )

    def on_mount(self) -> None:
        status = getattr(self.app, "card_data_status", None)
        if callable(status):
            self.set_card_data_status(*status())

    def set_card_data_status(self, text: str, attention: bool) -> None:
        """Called by the app as card data appears, ages or syncs."""
        from vimtg.data.scryfall_sync import NO_CARD_DATA

        views = self.query(GreeterView)
        if not views:
            return  # not composed yet; on_mount pulls the status
        gv = views.first()
        # The greeter's sync key is s, not :sync
        gv._card_note = "no card data - press s to download" if text == NO_CARD_DATA else text
        gv._card_note_attention = attention
        gv.refresh()

    def on_key(self, event: Key) -> None:
        event.prevent_default()
        event.stop()

        key = translate(event.key)
        gv = self.query_one(GreeterView)
        if event.key == "ctrl+c" and gv._mode == GreeterMode.MENU:
            # Ctrl-C is Esc and never quits; say what does
            gv._status = EXIT_HINT
            gv.refresh()
            return

        if gv._mode == GreeterMode.MENU:
            self._handle_menu_key(key, gv)
        elif gv._mode == GreeterMode.HELP:
            self._handle_help_key(key, gv)
        elif gv._mode == GreeterMode.IMPORT:
            self._handle_import_key(key, gv)
        elif gv._mode == GreeterMode.RECOVER:
            self._handle_recover_key(key, gv)
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
        elif key == "R" and gv._recoveries:
            gv.set_mode(GreeterMode.RECOVER)
            gv._status = ""
            gv.refresh()
        elif key == "q":
            self.app.exit()
        elif key in ("?", "f1"):
            gv.set_mode(GreeterMode.HELP)
            gv.refresh()
        elif key.isdigit() and 1 <= int(key) <= gv._shown_recent:
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
        """Terminals deliver a paste as one Paste event, not keys.

        A multi-line paste (in the menu or the import prompt) is a
        decklist: it opens in the editor. A single line goes into the
        import prompt — a deck URL or a file path, imported on Enter.
        """
        gv = self.query_one(GreeterView)
        if gv._mode not in (GreeterMode.MENU, GreeterMode.IMPORT):
            return
        text = event.text.strip()
        if not text:
            return
        if "\n" in text or "\r" in text:
            self._import_decklist(text, gv)
            return
        if gv._mode == GreeterMode.MENU:
            gv.set_mode(GreeterMode.IMPORT)
            gv._input = ""
            gv._status = ""
        gv._input += " ".join(text.split())
        gv.refresh()

    def _import_decklist(self, text: str, gv: GreeterView) -> bool:
        """Open pasted decklist text in the editor; False (with a status
        message) when it holds no card lines."""
        from vimtg.services.import_export_service import ImportExportService

        service = ImportExportService()
        try:
            report = service.import_deck_report(text)
        except ValueError as exc:
            report = None
            reason = str(exc)
        else:
            reason = "no card lines found (expected lines like '4 Lightning Bolt')"
        if report is None or not report.deck.entries:
            gv.set_mode(GreeterMode.IMPORT)
            gv._status = f"E: Not a decklist: {reason}"
            gv.refresh()
            return False
        self._open_editor(None, _imported_text(service, text, report.deck))
        return True

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

    def _handle_recover_key(self, key: str, gv: GreeterView) -> None:
        """Unsaved-buffer list: Enter opens a copy (its deck's path when
        it had one), d discards it for good."""
        copies = gv._recoveries
        step = gv.nav.feed(key, gv.list_viewport())
        if step == PENDING:
            return
        if step is not None:
            gv.navigate([c.copy for c in copies], step)
        elif key in ("escape", "q"):
            gv.set_mode(GreeterMode.MENU)
            gv._status = ""
        elif key in ("enter", "d") and 0 <= gv._cursor < len(copies):
            chosen = copies[gv._cursor]
            if key == "d":
                discard_copy(chosen.copy)
                gv._recoveries = [c for c in copies if c is not chosen]
                gv.navigate([c.copy for c in gv._recoveries], 0)
                gv._status = f"Discarded {chosen.label}"
            else:
                text = read_copy(chosen.copy)
                if text is None:
                    gv._status = f"E: Cannot read {chosen.copy.name}"
                else:
                    self._open_recovery(chosen, text)
                    return
        gv.refresh()

    def _open_recovery(self, chosen: RecoveryCopy, text: str) -> None:
        app = self.app
        self.app.pop_screen()
        open_deck = getattr(app, "open_deck", None)
        if callable(open_deck):  # duck-typed: hosts expose open_deck
            open_deck(chosen.original, initial_text=text, recovery=chosen)

    def _open_editor(
        self, file_path: Path | None, initial_text: str | None = None
    ) -> None:
        app = self.app
        if initial_text is None and file_path is not None and file_path.exists():
            # open_deck exits the app on an unreadable file (right at
            # startup, wrong here): report it and keep the greeter up
            try:
                file_path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as exc:
                gv = self.query_one(GreeterView)
                if isinstance(exc, UnicodeDecodeError):
                    reason = "not UTF-8 text"
                else:
                    reason = exc.strerror or str(exc)
                gv._status = f"E: Cannot open {file_path.name}: {reason}"
                gv.refresh()
                return
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
        from vimtg.services.import_export_service import ImportExportService

        path = Path(source).expanduser()
        if not path.is_file():
            # A single typed/pasted card line ("4 Lightning Bolt")
            if source[:1].isdigit() and self._import_decklist(source, gv):
                return
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
        if not deck.metadata.name:
            deck = replace(deck, metadata=replace(deck.metadata, name=path.stem))
        self._open_editor(None, _imported_text(service, text, deck))

    @work(thread=True)
    def _import_worker(self, url: str) -> None:
        """URL fetches run off the event loop, like the card sync."""
        from vimtg.services.import_export_service import structured_deck_text

        try:
            remote = fetch_deck(url)
        except DeckSourceError as exc:
            self.app.call_from_thread(self._import_failed, str(exc))
            return
        text = structured_deck_text(stamped_deck(remote, url))
        self.app.call_from_thread(self._open_editor, None, text)

    def _import_failed(self, message: str) -> None:
        gv = self.query_one(GreeterView)
        gv._status = f"E: {message}"
        gv.refresh()

    def _run_sync(self) -> None:
        """s: start the app's card sync (one sync at a time, app-wide);
        its progress reaches the card note through set_card_data_status."""
        start = getattr(self.app, "start_card_sync", None)
        if not callable(start):
            return
        gv = self.query_one(GreeterView)
        gv._status = start()
        gv.refresh()


def _find_all_decks() -> list[Path]:
    """Find all .deck files in cwd, sorted alphabetically by name."""
    from vimtg.data.deck_repository import DeckRepository

    return DeckRepository().list_decks(Path.cwd())


def _imported_text(service: ImportExportService, text: str, deck: Deck) -> str:
    """Editor text for an imported deck: a vimtg deck verbatim, anything
    else in the structured new-deck layout (see structured_deck_text)."""
    from vimtg.services.import_export_service import (
        DeckFormat,
        normalize_text,
        structured_deck_text,
    )

    if service.detect_format(normalize_text(text)) is DeckFormat.VIMTG:
        return normalize_text(text)
    return structured_deck_text(deck)
