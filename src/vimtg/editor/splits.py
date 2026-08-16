"""Split-view requests — the pure model behind :vsplit / :split / :edhrec.

The editor supports one companion pane beside (or below) the main deck
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


@dataclass(frozen=True)
class SplitOpen:
    """Request to open another deck file in the companion pane."""

    direction: SplitDirection
    path: Path


@dataclass(frozen=True)
class EdhrecOpen:
    """Request to open EDHREC recommendations for the deck's commander(s)."""

    commanders: tuple[str, ...]
    direction: SplitDirection = SplitDirection.VERTICAL
    initial_tab: str = ""


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
