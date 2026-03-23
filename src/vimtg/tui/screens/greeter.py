"""Greeter screen — shown when vimtg launches with no file argument.

Inspired by alpha-nvim: centered ASCII logo, recent files, and quick actions.
"""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Static

from vimtg.tui.theme import COLORS

LOGO = r"""
         _            _
  __   _(_)_ __ ___ | |_ __ _
  \ \ / / | '_ ` _ \| __/ _` |
   \ V /| | | | | | | || (_| |
    \_/ |_|_| |_| |_|\__\__, |
                         |___/
"""

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

        # Logo
        for line in LOGO.strip().split("\n"):
            t.append(f"  {line}\n", style=f"bold {COLORS['mana_red']}")
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
        event.prevent_default()
        event.stop()

        key = event.key

        if key == "n":
            self._open_new_deck()
        elif key == "e":
            self._open_editor(file_path=None)
        elif key == "s":
            self.app.exit(message="Run: vimtg sync")
        elif key in ("q", "escape"):
            self.app.exit()
        elif key == "question_mark" or key == "?":
            self._open_editor_with_help()
        elif key.isdigit() and 1 <= int(key) <= len(self._recent):
            path = self._recent[int(key) - 1]
            self._open_editor(file_path=path)
        elif key == "colon" or key == ":":
            # Drop into editor with command mode ready
            self._open_editor(file_path=None)

    def _open_new_deck(self) -> None:
        self._open_editor(file_path=None)

    def _open_editor(self, file_path: Path | None) -> None:
        # Pop greeter and let app mount the main editor screen
        self.app.pop_screen()
        self.app._launch_editor(file_path)  # type: ignore[attr-defined]

    def _open_editor_with_help(self) -> None:
        self._open_editor(file_path=None)
