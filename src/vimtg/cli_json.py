"""The JSON documents `vimtg <command> --json` prints.

Every shape the CLI emits is chosen here, once: commands build the
domain result and hand it to one of these pure functions. Each
document names itself in `"schema": "vimtg.<kind>/1"`; keys are
snake_case, numbers stay numbers and a value that is absent (no price,
no format) is null. A breaking change to a shape bumps its version.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from vimtg.domain.validation import ValidationError, ValidationReport


def dumps(doc: object) -> str:
    """The document as printed: indented, UTF-8 card names kept as is."""
    return json.dumps(doc, indent=2, ensure_ascii=False)


def _schema(kind: str) -> str:
    return f"vimtg.{kind}/1"


class ProblemJson(TypedDict):
    line: int | None
    level: str
    message: str
    code: str | None


class ValidationJson(TypedDict):
    schema: str
    file: str
    format: str | None
    ok: bool
    legality_checked: bool
    problems: list[ProblemJson]
    bracket: str | None


def _problem(problem: ValidationError) -> ProblemJson:
    return {
        "line": problem.line_number,
        "level": problem.level,
        "message": problem.message,
        "code": problem.code or None,
    }


def validation_doc(file: str, report: ValidationReport, ok: bool) -> ValidationJson:
    """`vimtg validate --json`: `ok` is what the exit code says (no
    errors, and no warnings either under --strict)."""
    return {
        "schema": _schema("validation"),
        "file": file,
        "format": report.fmt or None,
        "ok": ok,
        "legality_checked": report.legality_checked,
        "problems": [_problem(p) for p in report.problems],
        "bracket": report.bracket or None,
    }
