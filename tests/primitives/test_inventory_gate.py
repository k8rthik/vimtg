"""Every editor primitive has at least one isolated case, per slice.

Cases declare what they exercise with @pytest.mark.primitive("dd", ...)
on a test function or class. This gate reads those markers from the
source of tests/primitives/test_*.py (so running a subset of tests never
changes its verdict) and compares them with the live inventory.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.primitives.inventory import SLICES, inventory

HERE = Path(__file__).parent


def _marked_ids() -> dict[str, list[str]]:
    """Primitive id -> the 'file:line' places that mark it."""
    found: dict[str, list[str]] = {}
    for path in sorted(HERE.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "primitive"):
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.setdefault(arg.value, []).append(f"{path.name}:{node.lineno}")
    return found


def test_every_inventory_id_belongs_to_a_known_slice() -> None:
    unknown = {pid: s for pid, s in inventory().items() if s not in SLICES}
    assert not unknown


def test_every_marked_id_is_a_real_primitive() -> None:
    real = inventory()
    typos = {pid: where for pid, where in _marked_ids().items() if pid not in real}
    assert not typos, f"marked ids that are not primitives: {typos}"


@pytest.mark.parametrize("slice_name", SLICES)
def test_slice_has_a_case_for_every_primitive(slice_name: str) -> None:
    marked = _marked_ids()
    missing = sorted(
        pid for pid, owner in inventory().items() if owner == slice_name and pid not in marked
    )
    assert not missing, f"{len(missing)} primitives in {slice_name} have no case: {missing}"
