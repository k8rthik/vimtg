"""Key action handlers for MainScreen — separated to keep screen under 200 lines.

Each handler mutates EditorState and returns it. The MainScreen calls these
and then syncs the updated state to widgets.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vimtg.config.settings import Settings
from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_completer import CommandCompleter, CompletionState
from vimtg.editor.commands import CommandRegistry, EditorContext, parse_command
from vimtg.editor.cursor import Cursor
from vimtg.editor.dot_repeat import DotRepeat, RepeatableAction
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.macros import MacroRecorder
from vimtg.editor.marks import MarkStore
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

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository


class InsertSubmode(Enum):
    CARD_SEARCH = "card_search"
    LINE_EDIT = "line_edit"
    TAG_INPUT = "tag_input"


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
    settings: Settings = field(default_factory=Settings)
    cmd_completer: CommandCompleter | None = None
    cmd_completion: CompletionState | None = None
    card_repo: CardRepository | None = None
    macros: MacroRecorder = field(default_factory=MacroRecorder)
    dot_repeat: DotRepeat = field(default_factory=DotRepeat)
    marks: MarkStore = field(default_factory=MarkStore)
    visual_anchor: int | None = None
    insert_submode: InsertSubmode = InsertSubmode.CARD_SEARCH
    line_edit_original: str | None = None
    line_edit_row: int | None = None
    line_edit_prefix: str = ""
    tag_input_action: str = ""
    tag_filter: Any = None


@dataclass(frozen=True)
class HandlerResult:
    """Side effects requested by a handler that require widget access."""

    enter_insert: bool = False
    enter_command: bool = False
    enter_search: bool = False
    exit_to_normal: bool = False
    enter_visual: Mode | None = None
    command_message: str = ""
    quit_requested: bool = False
    greeter_requested: bool = False
    help_requested: bool = False
    search_query: str | None = None
    insert_card: Card | None = None
    insert_confirm: bool = False
    file_path: Path | None = None
    open_config_screen: bool = False
    open_history_screen: bool = False
    vcs_commit_description: str = ""
    command_ghost: str = ""
    command_accept: str = ""
    enter_line_edit: bool = False
    enter_tag_input: bool = False
    tag_prompt: str = ""


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
    """Process operator actions (dd, yy, cc, dj, etc.).

    In visual mode, operates on the selected range (anchor → cursor).
    """
    # Visual mode: override to line-range operation
    if state.visual_anchor is not None:
        start = min(state.visual_anchor, state.cursor.row)
        end = max(state.visual_anchor, state.cursor.row)
        count = end - start + 1
        op = action.action[0] if len(action.action) > 1 else action.action
        result = execute_operator(
            op + op, None, state.cursor.move_to(start, 0),
            state.buffer, count, state.registers, action.register,
        )
        state.visual_anchor = None
    else:
        result = execute_operator(
            action.action, action.motion, state.cursor, state.buffer,
            action.count or 1, state.registers, action.register,
        )
    state.buffer = result.buffer
    state.cursor = result.cursor
    state.registers = result.registers
    state.modified = True
    state.history.record(state.buffer, f"{action.action} operation")
    state.dot_repeat.record(RepeatableAction(
        "operator", operator=action.action,
        motion=action.motion, count=action.count or 1,
        register=action.register,
    ))
    if result.enter_insert:
        return HandlerResult(enter_insert=True)
    # Exit visual mode after operation
    if state.mode_mgr.current in (Mode.VISUAL, Mode.VISUAL_LINE):
        return HandlerResult(exit_to_normal=True)
    return HandlerResult()


def handle_mode_switch(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process mode switch actions (i, o, :, v, escape)."""
    key = action.action
    if key == "escape":
        state.visual_anchor = None
        return HandlerResult(exit_to_normal=True)
    if key == "i":
        line_text = state.buffer.get_line(state.cursor.row).text
        state.insert_submode = InsertSubmode.LINE_EDIT
        state.line_edit_original = line_text
        state.line_edit_row = state.cursor.row
        # Protect the // comment marker — user edits only the content after it
        if line_text.lstrip().startswith("//"):
            idx = line_text.index("//") + 2
            # Include trailing space after // if present
            if idx < len(line_text) and line_text[idx] == " ":
                idx += 1
            state.line_edit_prefix = line_text[:idx]
        else:
            state.line_edit_prefix = ""
        return HandlerResult(enter_line_edit=True)
    if key in ("o", "O"):
        _apply_insert_variant(state, key)
        return HandlerResult(enter_insert=True)
    if key == ":":
        return HandlerResult(enter_command=True)
    if key == "/":
        return HandlerResult(enter_search=True)
    if key in ("v", "V"):
        target = Mode.VISUAL if key == "v" else Mode.VISUAL_LINE
        state.visual_anchor = state.cursor.row
        return HandlerResult(enter_visual=target)
    return HandlerResult()


def handle_command(
    state: EditorState,
    action: ParsedAction,
    registry: CommandRegistry,
    file_path: Path | None,
    save_fn: Callable[[Path, str], None] | None = None,
) -> HandlerResult:
    """Process ex command or search submission."""
    if not action.text:
        return HandlerResult()

    # If in SEARCH mode, convert to :find command
    raw_text = action.text
    if state.mode_mgr.current == Mode.SEARCH:
        raw_text = f"find {action.text}"

    try:
        cmd = parse_command(raw_text, state.cursor.row, state.buffer.line_count())
        ctx = EditorContext(
            file_path=file_path, modified=state.modified,
            save_fn=save_fn, settings=state.settings,
            resolved_cards=state.resolved_cards,
            history=state.history,
            card_repo=state.card_repo,
        )
        state.buffer, state.cursor = registry.execute(cmd, state.buffer, state.cursor, ctx)
        # Sync modified flag unconditionally (allows :w to clear it)
        if ctx.modified and ctx.modified != state.modified:
            state.history.record(state.buffer, f":{action.text}")
        state.modified = ctx.modified
        if ctx.settings_changed and ctx.settings is not None:
            state.settings = ctx.settings
        return HandlerResult(
            command_message=ctx.message,
            quit_requested=ctx.quit_requested,
            greeter_requested=ctx.greeter_requested,
            file_path=ctx.file_path,
            open_config_screen=ctx.open_config_screen,
            open_history_screen=ctx.open_history_screen,
            vcs_commit_description=ctx.vcs_commit_description,
        )
    except Exception as exc:
        return HandlerResult(command_message=str(exc))


def handle_normal_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process normal-mode special keys (u, p, +, -, x, ., q, @, m, ')."""
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
            state.buffer, state.cursor, state.registers, action.register,
            above=True,
        )
        state.modified = True
        state.history.record(state.buffer, "put above")
    elif key == "+":
        state.buffer = increment_quantity(state.buffer, state.cursor)
        state.modified = True
        state.history.record(state.buffer, "increment")
        state.dot_repeat.record(RepeatableAction("quantity", operator="+"))
    elif key == "-":
        state.buffer, state.cursor = decrement_quantity(
            state.buffer, state.cursor,
        )
        state.modified = True
        state.history.record(state.buffer, "decrement")
        state.dot_repeat.record(RepeatableAction("quantity", operator="-"))
    elif key == "x":
        _delete_card_at_cursor(state)
        state.dot_repeat.record(RepeatableAction("operator", operator="x"))
    elif key == "?":
        return HandlerResult(help_requested=True)
    elif key == ".":
        _replay_dot(state)
    elif key == "q":
        _toggle_macro_recording(state)
    elif key == "@":
        reg = action.register or "@"
        _play_macro(state, reg)
    elif key.startswith("m") and len(key) == 2:
        mark_name = key[1]
        state.marks = state.marks.set(mark_name, state.cursor.row)
        return HandlerResult(
            command_message=f"Mark '{mark_name}' set",
        )
    elif key.startswith("'") and len(key) == 2:
        mark_name = key[1]
        mark = state.marks.get(mark_name)
        if mark is not None:
            row = min(mark.row, state.buffer.line_count() - 1)
            state.cursor = state.cursor.move_to(row, 0)
        else:
            return HandlerResult(
                command_message=f"Mark '{mark_name}' not set",
            )
    elif key.startswith("t") and len(key) == 2:
        return _handle_tag_action(state, key[1])
    return HandlerResult()


def _handle_tag_action(state: EditorState, sub_key: str) -> HandlerResult:
    """Dispatch tag sub-key: a(dd), r(emove), t(oggle), f(ilter), l(ist), c(lear), n(ext), p(rev)."""
    _TAG_PROMPTS = {
        "a": "tag add: ",
        "r": "tag remove: ",
        "t": "tag toggle: ",
        "f": "filter: ",
    }
    if sub_key in _TAG_PROMPTS:
        state.tag_input_action = sub_key
        state.insert_submode = InsertSubmode.TAG_INPUT
        return HandlerResult(
            enter_tag_input=True,
            tag_prompt=_TAG_PROMPTS[sub_key],
        )
    if sub_key == "l":
        # List all tags inline
        tag_counts: dict[str, int] = {}
        for i in range(state.buffer.line_count()):
            for tag in state.buffer.tags_at(i):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        if tag_counts:
            parts = [f"#{t}({c})" for t, c in sorted(tag_counts.items())]
            return HandlerResult(command_message=f"Tags: {' '.join(parts)}")
        return HandlerResult(command_message="No tags in deck")
    if sub_key == "c":
        # Clear all tags from cursor card
        if state.buffer.is_card_line(state.cursor.row) and state.buffer.tags_at(state.cursor.row):
            state.buffer = state.buffer.set_tags(state.cursor.row, frozenset())
            state.modified = True
            state.history.record(state.buffer, "clear tags")
            return HandlerResult(command_message="Tags cleared")
        return HandlerResult(command_message="No tags to clear")
    if sub_key == "n":
        return _jump_to_tagged(state, forward=True)
    if sub_key == "p":
        return _jump_to_tagged(state, forward=False)
    return HandlerResult()


def _jump_to_tagged(state: EditorState, forward: bool) -> HandlerResult:
    """Jump to next/prev card sharing a tag with the current card."""
    current_tags = state.buffer.tags_at(state.cursor.row)
    if not current_tags:
        return HandlerResult(command_message="No tags on current card")

    line_count = state.buffer.line_count()
    if forward:
        rng = range(state.cursor.row + 1, line_count)
    else:
        rng = range(state.cursor.row - 1, -1, -1)

    for i in rng:
        if state.buffer.is_card_line(i) and (state.buffer.tags_at(i) & current_tags):
            state.cursor = state.cursor.move_to(i, 0)
            return HandlerResult()
    return HandlerResult(command_message="No more tagged matches")


def handle_tag_input_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process tag-input mode keys (typing tag name, enter to confirm)."""
    key = action.action
    text = action.text or ""

    if key in ("char", "backspace", "delete", "cursor_move"):
        return HandlerResult()

    if key == "enter" and text.strip():
        result = _apply_tag_input(state, text.strip())
        state.tag_input_action = ""
        state.insert_submode = InsertSubmode.CARD_SEARCH
        return HandlerResult(
            exit_to_normal=True,
            command_message=result,
        )

    if key == "enter":
        state.tag_input_action = ""
        state.insert_submode = InsertSubmode.CARD_SEARCH
        return HandlerResult(exit_to_normal=True)

    return HandlerResult()


def _apply_tag_input(state: EditorState, text: str) -> str:
    """Apply the tag action from tag-input mode."""
    action = state.tag_input_action
    tag = text.lstrip("#").lower()

    if not tag:
        return ""

    row = state.cursor.row

    # Handle visual selection range
    if state.visual_anchor is not None:
        start = min(state.visual_anchor, row)
        end = max(state.visual_anchor, row)
        state.visual_anchor = None
    else:
        start = end = row

    if action == "a":
        count = 0
        for line in range(start, end + 1):
            if state.buffer.is_card_line(line):
                state.buffer = state.buffer.add_tag(line, tag)
                count += 1
        if count:
            state.modified = True
            state.history.record(state.buffer, f"tag add #{tag}")
        return f"Tagged {count} card(s) with #{tag}" if count else "No card lines"

    if action == "r":
        count = 0
        for line in range(start, end + 1):
            if state.buffer.is_card_line(line) and tag in state.buffer.tags_at(line):
                state.buffer = state.buffer.remove_tag(line, tag)
                count += 1
        if count:
            state.modified = True
            state.history.record(state.buffer, f"tag remove #{tag}")
        return f"Removed #{tag} from {count} card(s)" if count else f"No cards with #{tag}"

    if action == "t":
        added = 0
        removed = 0
        for line in range(start, end + 1):
            if state.buffer.is_card_line(line):
                if tag in state.buffer.tags_at(line):
                    state.buffer = state.buffer.remove_tag(line, tag)
                    removed += 1
                else:
                    state.buffer = state.buffer.add_tag(line, tag)
                    added += 1
        if added or removed:
            state.modified = True
            state.history.record(state.buffer, f"tag toggle #{tag}")
        return f"#{tag}: +{added} -{removed}"

    if action == "f":
        from vimtg.domain.tags import matches_filter, parse_tag_filter
        state.tag_filter = parse_tag_filter(text)
        visible = sum(
            1 for i in range(state.buffer.line_count())
            if state.buffer.is_card_line(i)
            and matches_filter(state.buffer.tags_at(i), state.tag_filter)
        )
        total = sum(1 for i in range(state.buffer.line_count()) if state.buffer.is_card_line(i))
        return f"Filter active: {visible}/{total} cards visible"

    return ""


def _replay_dot(state: EditorState) -> None:
    """Replay the last repeatable action."""
    last = state.dot_repeat.last_action
    if last is None:
        return
    if last.action_type == "operator" and last.operator:
        if last.operator == "x":
            _delete_card_at_cursor(state)
        else:
            result = execute_operator(
                last.operator, last.motion, state.cursor, state.buffer,
                last.count, state.registers, last.register,
            )
            state.buffer = result.buffer
            state.cursor = result.cursor
            state.registers = result.registers
            state.modified = True
            state.history.record(state.buffer, "dot repeat")
    elif last.action_type == "quantity":
        if last.operator == "+":
            state.buffer = increment_quantity(state.buffer, state.cursor)
        elif last.operator == "-":
            state.buffer, state.cursor = decrement_quantity(
                state.buffer, state.cursor,
            )
        state.modified = True
        state.history.record(state.buffer, "dot repeat")


def _toggle_macro_recording(state: EditorState) -> None:
    """Start or stop macro recording."""
    if state.macros.is_recording:
        state.macros.stop_recording()
    else:
        # Next key press after 'q' should be the register name
        # For simplicity, use the register from the action if set
        # The keymap sends 'q' as a special key; we need a follow-up
        # We'll use a simple convention: q is handled as a toggle
        # The register selection happens via "@" register prefix
        state.macros.start_recording("q")


def _play_macro(state: EditorState, register: str) -> None:
    """Play a macro from the given register."""
    keys = state.macros.play(register)
    if keys is None:
        return
    for key in keys:
        if key in MOTION_REGISTRY:
            motion_fn = MOTION_REGISTRY[key]
            state.cursor = motion_fn(state.cursor, state.buffer, 1)
        elif key in ("+", "-", "x"):
            handle_normal_special(
                state, ParsedAction("special", key),
            )


def handle_insert_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process insert-mode special keys (typing, tab, enter)."""
    key = action.action
    if key in ("char", "backspace", "delete"):
        state.search_query = action.text or ""
        return HandlerResult(search_query=state.search_query)
    if key == "cursor_move":
        return HandlerResult()
    if key in ("ctrl_j", "ctrl_n", "tab"):
        return HandlerResult(search_query="__next__")
    if key in ("ctrl_k", "ctrl_p", "shift_tab"):
        return HandlerResult(search_query="__prev__")
    if key == "enter":
        return HandlerResult(insert_confirm=True)
    return HandlerResult()


def handle_line_edit_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process line-edit insert-mode keys (typing updates buffer line in real-time)."""
    key = action.action
    text = action.text or ""
    row = state.line_edit_row
    prefix = state.line_edit_prefix
    if key in ("char", "backspace", "delete"):
        if row is not None and row < state.buffer.line_count():
            state.buffer = state.buffer.set_line(row, prefix + text)
        return HandlerResult()
    if key == "cursor_move":
        return HandlerResult()
    if key == "enter":
        # Confirm: record history, clear original (signals "confirmed, don't restore")
        if row is not None:
            state.history.record(state.buffer, "edit line")
            state.modified = True
        state.line_edit_original = None
        state.line_edit_row = None
        state.insert_submode = InsertSubmode.CARD_SEARCH
        return HandlerResult(exit_to_normal=True)
    return HandlerResult()


def handle_command_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process command-mode special keys for fuzzy completion."""
    key = action.action
    text = action.text or ""
    completer = state.cmd_completer

    if completer is None:
        return HandlerResult()

    if key in ("char", "backspace", "delete"):
        state.cmd_completion = completer.complete(text)
        ghost = completer.current_ghost(state.cmd_completion)
        return HandlerResult(command_ghost=ghost)

    if key == "cursor_move":
        return HandlerResult()

    if key == "tab" and state.cmd_completion and state.cmd_completion.matches:
        accepted = completer.accept(state.cmd_completion)
        state.cmd_completion = completer.cycle_next(state.cmd_completion)
        ghost = completer.current_ghost(state.cmd_completion)
        return HandlerResult(command_accept=accepted, command_ghost=ghost)

    if key == "shift_tab" and state.cmd_completion and state.cmd_completion.matches:
        state.cmd_completion = completer.cycle_prev(state.cmd_completion)
        accepted = completer.accept(state.cmd_completion)
        ghost = completer.current_ghost(state.cmd_completion)
        return HandlerResult(command_accept=accepted, command_ghost=ghost)

    return HandlerResult()


def count_cards(buffer: Buffer) -> int:
    """Count total cards in the buffer."""
    try:
        deck = parse_deck_text(buffer.to_text())
        return sum(e.quantity for e in deck.entries)
    except Exception:
        return 0


def resolve_cards(buffer: Buffer, card_repo: CardRepository) -> dict[str, Card]:
    """Resolve card names in the buffer to Card objects."""
    try:
        deck = parse_deck_text(buffer.to_text())
        names = list(deck.unique_card_names())
        return card_repo.get_by_names(names)
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
