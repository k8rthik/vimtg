"""Every text-mode file read, file write and subprocess pipe names its encoding.

Without one, Python uses the locale's encoding: cp1252 on Windows, which
garbles UTF-8 and raises on bytes such as 0x9d (part of a curly quote).
Source and tests both read UTF-8 files, so both are checked.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEXT_METHODS = frozenset({"read_text", "write_text"})
SUBPROCESS_CALLS = frozenset({"run", "Popen", "check_output", "check_call", "call"})
TEXT_FLAGS = frozenset({"text", "universal_newlines"})


def _mode(call: ast.Call) -> object:
    for kw in call.keywords:
        if kw.arg == "mode":
            return kw.value.value if isinstance(kw.value, ast.Constant) else None
    if len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
        return call.args[1].value
    return "r" if len(call.args) <= 1 else None


def _missing_encoding(call: ast.Call) -> bool:
    if any(kw.arg in ("encoding", None) for kw in call.keywords):
        return False
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in TEXT_METHODS:
        return True
    if isinstance(func, ast.Name) and func.id == "open":
        mode = _mode(call)
        return isinstance(mode, str) and "b" not in mode
    if isinstance(func, ast.Attribute) and func.attr in SUBPROCESS_CALLS:
        return any(
            kw.arg in TEXT_FLAGS and isinstance(kw.value, ast.Constant) and kw.value.value
            for kw in call.keywords
        )
    return False


def _offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        f"{path.relative_to(ROOT)}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _missing_encoding(node)
    ]


@pytest.mark.parametrize("folder", ["src", "tests"])
def test_text_file_io_names_its_encoding(folder: str) -> None:
    offenders = [
        hit for path in sorted((ROOT / folder).rglob("*.py")) for hit in _offenders(path)
    ]
    assert not offenders, "add encoding=\"utf-8\":\n" + "\n".join(offenders)


@pytest.mark.parametrize(
    ("snippet", "flagged"),
    [
        ("p.read_text()", True),
        ("p.write_text(s)", True),
        ("open(p)", True),
        ("open(p, 'w')", True),
        ("p.read_text(encoding='utf-8')", False),
        ("open(p, 'rb')", False),
        ("open(p, mode='wb')", False),
        ("p.read_bytes()", False),
        ("subprocess.run(cmd, text=True)", True),
        ("subprocess.run(cmd, text=True, encoding='utf-8')", False),
        ("subprocess.run(cmd, capture_output=True)", False),
    ],
)
def test_the_check_sees_the_calls_it_should(snippet: str, flagged: bool) -> None:
    call = ast.parse(snippet, mode="eval").body
    assert isinstance(call, ast.Call)
    assert _missing_encoding(call) is flagged
