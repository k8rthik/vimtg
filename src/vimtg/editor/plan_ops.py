"""Sideboard-plan edits — the pure engine behind zi/zo, :plan, and ]v.

A plan is text: a 'VS: name' header with indented '-N Card' / '+N Card'
lines. Every operation here rewrites that text and returns a new
Buffer; the session layer records history and moves marks.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass

from vimtg.domain.card import Card
from vimtg.domain.deck_lines import parse_plan_entry, parse_plan_header
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.command_completer import fuzzy_score

PLAN_INDENT = "    "
SIGN_OUT = "-"
SIGN_IN = "+"


@dataclass(frozen=True)
class PlanBlock:
    """Where one plan lives in the buffer."""

    name: str
    header_row: int
    entry_rows: tuple[int, ...] = ()

    @property
    def last_row(self) -> int:
        return self.entry_rows[-1] if self.entry_rows else self.header_row


@dataclass(frozen=True)
class PlanEntryLine:
    row: int
    sign: str
    quantity: int
    card_name: str


@dataclass(frozen=True)
class PlanEditResult:
    buffer: Buffer
    message: str
    error: bool = False
    inserted_row: int | None = None
    deleted_row: int | None = None


def plan_blocks(buffer: Buffer) -> tuple[PlanBlock, ...]:
    """Every plan block in buffer order."""
    blocks: list[PlanBlock] = []
    for i in range(buffer.line_count()):
        bl = buffer.get_line(i)
        if bl.line_type == LineType.PLAN_HEADER:
            name = parse_plan_header(bl.text) or ""
            blocks.append(PlanBlock(name=name, header_row=i))
        elif bl.line_type == LineType.PLAN_ENTRY and blocks:
            last = blocks[-1]
            blocks[-1] = PlanBlock(
                name=last.name,
                header_row=last.header_row,
                entry_rows=last.entry_rows + (i,),
            )
    return tuple(blocks)


def find_block(buffer: Buffer, name: str) -> PlanBlock | None:
    """The plan block named `name` (case-insensitive), else None."""
    wanted = name.strip().lower()
    for block in plan_blocks(buffer):
        if block.name.lower() == wanted:
            return block
    return None


def block_at(buffer: Buffer, row: int) -> PlanBlock | None:
    """The plan block whose header or entries include `row`."""
    for block in plan_blocks(buffer):
        if row == block.header_row or row in block.entry_rows:
            return block
    return None


def entry_lines(buffer: Buffer, block: PlanBlock) -> tuple[PlanEntryLine, ...]:
    """The parsed entries of a block, in buffer order."""
    out: list[PlanEntryLine] = []
    for row in block.entry_rows:
        parsed = parse_plan_entry(buffer.get_line(row).text)
        if parsed is None:
            continue
        sign, quantity, _ = parsed
        out.append(PlanEntryLine(
            row=row, sign=sign, quantity=quantity,
            card_name=buffer.card_name_at(row) or "",
        ))
    return tuple(out)


def plan_totals(buffer: Buffer, block: PlanBlock) -> tuple[int, int]:
    """(outs, ins) copy totals of a block."""
    outs = ins = 0
    for e in entry_lines(buffer, block):
        if e.sign == SIGN_OUT:
            outs += e.quantity
        elif e.sign == SIGN_IN:
            ins += e.quantity
    return outs, ins


def plan_summary(buffer: Buffer, block: PlanBlock) -> str:
    """'-x +y' — the block's running totals."""
    outs, ins = plan_totals(buffer, block)
    return f"-{outs} +{ins}"


def plan_label(buffer: Buffer, block: PlanBlock, sep: str = "  ") -> str:
    """'vs Tron  -4 +4', with a trailing ' !' when unbalanced."""
    outs, ins = plan_totals(buffer, block)
    mark = "" if outs == ins else " !"
    return f"vs {block.name}{sep}-{outs} +{ins}{mark}"


def row_deltas(buffer: Buffer, plan: str) -> dict[int, int]:
    """Net copies each deck row gains or loses under `plan`, keyed by
    buffer row — outs land on mainboard rows, ins on sideboard rows.
    Empty when the plan does not exist. Render-time only."""
    block = find_block(buffer, plan)
    if block is None:
        return {}
    by_key: dict[tuple[str, LineType], int] = {}
    for e in entry_lines(buffer, block):
        if e.sign == SIGN_OUT:
            key = (e.card_name.lower(), LineType.CARD_ENTRY)
            by_key[key] = by_key.get(key, 0) - e.quantity
        elif e.sign == SIGN_IN:
            key = (e.card_name.lower(), LineType.SIDEBOARD_ENTRY)
            by_key[key] = by_key.get(key, 0) + e.quantity
    deltas: dict[int, int] = {}
    for i in range(buffer.line_count()):
        line_type = buffer.get_line(i).line_type
        if line_type not in (LineType.CARD_ENTRY, LineType.SIDEBOARD_ENTRY):
            continue
        name = buffer.card_name_at(i)
        if name is None:
            continue
        delta = by_key.get((name.lower(), line_type))
        if delta:
            deltas[i] = delta
    return deltas


def plan_search(
    buffer: Buffer, resolved: dict[str, Card], query: str, limit: int = 20
) -> list[Card]:
    """Card-search results for a line opened inside a plan block: the
    deck's own mainboard and sideboard cards, fuzzy-matched on name.
    Sideboard cards rank first (boarding in is the common case); a name
    with no card data still shows up as a bare Card."""
    seen: set[str] = set()
    ranked: list[tuple[int, int, str]] = []
    for zone_rank, zone in ((0, LineType.SIDEBOARD_ENTRY), (1, LineType.CARD_ENTRY)):
        for i in range(buffer.line_count()):
            if buffer.get_line(i).line_type != zone:
                continue
            name = buffer.card_name_at(i)
            if not name or name.lower() in seen:
                continue
            score = fuzzy_score(query.lower(), name.lower())
            if score is None:
                continue
            seen.add(name.lower())
            ranked.append((zone_rank, score, name))
    ranked.sort()
    out: list[Card] = []
    for _, _, name in ranked[:limit]:
        card = resolved.get(name)
        if card is None:
            card = Card.from_scryfall({"id": f"deck:{name}", "name": name})
        out.append(card)
    return out


def next_plan_row(buffer: Buffer, row: int, forward: bool) -> int | None:
    """Header row of the next (or previous) plan block from `row`."""
    rows = [b.header_row for b in plan_blocks(buffer)]
    if forward:
        return next((r for r in rows if r > row), None)
    return next((r for r in reversed(rows) if r < row), None)


def ensure_plan(buffer: Buffer, name: str) -> tuple[Buffer, int, bool]:
    """(buffer, header_row, created): the plan named `name`, appended as
    a fresh 'VS: name' block at the end when missing. New blocks are
    written normalize-stable (blank line before) so cleanup never
    shifts them."""
    block = find_block(buffer, name)
    if block is not None:
        return buffer, block.header_row, False
    header = f"VS: {name.strip()}"
    count = buffer.line_count()
    if count == 1 and buffer.get_line(0).line_type == LineType.BLANK:
        return buffer.set_line(0, header), 0, True
    if buffer.get_line(count - 1).line_type != LineType.BLANK:
        buffer = buffer.append_line("")
    buffer = buffer.append_line(header)
    return buffer, buffer.line_count() - 1, True


def _insert_row_for(
    buffer: Buffer, block: PlanBlock, sign: str
) -> int:
    """Where a new entry of `sign` goes: outs stay grouped right after
    the header (after the last out), ins after everything."""
    if sign == SIGN_IN:
        return block.last_row + 1
    outs = [e.row for e in entry_lines(buffer, block) if e.sign == SIGN_OUT]
    return (outs[-1] if outs else block.header_row) + 1


def board(
    buffer: Buffer, row: int, plan: str, direction: str, count: int
) -> PlanEditResult:
    """Board the deck card on `row` in or out of `plan`.

    `direction` is 'out' (mo) or 'in' (mi). On a mainboard card, out
    grows its '-N' entry and in shrinks it; on a sideboard card, in
    grows its '+N' entry and out shrinks it. count 0 means every copy.
    Entries are clamped to the copies the zone actually holds and
    removed when they reach zero.
    """
    line_type = buffer.get_line(row).line_type
    if line_type == LineType.CARD_ENTRY:
        sign, verb = SIGN_OUT, "out"
        grow = direction == "out"
    elif line_type == LineType.SIDEBOARD_ENTRY:
        sign, verb = SIGN_IN, "in"
        grow = direction == "in"
    else:
        return PlanEditResult(
            buffer,
            "E: zi/zo board the mainboard or sideboard card under the cursor",
            error=True,
        )
    block = find_block(buffer, plan)
    if block is None:
        return PlanEditResult(
            buffer, f"E: No plan named {plan} — :plan {plan} to create it", error=True
        )
    name = buffer.card_name_at(row) or ""
    copies = buffer.quantity_at(row) or 0
    existing = next(
        (
            e for e in entry_lines(buffer, block)
            if e.sign == sign and e.card_name.lower() == name.lower()
        ),
        None,
    )
    current = existing.quantity if existing else 0

    if grow:
        step = copies if count == 0 else count
        new = min(current + step, copies)
        if new == current:
            return PlanEditResult(
                buffer, f"vs {block.name}: all {copies} {name} already {verb}"
            )
    else:
        if current == 0:
            return PlanEditResult(
                buffer, f"E: {name} is not boarded {verb} in vs {block.name}", error=True
            )
        step = current if count == 0 else count
        new = max(current - step, 0)

    inserted_row: int | None = None
    deleted_row: int | None = None
    if existing is not None and new == 0:
        buffer, _ = buffer.delete_lines(existing.row, existing.row)
        deleted_row = existing.row
    elif existing is not None:
        buffer = buffer.set_quantity(existing.row, new)
    else:
        inserted_row = _insert_row_for(buffer, block, sign)
        buffer = buffer.insert_line(inserted_row, f"{PLAN_INDENT}{sign}{new} {name}")

    after = find_block(buffer, plan)
    summary = plan_summary(buffer, after) if after else ""
    what = f"{sign}{new} {name}" if new else f"{name} removed from plan"
    return PlanEditResult(
        buffer,
        f"vs {block.name}: {what}  ({summary})",
        inserted_row=inserted_row,
        deleted_row=deleted_row,
    )
