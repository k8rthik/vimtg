"""`.` repeats an operator with its motion from a new position.

docs/keybindings.md: `.` repeats the last change, operators included,
and `c` together with the card it added; `u` undoes one change. Each
case runs `d` (and `c`, confirming Lightning Bolt, a duplicate that
bumps its quantity) once at `first`, then `.` on the line that was
`second` in the canonical DECK, and walks back with one `u` per change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from textual.pilot import Pilot

from tests.primitives.harness import DECK, Ed, editor
from tests.primitives.test_operators import LINES, OWN_HEADER, rows, text_without
from vimtg.editor.modes import Mode

BOLT = "    4 Lightning Bolt"


@dataclass(frozen=True)
class Repeat:
    """`op`+`motion` at row `first` takes rows `once`; `.` on the line that
    was row `second` leaves rows `twice` gone in all (original rows)."""

    motion: str
    first: int
    once: tuple[int, ...]
    second: int
    twice: tuple[int, ...]
    count: int = 0
    bug: str = ""


REPEATS = [
    Repeat("w", 7, (7,), 16, (7, 16)),
    Repeat("w", 7, (7, 8), 16, (7, 8, *rows(15, 18)), count=2),
    Repeat("b", 8, (7,), 17, (7, 16)),
    Repeat("}", 8, (8, 9), 17, (8, 9, 17)),
    Repeat("{", 9, (7, 8), 17, (7, 8, 16)),
    Repeat("]]", 8, (8, 9), 13, (8, 9, 13)),
    Repeat("[[", 9, (7, 8), 17, (7, 8, 16), bug=OWN_HEADER),
    Repeat("j", 7, (7, 8), 16, (7, 8, *rows(15, 18))),
    Repeat("k", 8, (7, 8), 17, (7, 8, *rows(15, 18))),
    Repeat("G", 17, rows(17, 20), 13, rows(13, 20)),
    Repeat("gg", 1, (0, 1), 2, (0, 1, 2)),
    Repeat("<C-d>", 17, rows(17, 20), 13, rows(13, 20)),
    Repeat("<C-u>", 1, (0, 1), 3, rows(0, 3)),
]


def _params() -> list[object]:
    out: list[object] = []
    for case in REPEATS:
        marks = [pytest.mark.xfail(strict=True, reason=case.bug)] if case.bug else []
        for op in ("d", "c"):
            typed = f"{case.count or ''}{op}{case.motion}"
            out.append(pytest.param(op, case, id=f"{typed}@{case.first}", marks=marks))
    return out


async def settle(ed: Ed) -> None:
    """Let the card search worker deliver its results."""
    pilot = Pilot(ed.app)
    await pilot.pause()
    await ed.app.workers.wait_for_complete()
    await pilot.pause()


def expected(gone: tuple[int, ...], bolts: int) -> str:
    return text_without(gone).replace(BOLT, f"    {4 + bolts} Lightning Bolt")


@pytest.mark.primitive(
    "d w", "c w", "d b", "c b", "d }", "c }", "d {", "c {", "d ]]", "c ]]",
    "d [[", "c [[", "d j", "c j", "d k", "c k", "d G", "c G", "d gg", "c gg",
    "d ctrl_d", "c ctrl_d", "d ctrl_u", "c ctrl_u",
)
@pytest.mark.parametrize(("op", "case"), _params())
@pytest.mark.asyncio
async def test_dot_repeats_operator_and_motion(tmp_path: Path, op: str, case: Repeat) -> None:
    changes = 1 if op == "c" else 0  # each c adds one Lightning Bolt
    async with editor(tmp_path) as ed:
        ed.press(f"{case.first + 1}G {case.count or ''}{op}{case.motion}")
        if op == "c":
            assert ed.mode is Mode.INSERT
            ed.press("lightning<Space>bolt")
            await settle(ed)
            ed.press("<CR>")
        assert ed.mode is Mode.NORMAL
        once = expected(case.once, changes)
        assert ed.text == once
        kept = [row for row in range(len(LINES)) if row not in case.once]
        ed.press(f"{kept.index(case.second) + 1}G .")
        await settle(ed)
        assert ed.mode is Mode.NORMAL
        assert ed.text == expected(case.twice, 2 * changes)
        ed.press("u")
        assert ed.text == once
        ed.press("u")
        assert ed.text == DECK
