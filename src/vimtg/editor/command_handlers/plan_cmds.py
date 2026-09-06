""":plan / :plans — activate, create, cycle, and list sideboard plans.

TUI-agnostic: zero Textual imports. The active plan is editor state;
handlers report the new value through EditorContext.active_plan.
"""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.plan_ops import (
    PlanBlock,
    ensure_plan,
    find_block,
    plan_blocks,
    plan_label,
)

NO_PLANS = "No sideboard plans — :plan <matchup> to start one"


def _next_block(blocks: tuple[PlanBlock, ...], active: str | None) -> PlanBlock:
    """The block after the active one, wrapping; the first when none is active."""
    if active is None:
        return blocks[0]
    names = [b.name.lower() for b in blocks]
    try:
        idx = names.index(active.lower())
    except ValueError:
        return blocks[0]
    return blocks[(idx + 1) % len(blocks)]


def cmd_plan(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:plan <matchup> — activate (creating if missing); :plan — next
    plan; :plan! — deactivate."""
    if cmd.bang:
        ctx.active_plan = None
        ctx.active_plan_set = True
        ctx.message = "Sideboard plan off"
        return buf, cursor

    name = cmd.args.strip()
    created = False
    if name:
        buf, _, created = ensure_plan(buf, name)
        block = find_block(buf, name)
        if block is None:  # cannot happen after ensure_plan; keeps mypy honest
            ctx.fail(f"Could not create plan {name}")
            return buf, cursor
        if created:
            ctx.modified = True
    else:
        blocks = plan_blocks(buf)
        if not blocks:
            ctx.fail(NO_PLANS)
            return buf, cursor
        block = _next_block(blocks, ctx.active_plan)

    ctx.active_plan = block.name
    ctx.active_plan_set = True
    prefix = "New plan: " if created else ""
    ctx.message = prefix + plan_label(buf, block)
    return buf, cursor.move_to(block.header_row, 0)


def cmd_plans(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:plans — list every plan with its -x +y totals; * marks the active one."""
    blocks = plan_blocks(buf)
    if not blocks:
        ctx.message = "No sideboard plans"
        return buf, cursor
    active = (ctx.active_plan or "").lower()
    ctx.message = " · ".join(
        ("*" if b.name.lower() == active else "") + plan_label(buf, b, sep=" ")
        for b in blocks
    )
    return buf, cursor


def register_plan_commands(registry: CommandRegistry) -> None:
    registry.register("plan", cmd_plan)
    registry.register("plans", cmd_plans)
