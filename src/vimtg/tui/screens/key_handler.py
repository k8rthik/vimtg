"""Key action handlers for MainScreen — separated to keep screen under 200 lines.

Each handler mutates EditorState and returns it. The MainScreen calls these
and then syncs the updated state to widgets.
"""

from __future__ import annotations

from dataclasses import dataclass

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import CommandRegistry, EditorContext, parse_command
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.motions import MOTION_REGISTRY, motion_goto_line, motion_last_line
from vimtg.editor.operators import (
    decrement_quantity,
    execute_operator,
    increment_quantity,
    put_lines,
)
from vimtg.editor.registers import RegisterStore
from vimtg.services.history_service import HistoryService


@dataclass
class EditorState:
    """Mutable editor state bundle passed through handlers."""

    buffer: Buffer
    cursor: Cursor
    mode_mgr: ModeManager
    registers: RegisterStore
    history: HistoryService
    modified: bool
    resolved_cards: dict[str, Card]
    search_query: str = ""


@dataclass(frozen=True)
class HandlerResult:
    """Side effects requested by a handler that require widget access."""

    enter_insert: bool = False
    enter_command: bool = False
    exit_to_normal: bool = False
    enter_visual: Mode | None = None
    command_message: str = ""
    quit_requested: bool = False
    search_query: str | None = None
    insert_card: Card | None = None
    insert_confirm: bool = False


def handle_motion(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process motion actions (j, k, G, gg, etc.)."""
    motion_fn = MOTION_REGISTRY.get(action.action)
    if motion_fn:
        count = action.count if action.count > 0 else 1
        state.cursor = motion_fn(state.cursor, state.buffer, count)
    elif action.action == "G":
        if action.count == 0:
            state.cursor = motion_last_line(state.cursor, state.buffer)
        else:
            state.cursor = motion_goto_line(state.cursor, state.buffer, action.count)
    return HandlerResult()


def handle_operator(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process operator actions (dd, yy, cc, dj, etc.)."""
    result = execute_operator(
        action.action,
        action.motion,
        state.cursor,
        state.buffer,
        action.count or 1,
        state.registers,
        action.register,
    )
    state.buffer = result.buffer
    state.cursor = result.cursor
    state.registers = result.registers
    state.modified = True
    state.history.record(state.buffer, f"{action.action} operation")
    if result.enter_insert:
        return HandlerResult(enter_insert=True)
    return HandlerResult()


def handle_mode_switch(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process mode switch actions (i, :, v, escape)."""
    key = action.action
    if key == "escape":
        return HandlerResult(exit_to_normal=True)
    if key in ("i", "a", "o", "O", "A"):
        _apply_insert_variant(state, key)
        return HandlerResult(enter_insert=True)
    if key == ":":
        return HandlerResult(enter_command=True)
    if key in ("v", "V"):
        target = Mode.VISUAL if key == "v" else Mode.VISUAL_LINE
        return HandlerResult(enter_visual=target)
    return HandlerResult()


def handle_command(
    state: EditorState,
    action: ParsedAction,
    registry: CommandRegistry,
    file_path: object,
) -> HandlerResult:
    """Process ex command submission."""
    if not action.text:
        return HandlerResult()
    try:
        cmd = parse_command(action.text, state.cursor.row, state.buffer.line_count())
        ctx = EditorContext(file_path=file_path, modified=state.modified)
        state.buffer, state.cursor = registry.execute(cmd, state.buffer, state.cursor, ctx)
        if ctx.modified:
            state.modified = True
            state.history.record(state.buffer, f":{action.text}")
        return HandlerResult(
            command_message=ctx.message,
            quit_requested=ctx.quit_requested,
        )
    except Exception as exc:
        return HandlerResult(command_message=str(exc))


def handle_normal_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process normal-mode special keys (u, p, +, -, x)."""
    key = action.action
    if key == "u":
        restored = state.history.undo()
        if restored:
            state.buffer = restored
            state.modified = True
    elif key == "ctrl_r":
        restored = state.history.redo()
        if restored:
            state.buffer = restored
            state.modified = True
    elif key == "p":
        state.buffer, state.cursor = put_lines(
            state.buffer, state.cursor, state.registers, action.register,
        )
        state.modified = True
        state.history.record(state.buffer, "put")
    elif key == "P":
        state.buffer, state.cursor = put_lines(
            state.buffer, state.cursor, state.registers, action.register, above=True,
        )
        state.modified = True
        state.history.record(state.buffer, "put above")
    elif key == "+":
        state.buffer = increment_quantity(state.buffer, state.cursor)
        state.modified = True
        state.history.record(state.buffer, "increment")
    elif key == "-":
        state.buffer, state.cursor = decrement_quantity(state.buffer, state.cursor)
        state.modified = True
        state.history.record(state.buffer, "decrement")
    elif key == "x":
        _delete_card_at_cursor(state)
    elif key in ("?", "question_mark"):
        from vimtg.editor.help_text import get_help
        return HandlerResult(command_message=get_help())
    return HandlerResult()


def handle_insert_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process insert-mode special keys (typing, tab, enter)."""
    key = action.action
    if key in ("char", "backspace"):
        state.search_query = action.text or ""
        return HandlerResult(search_query=state.search_query)
    if key in ("ctrl_n", "tab"):
        return HandlerResult(search_query="__next__")
    if key in ("ctrl_p", "shift_tab"):
        return HandlerResult(search_query="__prev__")
    if key == "enter":
        return HandlerResult(insert_confirm=True)
    return HandlerResult()


def count_cards(buffer: Buffer) -> int:
    """Count total cards in the buffer."""
    try:
        deck = parse_deck_text(buffer.to_text())
        return sum(e.quantity for e in deck.entries)
    except Exception:
        return 0


def resolve_cards(buffer: Buffer, card_repo: object) -> dict[str, Card]:
    """Resolve card names in the buffer to Card objects."""
    try:
        deck = parse_deck_text(buffer.to_text())
        names = list(deck.unique_card_names())
        return card_repo.get_by_names(names)  # type: ignore[union-attr]
    except Exception:
        return {}


def _apply_insert_variant(state: EditorState, variant: str) -> None:
    """Apply buffer changes for insert mode variants (o, O)."""
    if variant == "o":
        state.buffer = state.buffer.insert_line(state.cursor.row + 1, "")
        state.cursor = state.cursor.move_to(state.cursor.row + 1, 0)
    elif variant == "O":
        state.buffer = state.buffer.insert_line(state.cursor.row, "")


def _delete_card_at_cursor(state: EditorState) -> None:
    """Delete the card line at cursor, storing in register."""
    if not state.buffer.is_card_line(state.cursor.row):
        return
    new_buf, deleted = state.buffer.delete_lines(state.cursor.row, state.cursor.row)
    state.registers = state.registers.set_unnamed(deleted, is_delete=True)
    state.buffer = new_buf
    state.cursor = state.cursor.clamp(max(0, state.buffer.line_count() - 1))
    state.modified = True
    state.history.record(state.buffer, "delete card")
