"""Operators d, y, c over the exclusive motions w b { } [[ ]].

Every expectation comes from docs/keybindings.md: exclusive targets stop
short of the line they land on and never eat a section's blank line or
header (nor cross from DCK: into SB:); `dw` is this card, `db` the card
above, `d}` to the end of the section, `d{` the cards above in the
section, `d]]` up to (not including) the next header. Each case runs
for all three operators against one row table:

  d  removes the rows, fills the unnamed register and "1, one `u` undoes
  y  leaves the text alone, fills "0 and the unnamed register
  c  removes the rows into insert mode; `Esc` returns to normal mode

An empty range changes nothing, touches no register, and is not an undo
step. Rows are the canonical DECK's (map in harness.py). A count is
tried both before the operator (2dw) and before the motion (d2w).

The table helpers here are shared with the other test_operators* files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.primitives.harness import DECK, Ed, editor
from vimtg.editor.modes import Mode

LINES = tuple(DECK.splitlines())
_CARD = re.compile(r"^\s*\d+ ")
CARD_ROWS = tuple(i for i, text in enumerate(LINES) if _CARD.match(text))
OPS = ("d", "y", "c")


def rows(first: int, last: int) -> tuple[int, ...]:
    return tuple(range(first, last + 1))


@dataclass(frozen=True)
class Case:
    """`op` + `motion` from `start`: the rows it acts on, exactly.

    covered  rows the operator takes, in order (the register's lines);
             () is an empty range
    gone     rows missing from the text afterwards, when the deck's own
             tidying also drops a section header the delete emptied
             (with one blank of the pair it leaves); default `covered`
    tidy     compare the surviving cards and their zones only: the
             delete leaves a header-less run the deck tidies its own way
    """

    motion: str
    start: int
    covered: tuple[int, ...]
    count: int = 0
    gone: tuple[int, ...] | None = None
    tidy: bool = False
    bug: str = ""
    bug_ops: str = "dyc"


@dataclass(frozen=True)
class Keeps:
    """`op` + `motion` from a line whose exact range the spec leaves
    open (a header, a blank, the metadata): only what must survive.

    cards    rows of cards that must survive, in their zone (for d and c)
    lines    other rows that must survive (zone and section headers)
    lost     rows of cards that must be gone
    """

    motion: str
    start: int
    cards: tuple[int, ...]
    lines: tuple[int, ...] = ()
    lost: tuple[int, ...] = ()
    count: int = 0
    bug: str = ""
    bug_ops: str = "dyc"


def key_forms(op: str, motion: str, count: int) -> list[tuple[str, str]]:
    """(id, keys) for each way to type op + motion with this count."""
    if not count:
        return [(f"{op}{motion}", f"{op}{motion}")]
    return [
        (f"{count}{op}{motion}", f"{count}{op}{motion}"),
        (f"{op}{count}{motion}", f"{op}{count}{motion}"),
    ]


def params(cases: list[Case | Keeps]) -> list[object]:
    out: list[object] = []
    for case in cases:
        for op in OPS:
            marks = []
            if case.bug and op in case.bug_ops:
                marks.append(pytest.mark.xfail(strict=True, reason=case.bug))
            for ident, typed in key_forms(op, case.motion, case.count):
                out.append(pytest.param(
                    op, case, f"{case.start + 1}G {typed}",
                    id=f"{ident}@{case.start}", marks=marks,
                ))
    return out


def text_without(gone: tuple[int, ...] | set[int]) -> str:
    return "".join(line + "\n" for i, line in enumerate(LINES) if i not in gone)


def card_zones(lines: list[str] | tuple[str, ...]) -> dict[str, str]:
    """Card line (stripped) -> the zone block it sits in."""
    zone = ""
    out: dict[str, str] = {}
    for text in lines:
        if text.strip() in ("DCK:", "SB:"):
            zone = text.strip()
        elif _CARD.match(text):
            out[text.strip()] = zone
    return out


ZONES = card_zones(LINES)


def assert_cards_and_zones(ed: Ed, card_rows: tuple[int, ...]) -> None:
    assert ed.cards == [LINES[i].strip() for i in card_rows]
    assert card_zones(ed.lines) == {LINES[i].strip(): ZONES[LINES[i].strip()] for i in card_rows}


def finish_change(ed: Ed, op: str) -> None:
    """After d or c: back in normal mode (c through its card search)."""
    if op == "c":
        assert ed.mode is Mode.INSERT
        ed.press("<Esc>")
    assert ed.mode is Mode.NORMAL


async def check_empty(tmp_path: Path, op: str, seq: str) -> None:
    async with editor(tmp_path) as ed:
        # An earlier change: one u after the no-op must undo it
        ed.press("18G +")
        bumped = ed.text
        assert bumped != DECK
        ed.press(seq)
        if op == "c":
            ed.press("<Esc>")
        assert ed.mode is Mode.NORMAL
        assert ed.text == bumped
        assert ed.register() == ()
        assert ed.register("0") == ()
        assert ed.register("1") == ()
        ed.press("u")
        assert ed.text == DECK


async def check_case(tmp_path: Path, op: str, case: Case, seq: str) -> None:
    if not case.covered:
        await check_empty(tmp_path, op, seq)
        return
    taken = tuple(LINES[i] for i in case.covered)
    async with editor(tmp_path) as ed:
        ed.press(seq)
        if op == "y":
            assert ed.mode is Mode.NORMAL
            assert ed.text == DECK
            assert ed.modified is False
            assert ed.register("0") == taken
            assert ed.register() == taken
            assert ed.register("1") == ()  # a yank is no delete
            return
        finish_change(ed, op)
        assert ed.register("0") == ()  # a delete is no yank
        if case.tidy:
            assert_cards_and_zones(ed, tuple(i for i in CARD_ROWS if i not in case.covered))
        else:
            assert ed.text == text_without(case.gone or case.covered)
        assert ed.register() == taken
        assert ed.register("1") == taken
        assert ed.modified is True
        ed.press("u")
        assert ed.text == DECK
        assert ed.modified is False


async def check_keeps(tmp_path: Path, op: str, case: Keeps, seq: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(seq)
        if op == "y":
            assert ed.mode is Mode.NORMAL
            assert ed.text == DECK
            assert ed.modified is False
            return
        finish_change(ed, op)
        zones = card_zones(ed.lines)
        for row in case.cards:
            card = LINES[row].strip()
            assert zones.get(card) == ZONES[card], f"{card!r} lost or moved"
        assert all(zones[card] == ZONES[card] for card in zones)
        for row in case.lost:
            assert LINES[row].strip() not in zones
        for row in case.lines:
            assert LINES[row] in ed.lines, f"{LINES[row]!r} was deleted"
        ed.press("u")
        assert ed.text == DECK


async def run(tmp_path: Path, op: str, case: Case | Keeps, seq: str) -> None:
    if isinstance(case, Keeps):
        await check_keeps(tmp_path, op, case, seq)
    else:
        await check_case(tmp_path, op, case, seq)


ALL_CARDS = CARD_ROWS
INTERIOR = (
    "BUG: a counted exclusive range deletes the // Instant header between "
    "its cards and refiles Fire // Ice under // Creature; expected only the "
    "cards to go, the header to stay"
)

BLANK_TAKEN = (
    "BUG: from the blank before // Instant the range is that blank, which "
    "lands in the register (the deck's tidying puts it back); expected an "
    "empty range"
)

W: list[Case | Keeps] = [
    Case("w", 7, (7,)),
    Case("w", 7, (7, 8), count=2),
    Case("w", 9, (9,)),  # last card of its section: not the blank after
    Case("w", 12, (12,)),  # first card of its section
    Case("w", 17, (17,)),  # last mainboard card: SB: stays
    Case("w", 17, (17,), count=2),  # never on into the sideboard
    Case("w", 20, (20,)),  # last card of the deck
    Case("w", 20, (20,), count=3),  # fewer cards left: through the last
    Case("w", 9, (9, 12), count=2, bug=INTERIOR),
    Case("w", 10, (), bug=BLANK_TAKEN),  # blank before // Instant
    Keeps("w", 6, ALL_CARDS, (4, 19)),  # a header: no card goes
    Keeps("w", 0, ALL_CARDS, (4, 6, 19)),  # the metadata: no card goes
]

B: list[Case | Keeps] = [
    Case("b", 8, (7,)),
    Case("b", 9, (7, 8), count=2),
    Case("b", 8, (7,), count=2),  # only one card above: just that one
    Case("b", 9, (8,)),  # last card of its section
    Case("b", 12, (9,)),  # first card of a section: the card above it
    Case("b", 11, (9,)),  # from a header
    Case("b", 14, (13,)),  # from a blank line
    Case("b", 20, ()),  # sideboard's first card: never back across SB:
    Case("b", 7, ()),  # first card: nothing above
    Case("b", 0, ()),  # deck top
    Case("b", 13, (9, 12), count=2, bug=INTERIOR),
]

RBRACE: list[Case | Keeps] = [
    Case("}", 7, rows(7, 9), gone=rows(6, 10)),  # whole section: header goes
    Case("}", 8, (8, 9)),
    Case("}", 9, (9,)),
    Case("}", 12, (12, 13), gone=rows(11, 14)),
    Case("}", 17, (17,)),  # last mainboard card: SB: stays
    Case("}", 20, (20,)),  # deck bottom
    Case("}", 8, rows(8, 13), count=2),  # through the next section
    Case("}", 16, (16, 17), count=2, gone=rows(15, 18)),
    Case("}", 12, rows(12, 17), count=3, gone=rows(11, 18)),
    Keeps("}", 6, (12, 13, 16, 17, 20), (4, 11, 15, 19), lost=(7, 8, 9)),  # header
    Keeps("}", 18, ALL_CARDS, (4, 19)),  # blank before SB:
    Keeps("}", 0, (12, 13, 16, 17, 20), (4, 11, 15, 19)),  # the metadata
]

LBRACE: list[Case | Keeps] = [
    Case("{", 9, (7, 8)),
    Case("{", 8, (7,)),
    Case("{", 13, (12,)),
    Case("{", 17, (16,)),  # last mainboard card
    Case("{", 7, ()),  # first card of the deck's first section
    Case("{", 12, (), bug=(  # first card of a later section
        "DOC: keybindings says d{ takes the cards above the cursor in its "
        "section, none here; it deletes the whole // Creature section above"
    )),
    Case("{", 20, ()),  # sideboard's first card: nothing above in SB:
    Case("{", 0, ()),  # deck top
    Case("{", 13, (7, 8, 9, 12), count=2, gone=(6, 7, 8, 9, 10, 12), bug=INTERIOR),
    Keeps("{", 15, (7, 8, 9, 16, 17, 20), (4, 6, 15, 19)),  # from a header
    Keeps("{", 14, (7, 8, 9, 16, 17, 20), (4, 6, 15, 19)),  # from a blank
]

RBRACKET: list[Case | Keeps] = [
    Case("]]", 7, rows(7, 9), gone=rows(6, 10)),
    Case("]]", 8, (8, 9)),
    Case("]]", 12, (12, 13), gone=rows(11, 14)),
    Case("]]", 16, (16, 17), gone=rows(15, 18)),  # no header left: not into SB:
    Case("]]", 17, (17,)),
    Case("]]", 20, (20,)),  # deck bottom
    Case("]]", 7, rows(7, 13), count=2, gone=rows(6, 14)),
    Case("]]", 12, rows(12, 17), count=2, gone=rows(11, 18)),
    Case("]]", 10, (), bug=BLANK_TAKEN),  # the blank before a header
    Keeps("]]", 6, (12, 13, 16, 17, 20), (4, 11, 15, 19), lost=(7, 8, 9)),  # header
    Keeps("]]", 0, ALL_CARDS, (4, 6, 11, 15, 19)),  # deck top
]

OWN_HEADER = (
    "DOC: d[[ takes the section header it lands on (cards left header-less); "
    "the brief says exclusive motions never delete a header, the doc only "
    "protects the next section's"
)

LBRACKET: list[Case | Keeps] = [
    Case("[[", 9, (7, 8), bug=OWN_HEADER),
    Case("[[", 13, (12,), bug=OWN_HEADER),
    Case("[[", 17, (16,), bug=OWN_HEADER),  # last mainboard card
    Case("[[", 7, (), bug=OWN_HEADER),  # first card: only its header above
    Case("[[", 14, (12, 13), gone=rows(11, 14), bug=OWN_HEADER),  # blank
    Case("[[", 15, (12, 13), gone=rows(11, 14), bug=OWN_HEADER),  # header
    Case("[[", 13, (7, 8, 9, 12), count=2, gone=(6, 7, 8, 9, 10, 12), bug=(
        "BUG: 2d[[ on Fire // Ice deletes // Creature through Lightning Bolt, "
        "the // Instant header too, leaving Fire // Ice under no header; "
        "expected // Instant to stay"
    )),
    Case("[[", 20, ()),  # sideboard card: never back into DCK:
    Case("[[", 0, ()),  # deck top
]


@pytest.mark.primitive("d w", "y w", "c w")
@pytest.mark.parametrize(("op", "case", "seq"), params(W))
@pytest.mark.asyncio
async def test_w(tmp_path: Path, op: str, case: Case | Keeps, seq: str) -> None:
    await run(tmp_path, op, case, seq)


@pytest.mark.primitive("d b", "y b", "c b")
@pytest.mark.parametrize(("op", "case", "seq"), params(B))
@pytest.mark.asyncio
async def test_b(tmp_path: Path, op: str, case: Case | Keeps, seq: str) -> None:
    await run(tmp_path, op, case, seq)


@pytest.mark.primitive("d }", "y }", "c }")
@pytest.mark.parametrize(("op", "case", "seq"), params(RBRACE))
@pytest.mark.asyncio
async def test_section_forward(tmp_path: Path, op: str, case: Case | Keeps, seq: str) -> None:
    await run(tmp_path, op, case, seq)


@pytest.mark.primitive("d {", "y {", "c {")
@pytest.mark.parametrize(("op", "case", "seq"), params(LBRACE))
@pytest.mark.asyncio
async def test_section_backward(tmp_path: Path, op: str, case: Case | Keeps, seq: str) -> None:
    await run(tmp_path, op, case, seq)


@pytest.mark.primitive("d ]]", "y ]]", "c ]]")
@pytest.mark.parametrize(("op", "case", "seq"), params(RBRACKET))
@pytest.mark.asyncio
async def test_header_forward(tmp_path: Path, op: str, case: Case | Keeps, seq: str) -> None:
    await run(tmp_path, op, case, seq)


@pytest.mark.primitive("d [[", "y [[", "c [[")
@pytest.mark.parametrize(("op", "case", "seq"), params(LBRACKET))
@pytest.mark.asyncio
async def test_header_backward(tmp_path: Path, op: str, case: Case | Keeps, seq: str) -> None:
    await run(tmp_path, op, case, seq)
