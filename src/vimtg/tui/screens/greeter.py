"""Greeter screen — shown when vimtg launches with no file argument.

Inspired by alpha-nvim: centered ASCII logo, recent files, and quick actions.
"""

from __future__ import annotations

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


class GreeterView(Static):
    """Centered greeter content."""

    def __init__(self, recent_files: list[Path] | None = None) -> None:
        super().__init__()
        self._recent = recent_files or []

    def render(self) -> Text:
        t = Text()

        # Logo — use Text directly to avoid Rich markup interpretation
        for line in LOGO_LINES:
            logo_line = Text(f"  {line}\n")
            logo_line.stylize(f"bold {COLORS['mana_red']}")
            t.append_text(logo_line)
        t.append("\n")

        # Tagline
        t.append("  Vim-powered MTG deck builder\n", style=f"dim {COLORS['comment']}")
        t.append("  v0.1.0\n", style=f"dim {COLORS['comment']}")
        t.append("\n")

        # Quick actions
        for key, label, _cmd in ACTIONS:
            t.append(f"  [{key}]", style=f"bold {COLORS['quantity']}")
            t.append(f"  {label}\n", style="")
        t.append("\n")

        # Recent files
        if self._recent:
            t.append("  Recent\n", style=f"bold {COLORS['mana_blue']}")
            for i, path in enumerate(self._recent[:5]):
                num = i + 1
                t.append(f"  [{num}]", style=f"bold {COLORS['quantity']}")
                t.append(f"  {path.name}\n", style="dim")
            t.append("\n")

        t.append(
            "  Press a key or type :command\n",
            style=f"dim {COLORS['comment']}",
        )
        return t


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

    def compose(self):  # noqa: ANN201
        yield GreeterView(recent_files=self._recent)

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+c":
            self.app.exit()
            return
        event.prevent_default()
        event.stop()

        key = translate(event.key)

        if key == "n" or key == "e":
            self._open_editor(file_path=None)
        elif key == "s":
            self._run_sync()
        elif key in ("q", "escape"):
            self.app.exit()
        elif key == "?" or key == ":":
            self._open_editor(file_path=None)
        elif key.isdigit() and int(key) >= 1 and int(key) <= len(self._recent):
            self._open_editor(file_path=self._recent[int(key) - 1])

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
            # Update the view to show sync status
            count = sync.sync()
            gv._status = f"Synced {count} cards"  # type: ignore[attr-defined]
            gv.refresh()
        except Exception as exc:
            gv = self.query_one(GreeterView)
            gv._status = f"Sync failed: {exc}"  # type: ignore[attr-defined]
            gv.refresh()
