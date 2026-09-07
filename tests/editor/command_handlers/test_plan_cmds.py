"""Tests for :plan / :plans."""

from __future__ import annotations

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import CommandRegistry, EditorContext, parse_command
from vimtg.editor.cursor import Cursor

DECK = (
    "4 Lightning Bolt\n"
    "SB: 3 Alpine Moon\n"
    "\n"
    "VS: Tron\n"
    "    -2 Lightning Bolt\n"
    "    +1 Alpine Moon\n"
    "\n"
    "VS: Burn\n"
    "    -1 Lightning Bolt\n"
)


def _run(
    line: str, text: str = DECK, active: str | None = None, row: int = 0
) -> tuple[EditorContext, Buffer, Cursor]:
    registry = CommandRegistry()
    register_all_commands(registry)
    buffer = Buffer.from_text(text)
    ctx = EditorContext(settings=Settings(), active_plan=active)
    cmd = parse_command(line, row, buffer.line_count())
    buffer, cursor = registry.execute(cmd, buffer, Cursor(row=row), ctx)
    return ctx, buffer, cursor


class TestPlan:
    def test_activates_an_existing_plan(self) -> None:
        ctx, buf, cursor = _run("plan tron")
        assert not ctx.error
        assert ctx.active_plan == "Tron"
        assert ctx.active_plan_set
        assert cursor.row == 3
        assert buf.to_text() == DECK
        assert not ctx.modified
        assert ctx.message == "vs Tron  -2 +1 !"

    def test_creates_a_missing_plan(self) -> None:
        ctx, buf, cursor = _run("plan Mirror")
        assert ctx.active_plan == "Mirror"
        assert ctx.modified
        assert buf.to_text().endswith("VS: Burn\n    -1 Lightning Bolt\n\nVS: Mirror\n")
        assert cursor.row == buf.line_count() - 1
        assert "vs Mirror" in ctx.message

    def test_bare_plan_cycles(self) -> None:
        ctx, _, cursor = _run("plan")
        assert ctx.active_plan == "Tron"
        ctx, _, cursor = _run("plan", active="Tron")
        assert ctx.active_plan == "Burn"
        assert cursor.row == 7
        ctx, _, _ = _run("plan", active="Burn")
        assert ctx.active_plan == "Tron"

    def test_bare_plan_without_plans_fails(self) -> None:
        ctx, _, _ = _run("plan", text="4 Opt\n")
        assert ctx.error
        assert ":plan <matchup>" in ctx.message

    def test_bang_deactivates(self) -> None:
        ctx, _, _ = _run("plan!", active="Tron")
        assert ctx.active_plan is None
        assert ctx.active_plan_set
        assert not ctx.error

    def test_unbalanced_mark_in_message(self) -> None:
        ctx, _, _ = _run("plan burn")
        assert ctx.message == "vs Burn  -1 +0 !"


class TestPlans:
    def test_lists_plans(self) -> None:
        ctx, _, _ = _run("plans", active="Tron")
        assert not ctx.error
        assert ctx.message == "*vs Tron -2 +1 ! · vs Burn -1 +0 !"

    def test_no_plans(self) -> None:
        ctx, _, _ = _run("plans", text="4 Opt\n")
        assert ctx.message == "No sideboard plans"


class TestExportGuide:
    def test_export_guide_to_file(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        out = tmp_path / "guide.md"
        ctx, _, _ = _run(f"export guide {out}")
        assert not ctx.error
        text = out.read_text()
        assert "## vs Tron" in text and "## vs Burn" in text

    def test_export_guide_preview(self) -> None:
        ctx, _, _ = _run("export guide")
        assert not ctx.error
        assert "guide" in ctx.message
