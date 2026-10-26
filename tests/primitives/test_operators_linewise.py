"""Operators d, y, c over the linewise motions j k G gg Ctrl-D Ctrl-U.

docs/keybindings.md: as operator targets these include the line they
land on. README: `dj`/`dk` use raw line arithmetic (blanks count), `d8G`
stops at line 8 and `dG` runs to the end; `{n}gg` is line n like `{n}G`.
A motion that cannot move (j on the last line, k on the first) takes
nothing, as in vim. The row tables run through the same checks as the
exclusive motions (see test_operators.py).

Ctrl-D/Ctrl-U move half a page, a size the spec ties to the screen, so
the canonical deck only pins cases where any half page of a 40-row
terminal reaches the deck's edge; a long deck then checks that the
operator covers exactly the rows between the cursor and where the bare
motion lands, with and without a count.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import editor
from tests.primitives.test_operators import Case, finish_change, params, rows, run
from vimtg.editor.modes import Mode

J: list[Case] = [
    Case("j", 7, (7, 8)),
    Case("j", 7, rows(7, 9), count=2, gone=rows(6, 10)),
    Case("j", 9, (9, 10), tidy=True),  # last card of a section and its blank
    Case("j", 16, (16, 17), gone=rows(15, 18)),  # first card of a section
    Case("j", 17, (17, 18), tidy=True),  # last mainboard card
    Case("j", 20, ()),  # deck bottom: j cannot move
    Case("j", 19, (19, 20), tidy=True),  # SB: and its card
    Case("j", 6, (6, 7), tidy=True),  # a header
    Case("j", 10, (10, 11), tidy=True),  # a blank line
    Case("j", 0, (0, 1)),  # deck top
]

K: list[Case] = [
    Case("k", 8, (7, 8)),
    Case("k", 9, rows(7, 9), count=2, gone=rows(6, 10)),
    Case("k", 7, (6, 7), tidy=True),  # first card of a section: its header
    Case("k", 12, (11, 12), tidy=True),
    Case("k", 17, (16, 17), gone=rows(15, 18)),  # last card of a section
    Case("k", 20, (19, 20), tidy=True),  # deck bottom
    Case("k", 10, (9, 10), tidy=True),  # a blank line
    Case("k", 11, (10, 11), tidy=True),  # a header
    Case("k", 1, (0, 1)),
    Case("k", 0, ()),  # deck top: k cannot move
]

BIG_G: list[Case] = [
    Case("G", 17, rows(17, 20)),
    Case("G", 20, (20,)),  # deck bottom: just the last line
    Case("G", 0, rows(0, 20), tidy=True),  # deck top: everything
    Case("G", 7, (7, 8), count=9),
    Case("G", 12, (12,), count=13),  # its own line
    Case("G", 9, rows(7, 9), count=8, gone=rows(6, 10)),  # backward
    Case("G", 2, rows(0, 2), count=1),
    Case("G", 17, rows(17, 20), count=99),  # past the end: the last line
    Case("G", 15, rows(15, 20), tidy=True),  # a header
    Case("G", 10, rows(10, 20), tidy=True),  # a blank line
]

GG: list[Case] = [
    Case("gg", 2, rows(0, 2)),
    Case("gg", 0, (0,)),  # deck top: just the first line
    Case("gg", 20, rows(0, 20), tidy=True),  # deck bottom: everything
    Case("gg", 7, (7, 8), count=9),
    Case("gg", 20, rows(17, 20), count=18),
    Case("gg", 12, (12,), count=13),  # its own line
    Case("gg", 17, rows(17, 20), count=99),  # past the end: the last line
    Case("gg", 11, rows(8, 11), count=9, tidy=True),  # a header
]

CTRL_D: list[Case] = [
    Case("<C-d>", 14, rows(14, 20)),  # a blank line, to the end
    Case("<C-d>", 13, rows(13, 20)),  # last card of a section
    Case("<C-d>", 11, rows(11, 20), tidy=True),  # a header
    Case("<C-d>", 20, ()),  # deck bottom: Ctrl-D cannot move
]

CTRL_U: list[Case] = [
    Case("<C-u>", 1, (0, 1)),
    Case("<C-u>", 2, rows(0, 2)),
    Case("<C-u>", 0, ()),  # deck top: Ctrl-U cannot move
]


@pytest.mark.primitive("d j", "y j", "c j")
@pytest.mark.parametrize(("op", "case", "seq"), params(J))
@pytest.mark.asyncio
async def test_j(tmp_path: Path, op: str, case: Case, seq: str) -> None:
    await run(tmp_path, op, case, seq)


@pytest.mark.primitive("d k", "y k", "c k")
@pytest.mark.parametrize(("op", "case", "seq"), params(K))
@pytest.mark.asyncio
async def test_k(tmp_path: Path, op: str, case: Case, seq: str) -> None:
    await run(tmp_path, op, case, seq)


@pytest.mark.primitive("d G", "y G", "c G")
@pytest.mark.parametrize(("op", "case", "seq"), params(BIG_G))
@pytest.mark.asyncio
async def test_last_line(tmp_path: Path, op: str, case: Case, seq: str) -> None:
    await run(tmp_path, op, case, seq)


@pytest.mark.primitive("d gg", "y gg", "c gg")
@pytest.mark.parametrize(("op", "case", "seq"), params(GG))
@pytest.mark.asyncio
async def test_first_line(tmp_path: Path, op: str, case: Case, seq: str) -> None:
    await run(tmp_path, op, case, seq)


@pytest.mark.primitive("d ctrl_d", "y ctrl_d", "c ctrl_d")
@pytest.mark.parametrize(("op", "case", "seq"), params(CTRL_D))
@pytest.mark.asyncio
async def test_half_page_down(tmp_path: Path, op: str, case: Case, seq: str) -> None:
    await run(tmp_path, op, case, seq)


@pytest.mark.primitive("d ctrl_u", "y ctrl_u", "c ctrl_u")
@pytest.mark.parametrize(("op", "case", "seq"), params(CTRL_U))
@pytest.mark.asyncio
async def test_half_page_up(tmp_path: Path, op: str, case: Case, seq: str) -> None:
    await run(tmp_path, op, case, seq)


# One section of 60 cards: rows 7-66 are cards, far from either edge
LONG = "// Deck: Long\n// Format: modern\n// Tags:\n\nDCK:\n\n    // Creature\n" + "".join(
    f"    1 Card {n:02d}\n" for n in range(60)
)
LONG_LINES = tuple(LONG.splitlines())


def _half_page_params() -> list[object]:
    out: list[object] = []
    for motion, start in (("<C-d>", 20), ("<C-u>", 60)):
        for op in ("d", "y", "c"):
            for count, typed in (
                (0, f"{op}{motion}"), (2, f"2{op}{motion}"), (2, f"{op}2{motion}"),
            ):
                out.append(pytest.param(op, motion, start, count, typed, id=f"{typed}@{start}"))
    return out


@pytest.mark.primitive(
    "d ctrl_d", "y ctrl_d", "c ctrl_d", "d ctrl_u", "y ctrl_u", "c ctrl_u"
)
@pytest.mark.parametrize(("op", "motion", "start", "count", "typed"), _half_page_params())
@pytest.mark.asyncio
async def test_half_page_covers_through_where_the_motion_lands(
    tmp_path: Path, op: str, motion: str, start: int, count: int, typed: str
) -> None:
    async with editor(tmp_path, LONG) as ed:
        assert ed.text == LONG
        ed.press(f"{start + 1}G {count or ''}{motion}")
        target = ed.row
        assert target != start
        assert (target > start) == (motion == "<C-d>")
        first, last = min(start, target), max(start, target)
        taken = LONG_LINES[first:last + 1]
        ed.press(f"{start + 1}G {typed}")
        if op == "y":
            assert ed.mode is Mode.NORMAL
            assert ed.text == LONG
            assert ed.register("0") == taken
            assert ed.register() == taken
            return
        finish_change(ed, op)
        assert ed.lines == list(LONG_LINES[:first] + LONG_LINES[last + 1:])
        assert ed.register() == taken
        assert ed.register("1") == taken
        ed.press("u")
        assert ed.text == LONG
