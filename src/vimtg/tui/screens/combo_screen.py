"""ComboScreen — Commander Spellbook combos overlay (:combos, Space c).

Two sections: the combos the deck already holds and those one card
away. j/k (gg/G, Ctrl-D/U) select a combo, Enter on a one-away combo
closes the overlay with it so the editor adds the missing card, ? opens
the combos help topic, F1 the full help, q/Esc close. The lookup runs
in MainScreen's worker; this screen shows its status, then the report.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.events import Key
from textual.widgets import Static

from vimtg.services.spellbook import SERVICE, Combo, ComboReport, combo_url
from vimtg.tui.key_translator import translate
from vimtg.tui.keys import (
    CLOSE_KEYS,
    FULL_HELP_KEY,
    HELP_KEY,
    PENDING,
    VimNav,
    render_hints,
)
from vimtg.tui.screens.floating import CLOSE_HINT, FloatingScreen
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.scrolling import compute_scroll_offset

LOADING = "Looking up combos…"

HINTS = (
    ("j/k", "select"), ("gg/G", "first/last"), ("Enter", "add the missing card"),
    ("?", "help"), ("q/Esc", "close"),
)

_INDENT = "      "


@dataclass(frozen=True)
class ComboView:
    """The rendered body and the first line of each combo's row."""

    text: Text
    row_lines: tuple[int, ...]


def render_combos(report: ComboReport, selected: int) -> ComboView:
    """The overlay body: the report's note, then each section's combos,
    two lines apiece (cards, then what they produce). The missing card
    of a one-away combo is highlighted."""
    text = Text()
    lines = 0
    row_lines: list[int] = []
    if report.note:
        text.append(f"({report.note})\n\n", style="dim")
        lines += 2
    offset = 0
    for title, combos in (
        ("In this deck", report.included), ("One card away", report.one_away),
    ):
        if offset:
            text.append("\n")
            lines += 1
        text.append(f"{title} ({len(combos)})\n", style=f"bold {COLORS['mode_command']}")
        lines += 1
        if not combos:
            text.append("   (none)\n", style="dim")
            lines += 1
        for i, combo in enumerate(combos, start=offset):
            row_lines.append(lines)
            _append_combo(text, combo, i == selected)
            lines += 2
        offset += len(combos)
    return ComboView(text=text, row_lines=tuple(row_lines))


def _append_combo(text: Text, combo: Combo, is_sel: bool) -> None:
    line_style = f"on {COLORS['cursor_bg']}" if is_sel else ""
    text.append(" > " if is_sel else "   ", style=line_style)
    text.append(f"{combo.id}  ", style=f"dim {line_style}".strip())
    for j, card in enumerate(combo.cards):
        if j:
            text.append(" + ", style=line_style)
        missing = card in combo.missing
        style = f"bold {COLORS['warning']} {line_style}" if missing else line_style
        text.append(card, style=style.strip())
    text.append("\n")
    produces = ", ".join(combo.produces) or "?"
    text.append(f"{_INDENT}→ {produces}\n", style="dim")


class ComboScreen(FloatingScreen[Combo | None]):
    """Combos overlay; dismisses with the one-away combo to complete."""

    WINDOW_ID = "combo-window"
    CSS = f"""
    #combo-scroll {{
        height: 1fr;
        scrollbar-size: 1 1;
    }}
    #combo-body {{
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }}
    #combo-footer {{
        height: 2;
        text-wrap: nowrap;
        text-overflow: ellipsis;
        background: {COLORS['bg']};
    }}
    """

    def __init__(self, deck_name: str) -> None:
        super().__init__(f"Combos — {deck_name}", close_hint=f"{SERVICE} · {CLOSE_HINT}")
        self.report: ComboReport | None = None
        self.status = LOADING
        self.status_error = False
        self.selected = 0
        self._nav = VimNav()
        self._row_lines: tuple[int, ...] = ()

    def compose_window(self) -> ComposeResult:
        yield VerticalScroll(Static(id="combo-body"), id="combo-scroll")
        yield Static(id="combo-footer")

    def on_mount(self) -> None:
        self._refresh()

    @property
    def rows(self) -> tuple[Combo, ...]:
        if self.report is None:
            return ()
        return self.report.included + self.report.one_away

    def show_report(self, report: ComboReport) -> None:
        """The lookup finished: list its combos."""
        self.report = report
        self.status = ""
        if self.is_attached:
            self._refresh()

    def show_error(self, message: str) -> None:
        """The lookup failed: say why in place of the list."""
        self.status = message
        self.status_error = True
        if self.is_attached:
            self._refresh()

    def _refresh(self) -> None:
        body = self.query_one("#combo-body", Static)
        if self.report is None:
            style = COLORS["error"] if self.status_error else "dim"
            body.update(Text(f"\n{self.status}", style=style))
            self.query_one("#combo-footer", Static).update(render_hints(HINTS[-2:]))
            return
        self.selected = max(0, min(self.selected, len(self.rows) - 1))
        view = render_combos(self.report, self.selected)
        self._row_lines = view.row_lines
        body.update(view.text)
        self._update_footer()
        self._scroll_to_selection(view)

    def _update_footer(self) -> None:
        footer = Text()
        if self.rows:
            combo = self.rows[self.selected]
            if combo.missing:
                footer.append(f" Enter adds {combo.missing[0]}", style="bold")
            else:
                footer.append(" already in the deck", style="dim")
            footer.append(f" · {combo_url(combo.id)}", style="dim")
        footer.append("\n")
        footer.append_text(render_hints(HINTS))
        self.query_one("#combo-footer", Static).update(footer)

    def _scroll_to_selection(self, view: ComboView) -> None:
        if not self._row_lines:
            return
        scroll = self.query_one("#combo-scroll", VerticalScroll)
        viewport = scroll.size.height
        if viewport <= 0:
            return
        total = len(view.text.plain.splitlines())
        top = compute_scroll_offset(
            self._row_lines[self.selected], int(scroll.scroll_y), total, viewport,
        )
        scroll.scroll_to(y=top, animate=False)

    def on_key(self, event: Key) -> None:
        event.prevent_default()
        event.stop()
        key = translate(event.key)
        if key in CLOSE_KEYS:
            self.dismiss(None)
            return
        if key in (HELP_KEY, FULL_HELP_KEY):
            from vimtg.tui.screens.help_screen import HelpScreen

            self.app.push_screen(HelpScreen(topic="combos" if key == HELP_KEY else None))
            return
        rows = self.rows
        if not rows:
            return
        if key == "enter":
            if rows[self.selected].missing:
                self.dismiss(rows[self.selected])
            return
        step = self._nav.feed(key, max(1, self.query_one("#combo-scroll").size.height // 2))
        if step is None or step == PENDING:
            return
        if step == "home":
            self.selected = 0
        elif step == "end":
            self.selected = len(rows) - 1
        else:
            self.selected += int(step)
        self._refresh()
