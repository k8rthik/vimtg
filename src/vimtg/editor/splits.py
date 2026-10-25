"""Pane requests — the pure model behind :edhrec and the side pane.

The editor has one side pane, hosting the live analytics readout or
EDHREC recommendations. Handlers describe what to open; the TUI layer
owns the widgets, the pane's placement (beside the deck when the
terminal is wide enough, hidden otherwise) and its focus.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EdhrecOpen:
    """Request to open EDHREC recommendations for the deck's commander(s)."""

    commanders: tuple[str, ...]
    initial_tab: str = ""
