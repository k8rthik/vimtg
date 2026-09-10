"""Shared fixtures and helpers for the history overlay tests."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import App

from vimtg.services.deck_diff_service import DeckDiffService
from vimtg.services.vcs_service import VersionControlService
from vimtg.tui.screens.history_screen import HistoryScreen

DECK_PATH = "/tmp/burn.deck"
STATE_V1 = "4 Lightning Bolt\n4 Goblin Guide\n"
STATE_V2 = "4 Lightning Bolt\n4 Goblin Guide\n4 Monastery Swiftspear\n"
STATE_CURRENT = STATE_V2 + "2 Shock\n"


class HistoryHostApp(App[None]):
    """Minimal app that hosts a single HistoryScreen for pilot tests."""

    def __init__(self, screen: HistoryScreen) -> None:
        super().__init__()
        self._target = screen

    def on_mount(self) -> None:
        self.push_screen(self._target)


def make_history_screen(
    vcs: VersionControlService,
    on_restore: Callable[[str], None] | None = None,
    current_state: str = STATE_CURRENT,
    price_source: str = "usd",
    diff_service: DeckDiffService | None = None,
    on_apply_state: Callable[[str, str], None] | None = None,
) -> HistoryScreen:
    return HistoryScreen(
        vcs_service=vcs,
        diff_service=diff_service or DeckDiffService(),
        current_deck_state=current_state,
        deck_name="Burn",
        on_restore=on_restore,
        price_source=price_source,
        on_apply_state=on_apply_state,
    )
