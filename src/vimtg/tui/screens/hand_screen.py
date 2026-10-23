"""HandScreen — sample hand / goldfish overlay (:hand, Space h).

Draws an opening seven from the main deck and lets the user goldfish:
n/Space draw, m London mulligan (b bottoms the selected card), r
reshuffles a fresh hand, j/k select, q/Esc close. The game logic lives
in domain.sample_hand; this screen only renders it and maps keys.
"""

from __future__ import annotations

import random

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Static

from vimtg.domain.sample_hand import (
    Goldfish,
    GoldfishError,
    HandSource,
    count_lands,
    deal,
    draw,
    format_odds,
    mulligan,
    put_on_bottom,
    source_odds,
)
from vimtg.editor.command_handlers.hand_cmds import HandOpen
from vimtg.tui.key_translator import translate
from vimtg.tui.keys import CLOSE_KEYS, NAV_DOWN, NAV_UP, render_hints
from vimtg.tui.theme import COLORS

DRAW_KEYS = frozenset({"n", " "})
MULLIGAN_KEY = "m"
BOTTOM_KEY = "b"
RESHUFFLE_KEY = "r"

HINTS = (
    ("n/Space", "draw"), ("m", "mulligan"), ("b", "bottom"),
    ("r", "reshuffle"), ("j/k", "select"), ("q/Esc", "close"),
)

_HEADER = "═══ Sample hand ═══════════════════════════════════════"


def render_hand(
    source: HandSource,
    state: Goldfish,
    selected: int,
    seed: int | None = None,
    mana_costs: dict[str, str] | None = None,
    message: str = "",
) -> Text:
    """The overlay body: zones, the hand with its land count, and odds."""
    costs = mana_costs or {}
    accent = f"bold {COLORS['mode_command']}"
    text = Text()
    title = _HEADER
    if source.plan:
        title += f"  vs {source.plan}"
    if seed is not None:
        title += f"  seed={seed}"
    text.append(f"\n{title}\n\n", style=accent)
    if source.command_zone:
        text.append("Command zone: ", style="bold")
        text.append(", ".join(source.command_zone) + "\n")
    if source.companions:
        text.append("Companion: ", style="bold")
        text.append(", ".join(source.companions) + "\n")

    lands = count_lands(state.hand, source.lands)
    text.append(
        f"Hand ({len(state.hand)} cards, {lands} land{'s' if lands != 1 else ''})",
        style="bold",
    )
    if state.mulligans:
        text.append(f"  mulligans: {state.mulligans}", style="dim")
    if state.draws:
        text.append(f"  draws: {state.draws}", style="dim")
    text.append("\n")
    if state.to_bottom:
        text.append(
            f"Put {state.to_bottom} card{'s' if state.to_bottom != 1 else ''} "
            "on the bottom: select with j/k, press b\n",
            style=COLORS["warning"],
        )

    width = max((len(name) for name in state.hand), default=0)
    for i, name in enumerate(state.hand):
        is_sel = i == selected
        line_style = f"on {COLORS['cursor_bg']}" if is_sel else ""
        text.append(" > " if is_sel else "   ", style=line_style)
        text.append(name.ljust(width), style=line_style)
        detail = "Land" if name in source.lands else costs.get(name, "")
        text.append(f"  {detail}\n", style="dim")

    if state.bottomed:
        text.append("Bottom: ", style="bold")
        text.append(", ".join(state.bottomed) + "\n", style="dim")
    text.append(f"Library: {len(state.library)} cards\n\n", style="dim")

    for line in format_odds(source_odds(source)):
        text.append(line + "\n")
    if message:
        text.append(f"\n{message}\n", style=COLORS["error"])
    return text


class HandScreen(Screen[None]):
    """Sample-hand overlay; the game state is replaced on every action."""

    CSS = f"""
    #hand-scroll {{
        height: 1fr;
        scrollbar-size: 1 1;
    }}
    #hand-body {{
        padding: 0 2;
    }}
    #hand-footer {{
        height: 1;
        dock: bottom;
        background: {COLORS['bg']};
    }}
    """

    def __init__(self, request: HandOpen) -> None:
        super().__init__()
        self.request = request
        self._rng = random.Random(request.seed)
        self.state = self._new_game()
        self.selected = 0
        self.message = ""

    def _new_game(self) -> Goldfish:
        source = self.request.source
        return deal(source.library, self._rng, free_mulligan=source.free_mulligan)

    def compose(self) -> ComposeResult:
        yield VerticalScroll(Static(id="hand-body"), id="hand-scroll")
        yield Static(id="hand-footer")

    def on_mount(self) -> None:
        self.query_one("#hand-footer", Static).update(render_hints(HINTS))
        self._refresh()

    def _refresh(self) -> None:
        self.selected = max(0, min(self.selected, len(self.state.hand) - 1))
        self.query_one("#hand-body", Static).update(render_hand(
            self.request.source,
            self.state,
            self.selected,
            self.request.seed,
            self.request.mana_costs,
            self.message,
        ))

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+c":
            return
        event.prevent_default()
        event.stop()

        key = translate(event.key)
        if key in CLOSE_KEYS:
            self.app.pop_screen()
            return
        self.message = ""
        try:
            if key in DRAW_KEYS:
                self.state = draw(self.state)
                self.selected = len(self.state.hand) - 1
            elif key == MULLIGAN_KEY:
                self.state = mulligan(self.state, self._rng)
                self.selected = 0
            elif key == BOTTOM_KEY:
                self.state = put_on_bottom(self.state, self.selected)
            elif key == RESHUFFLE_KEY:
                self.state = self._new_game()
                self.selected = 0
            elif key in NAV_DOWN:
                self.selected += 1
            elif key in NAV_UP:
                self.selected -= 1
            else:
                return
        except GoldfishError as exc:
            self.message = str(exc)
        self._refresh()
