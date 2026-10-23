"""NewDeckScreen — the two-question "new deck" wizard.

Shown over the editor when a deck with no cards opens with a blank
'// Deck:' name or '// Format:' (greeter `n`, `vimtg new.deck`, a deck
made with `vimtg new` and no --format). It asks for the deck name and
the format — the name later names the file on the first :w, the format
turns on legality checks — then hands both back to the editor. Esc
skips it; both lines stay editable in the buffer as before.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key, Paste
from textual.screen import ModalScreen
from textual.widgets import Static

from vimtg.domain.formats import known_formats, normalize_format
from vimtg.editor.line_buffer import LineBuffer
from vimtg.tui.key_translator import translate
from vimtg.tui.theme import COLORS

# The short list offered on screen; every known format still tab-completes
COMMON_FORMATS: tuple[str, ...] = (
    "standard", "pioneer", "modern", "legacy",
    "vintage", "pauper", "commander", "brawl",
)

_DIM = f"dim {COLORS['comment']}"
_EDITS: dict[str, Callable[[LineBuffer], LineBuffer]] = {
    "backspace": LineBuffer.delete_backward,
    "ctrl_w": LineBuffer.delete_word_backward,
    "ctrl_u": LineBuffer.delete_to_start,
}


@dataclass(frozen=True)
class NewDeckInfo:
    """The wizard's answers ('' = left blank)."""

    name: str
    fmt: str


def format_matches(prefix: str) -> list[str]:
    """Known formats starting with `prefix`, the common ones first."""
    p = prefix.strip().lower()
    known = known_formats()
    common = [f for f in COMMON_FORMATS if f in known and f.startswith(p)]
    rest = [f for f in known if f.startswith(p) and f not in common]
    return common + rest


class NewDeckScreen(ModalScreen[NewDeckInfo | None]):
    """Prompt for a new deck's name and format."""

    DEFAULT_CSS = f"""
    NewDeckScreen {{
        align: center middle;
        background: {COLORS['bg']} 60%;
    }}
    #new-deck-box {{
        width: 64;
        max-width: 100%;
        height: auto;
        max-height: 100%;
        border: round {COLORS['mana_blue']};
        background: {COLORS['bg']};
        padding: 0 1;
    }}
    """

    def __init__(self, name: str = "", fmt: str = "", suggested_name: str = "") -> None:
        """`name`/`fmt` are the deck's current answers; `suggested_name`
        prefills a blank name (still asked, Enter accepts it)."""
        super().__init__()
        self.name_text = name or suggested_name
        self.fmt_text = fmt
        # Start on the first question still unanswered
        self.field = "format" if name and not fmt else "name"
        self.error = ""
        self._cycle: list[str] = []
        self._cycle_at = -1

    def compose(self) -> ComposeResult:
        with Vertical(id="new-deck-box"):
            yield Static(id="new-deck-body")

    def on_mount(self) -> None:
        self._refresh()

    # -- rendering -----------------------------------------------------

    def _ghost(self) -> str:
        if self.field != "format" or not self.fmt_text:
            return ""
        matches = format_matches(self.fmt_text)
        return matches[0][len(self.fmt_text):] if matches else ""

    def render_body(self) -> Text:
        t = Text()
        t.append("New deck\n", style=f"bold {COLORS['mana_blue']}")
        self._field_line(t, "name", "Deck name", self.name_text)
        self._field_line(t, "format", "Format", self.fmt_text, self._ghost())
        t.append("Formats: ", style=_DIM)
        t.append(" ".join(COMMON_FORMATS), style=COLORS["fg"])
        t.append(" (Tab completes)\n", style=_DIM)
        if self.error:
            t.append(f"{self.error}\n", style=f"bold {COLORS['error']}")
        t.append("Enter next/done  Tab complete  Esc skip", style=_DIM)
        return t

    def _field_line(
        self, t: Text, field: str, label: str, value: str, ghost: str = ""
    ) -> None:
        active = self.field == field
        t.append("> " if active else "  ", style=f"bold {COLORS['quantity']}")
        t.append(f"{label}: ", style="bold" if active else "")
        t.append(value)
        if active:
            if ghost:
                t.append(ghost[0], style="reverse")
                t.append(ghost[1:], style=_DIM)
            else:
                t.append(" ", style="reverse")
        t.append("\n")

    def _refresh(self) -> None:
        self.query_one("#new-deck-body", Static).update(self.render_body())

    # -- input ---------------------------------------------------------

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+c":
            return
        event.prevent_default()
        event.stop()
        self.feed(translate(event.key))
        self._refresh()

    def on_paste(self, event: Paste) -> None:
        event.stop()
        self._type(" ".join(event.text.split()))
        self._refresh()

    def feed(self, key: str) -> None:
        if key == "tab":
            self._complete()
            return
        self._cycle = []
        if key == "escape":
            self.dismiss(None)
        elif key == "enter":
            self._submit()
        elif key in ("up", "shift_tab"):
            self.field = "name"
        elif key == "down":
            self.field = "format"
        elif key in _EDITS:
            self._edit(_EDITS[key])
        elif len(key) == 1 and key.isprintable():
            self._type(key)

    def _edit(self, edit: Callable[[LineBuffer], LineBuffer]) -> None:
        """Backspace / Ctrl-W / Ctrl-U at the end of the active field,
        with the same semantics as every other prompt."""
        text = self.name_text if self.field == "name" else self.fmt_text
        edited = edit(LineBuffer(text=text, cursor=len(text))).text
        if self.field == "name":
            self.name_text = edited
        else:
            self.fmt_text = edited

    def _type(self, chars: str) -> None:
        self.error = ""
        if self.field == "name":
            self.name_text += chars
        else:
            self.fmt_text += chars.replace(" ", "")

    def _complete(self) -> None:
        """Tab: on the name, move on; on the format, cycle the matches."""
        if self.field == "name":
            self.field = "format"
            return
        if not self._cycle:
            self._cycle = format_matches(self.fmt_text) or []
            self._cycle_at = -1
        if self._cycle:
            self._cycle_at = (self._cycle_at + 1) % len(self._cycle)
            self.fmt_text = self._cycle[self._cycle_at]
            self.error = ""

    def _submit(self) -> None:
        if self.field == "name":
            self.field = "format"
            return
        fmt = normalize_format(self.fmt_text)
        if fmt and fmt not in known_formats():
            matches = format_matches(fmt)
            if len(matches) != 1:
                self.error = f"Unknown format: {fmt} (Tab completes)"
                return
            fmt = matches[0]
        self.dismiss(NewDeckInfo(name=self.name_text.strip(), fmt=fmt))
