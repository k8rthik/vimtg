"""Split-view requests — the pure model behind :vsplit / :split / :edhrec
and the Ctrl-W window keys.

The editor supports one split pane beside (or below) the main deck
view, showing either another deck read-only or EDHREC recommendations.
Handlers describe what to open with these frozen dataclasses; the TUI
layer owns the actual widgets.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class SplitDirection(Enum):
    """Vertical = panes side by side; horizontal = stacked."""

    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


class WindowCommand(Enum):
    """A Ctrl-W window command over the editor and its one pane.

    Focus moves to the other window (w W) or the one in a direction
    (h j k l: the pane is right of a vertical split, below a horizontal
    one). CLOSE and ONLY close the pane; QUIT does too, and is :quit
    when there is no pane.
    """

    NEXT = "next"
    LEFT = "left"
    DOWN = "down"
    UP = "up"
    RIGHT = "right"
    CLOSE = "close"
    QUIT = "quit"
    ONLY = "only"


@dataclass(frozen=True)
class SplitOpen:
    """Request to open another deck file in the split pane."""

    direction: SplitDirection
    path: Path


@dataclass(frozen=True)
class EdhrecOpen:
    """Request to open EDHREC recommendations for the deck's commander(s)."""

    commanders: tuple[str, ...]
    direction: SplitDirection = SplitDirection.VERTICAL
    initial_tab: str = ""


@dataclass(frozen=True)
class AnalyticsOpen:
    """Request to open the live deck-analytics pane."""

    direction: SplitDirection = SplitDirection.VERTICAL


def resolve_deck_path(arg: str, current_file: Path | None) -> Path | None:
    """Resolve a user-supplied deck path for a split.

    Relative paths are tried against the current deck's directory first,
    then the working directory (same rule as :merge). Returns None when
    no candidate exists.
    """
    path = Path(arg).expanduser()
    if path.is_absolute():
        return path if path.is_file() else None
    base_dir = current_file.parent if current_file else Path.cwd()
    for candidate in (base_dir / path, Path.cwd() / path):
        if candidate.is_file():
            return candidate
    return None
