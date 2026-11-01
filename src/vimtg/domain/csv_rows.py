"""Reading card rows out of a vendor CSV (Moxfield, Archidekt, ManaBox,
Deckbox exports). Deck imports and collection files share these so a
header spelling learnt for one works for the other."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vimtg.domain.deck_lines import strip_printing_suffix

# Header names seen in the wild, first match wins
NAME_HEADERS: tuple[str, ...] = ("Name", "Card Name", "Card")
COUNT_HEADERS: tuple[str, ...] = ("Count", "Quantity", "Qty")


class MalformedCsvError(ValueError):
    """CSV text the csv module cannot split into rows."""


@dataclass(frozen=True)
class CsvTable:
    """A CSV's header row and its data rows, each paired with the line
    number it ends on."""

    fieldnames: Sequence[str] | None
    rows: tuple[tuple[int, Mapping[str, str | None]], ...]


def read_csv(text: str) -> CsvTable:
    """Split `text` into a header and rows.

    Raises :class:`MalformedCsvError` naming the line an unreadable row
    starts on. In practice that is a quote that never closes: it runs
    to the end of the file, and the csv module stops it at its field
    size limit.
    """
    reader = csv.DictReader(io.StringIO(text))
    rows: list[tuple[int, Mapping[str, str | None]]] = []
    start = 1
    try:
        fieldnames = reader.fieldnames
        start = reader.line_num + 1
        for row in reader:
            rows.append((reader.line_num, row))
            start = reader.line_num + 1
    except csv.Error as exc:
        raise MalformedCsvError(
            f"unreadable row starting on line {start} ({exc}); "
            "look for an unclosed quote there"
        ) from exc
    return CsvTable(fieldnames, tuple(rows))


def find_column(fieldnames: Sequence[str] | None, candidates: Sequence[str]) -> str | None:
    """The header in `fieldnames` that spells one of `candidates`, ignoring
    case and surrounding whitespace, or None. Candidate order wins over
    header order, so "Count" beats "Quantity" when a file has both."""
    if not fieldnames:
        return None
    by_key = {name.strip().casefold(): name for name in reversed(fieldnames)}
    for candidate in candidates:
        found = by_key.get(candidate.casefold())
        if found is not None:
            return found
    return None


def card_name_cell(row: Mapping[str, str | None], column: str | None) -> str:
    """The card name in `column`, without any printing suffix
    ('Goblin Guide (ZEN) 126 *F*' -> 'Goblin Guide'); '' when absent.
    DictReader yields None (not the default) for short rows."""
    if column is None:
        return ""
    return strip_printing_suffix(row.get(column) or "")


def count_cell(row: Mapping[str, str | None], column: str | None) -> int | None:
    """The integer in `column`, or None for a missing, empty, or
    non-integer cell. Callers decide whether that means 1 or a skipped row."""
    if column is None:
        return None
    raw = row.get(column)
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        return None
