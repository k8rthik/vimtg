"""Buffer linting — validation results mapped onto buffer rows.

TUI-agnostic bridge between domain validation and the deck view's
gutter signs. Row mapping is exact: Buffer.to_text() is a line-for-line
join and parse_deck_text numbers lines from 1, so row = line_number - 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.validation import ValidationError, validate_deck

if TYPE_CHECKING:
    from vimtg.domain.card import Card
    from vimtg.domain.deck import Deck
    from vimtg.editor.buffer import Buffer


@dataclass(frozen=True)
class LintResult:
    line_errors: dict[int, ValidationError]  # 0-based row -> worst issue
    deck_errors: tuple[ValidationError, ...]  # no line anchor
    error_count: int
    warning_count: int


EMPTY_LINT = LintResult(
    line_errors={}, deck_errors=(), error_count=0, warning_count=0
)


def effective_format(deck: Deck, default_format: str) -> str:
    """The deck's declared format, falling back to the global setting.

    Normalized to lowercase: Scryfall legality keys are lowercase, and
    hand-typed '// Format: Commander' must mean the same as 'commander'
    everywhere (a raw-cased key once silently emptied card search).
    """
    return (deck.metadata.format or default_format).strip().lower()


def _format_metadata_row(buffer: Buffer) -> int | None:
    """Row of the '// Format:' metadata line, or None."""
    from vimtg.domain.deck_lines import match_metadata

    for i in range(buffer.line_count()):
        meta = match_metadata(buffer.get_line(i).text)
        if meta is not None and meta[0] == "Format":
            return i
    return None


def lint_buffer(
    buffer: Buffer,
    resolved: dict[str, Card],
    default_format: str = "",
    deck: Deck | None = None,
) -> LintResult:
    """Validate the buffer's deck and map issues to buffer rows.

    Callers that already parsed the buffer can pass `deck` to skip
    the re-parse.
    """
    if deck is None:
        deck = parse_deck_text(buffer.to_text())

    errors = validate_deck(deck, resolved, effective_format(deck, default_format))

    line_errors: dict[int, ValidationError] = {}
    deck_errors: list[ValidationError] = []
    fmt_row = _format_metadata_row(buffer)
    for err in errors:
        if err.line_number is None:
            # The unknown-format warning belongs on the '// Format:'
            # line itself — a gutter sign the user actually sees.
            if err.message.startswith("Unknown format") and fmt_row is not None:
                err = ValidationError(
                    level=err.level, message=err.message,
                    line_number=fmt_row + 1,
                )
                row = fmt_row
            else:
                deck_errors.append(err)
                continue
        else:
            row = err.line_number - 1
        existing = line_errors.get(row)
        # Worst issue wins the row: error beats warning, first wins ties
        if existing is None or (
            existing.level != "error" and err.level == "error"
        ):
            line_errors[row] = err

    return LintResult(
        line_errors=line_errors,
        deck_errors=tuple(deck_errors),
        error_count=sum(1 for e in errors if e.level == "error"),
        warning_count=sum(1 for e in errors if e.level == "warning"),
    )
