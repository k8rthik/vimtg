"""HandScreen — sample hand / goldfish overlay (:hand, Space h).

Draws an opening seven from the main deck and lets the user goldfish:
n/Space draw, m London mulligan (b bottoms the selected card), r
reshuffles a fresh hand; the shared navigation keys (j/k, gg/G,
Ctrl-D/U, Home/End) select a card, ? opens the hand help topic, F1 the
full help, q/Esc close. The game logic lives in domain.sample_hand;
this screen only renders it and maps keys.
"""

from __future__ import annotations

import random

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.events import Key
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
from vimtg.tui.keys import (
    CLOSE_KEYS,
    FULL_HELP_KEY,
    HELP_KEY,
    PENDING,
    VimNav,
    render_hints,
)
from vimtg.tui.screens.floating import FloatingScreen
from vimtg.tui.theme import COLORS

# Game keys → HandScreen method names; the hint bar names every one
ACTIONS: dict[str, str] = {
    "n": "_draw", " ": "_draw", "m": "_mulligan", "b": "_bottom", "r": "_reshuffle",
}

HINTS = (
    ("n/Space", "draw"), ("m", "mulligan"), ("b", "bottom"),
    ("r", "reshuffle"), ("j/k", "select"), ("gg/G", "first/last"),
    ("?", "help"), ("q/Esc", "close"),
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


class HandScreen(FloatingScreen[None]):
    """Sample-hand overlay; the game state is replaced on every action."""

    WINDOW_ID = "hand-window"
    CSS = f"""
    #hand-scroll {{
        height: 1fr;
        scrollbar-size: 1 1;
    }}
    #hand-body {{
        padding: 0 1;
    }}
    #hand-footer {{
        height: 1;
        background: {COLORS['bg']};
    }}
    """

    def __init__(self, request: HandOpen) -> None:
        super().__init__("Sample hand")
        self.request = request
        self._rng = random.Random(request.seed)
        self.state = self._new_game()
        self.selected = 0
        self.message = ""
        self._nav = VimNav()

    def _new_game(self) -> Goldfish:
        source = self.request.source
        return deal(source.library, self._rng, free_mulligan=source.free_mulligan)

    def compose_window(self) -> ComposeResult:
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
        event.prevent_default()
        event.stop()

        key = translate(event.key)
        if key in CLOSE_KEYS:
            self.app.pop_screen()
            return
        if key in (HELP_KEY, FULL_HELP_KEY):
            from vimtg.tui.screens.help_screen import HelpScreen

            self.app.push_screen(HelpScreen(topic="hand" if key == HELP_KEY else None))
            return
        step = self._nav.feed(key, len(self.state.hand))
        if step == PENDING:
            return
        self.message = ""
        if step is not None:
            self._select(step)
        elif (method := ACTIONS.get(key)) is not None:
            try:
                getattr(self, method)()
            except GoldfishError as exc:
                self.message = str(exc)
        else:
            return
        self._refresh()

    def _select(self, step: int | str) -> None:
        last = len(self.state.hand) - 1
        if step == "home":
            self.selected = 0
        elif step == "end":
            self.selected = last
        else:
            self.selected += int(step)

    def _draw(self) -> None:
        self.state = draw(self.state)
        self.selected = len(self.state.hand) - 1

    def _mulligan(self) -> None:
        self.state = mulligan(self.state, self._rng)
        self.selected = 0

    def _bottom(self) -> None:
        self.state = put_on_bottom(self.state, self.selected)

    def _reshuffle(self) -> None:
        self.state = self._new_game()
        self.selected = 0
