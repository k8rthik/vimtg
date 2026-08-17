"""Editor session: EditorState and the key-action handlers.

This is the editor engine — pure state + handlers with zero Textual
imports. The TUI layer (MainScreen) feeds it ParsedActions and applies
the returned HandlerResult side effects to widgets.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vimtg.config.category_history import load_category_history, record_category
from vimtg.config.settings import Settings
from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.domain.categories import (
    CATEGORY_NAME_RE,
    complete_category,
    completion_candidates,
)
from vimtg.domain.deck_lines import split_metadata_prefix
from vimtg.domain.formats import get_format_rules, known_formats
from vimtg.domain.tags import TagFilter, format_tag_summary
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.category_ops import (
    clear_category_in_range,
    set_category_in_range,
)
from vimtg.editor.command_completer import CommandCompleter, CompletionState
from vimtg.editor.commands import CommandRegistry, EditorContext, parse_command
from vimtg.editor.cursor import Cursor
from vimtg.editor.dot_repeat import DotRepeat, RepeatableAction
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.layout import (
    LAYOUT_CATEGORY,
    LAYOUT_TYPE,
    detect_layout,
    regroup_buffer,
)
from vimtg.editor.macros import MacroRecorder
from vimtg.editor.marks import MarkStore
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.motions import MOTION_REGISTRY, motion_goto_line
from vimtg.editor.operators import (
    ZONE_LABELS,
    decrement_quantity,
    execute_operator,
    increment_quantity,
    move_to_zone,
    put_lines,
    resolve_line_range,
)
from vimtg.editor.registers import RegisterStore
from vimtg.editor.sort_keys import SORT_FIELDS
from vimtg.editor.splits import EdhrecOpen, SplitOpen
from vimtg.editor.tag_ops import (
    add_tags_in_range,
    remove_tags_in_range,
    toggle_tag_in_range,
)
from vimtg.services.history_service import HistoryService

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository


class InsertSubmode(Enum):
    CARD_SEARCH = "card_search"
    LINE_EDIT = "line_edit"
    TAG_INPUT = "tag_input"
    COMMENT_INPUT = "comment_input"


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
    tag_filter: TagFilter | None = None
    # Ordered completion pool for category input, built on entry
    category_candidates: tuple[str, ...] = ()
    remapper: Any = None  # KeyRemapper, passed through to :map/:unmap


@dataclass(frozen=True)
class HandlerResult:
    """Side effects requested by a handler that require widget access."""

    enter_insert: bool = False
    enter_command: bool = False
    enter_search: bool = False
    exit_to_normal: bool = False
    enter_visual: Mode | None = None
    command_message: str = ""
    error: bool = False  # command_message is an error, not status
    quit_requested: bool = False
    greeter_requested: bool = False
    help_requested: bool = False
    search_query: str | None = None
    insert_confirm: bool = False
    file_path: Path | None = None
    file_saved: bool = False
    open_config_screen: bool = False
    open_history_screen: bool = False
    open_help_screen: bool = False
    help_topic: str | None = None
    vcs_commit_description: str = ""
    vcs_checkpoint_name: str = ""
    vcs_list_branches: bool = False
    vcs_create_branch: str = ""
    vcs_switch_branch: str = ""
    vcs_merge_target: str = ""
    vcs_rebase_target: str = ""
    command_ghost: str = ""
    command_accept: str = ""
    enter_line_edit: bool = False
    enter_tag_input: bool = False
    tag_prompt: str = ""
    enter_comment_input: bool = False
    comment_prefill: str = ""
    replay_keys: tuple[str, ...] = ()  # macro playback via the key pipeline
    # Companion pane (splits / EDHREC)
    split_open: SplitOpen | None = None
    split_close: bool = False
    edhrec_open: EdhrecOpen | None = None
    focus_next_pane: bool = False
    command_prefill: str = ""  # pre-typed text when entering command mode
    run_ex_command: str = ""  # execute an ex command as if typed


def handle_motion(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process motion actions (j, k, G, gg, etc.).

    A counted ``G`` (e.g. ``5G``) jumps to that line number; bare ``G`` falls
    through to the registry handler (last line). The registry's ``G`` ignores
    its count, so the counted case must be intercepted here.
    """
    count = action.count if action.count > 0 else 1
    if action.action == "G" and count > 1:
        state.cursor = motion_goto_line(state.cursor, state.buffer, count)
        return HandlerResult()
    motion_fn = MOTION_REGISTRY.get(action.action)
    if motion_fn:
        state.cursor = motion_fn(state.cursor, state.buffer, count)
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
        affected = (start, end)
        state.visual_anchor = None
    else:
        affected = resolve_line_range(
            action.action, action.motion, state.cursor, state.buffer,
            action.count or 1,
        )
        result = execute_operator(
            action.action, action.motion, state.cursor, state.buffer,
            action.count or 1, state.registers, action.register,
        )
    if result.buffer.line_count() < state.buffer.line_count():
        state.marks = state.marks.update_for_delete(*affected)
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
        # On metadata lines, lock the whole '// Key: ' prefix so the
        # user edits only the value
        meta = split_metadata_prefix(line_text)
        if meta is not None:
            state.line_edit_prefix = meta[0]
        # Protect the // comment marker — user edits only the content after it
        elif line_text.lstrip().startswith("//"):
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
            remapper=state.remapper,
        )
        state.buffer, state.cursor = registry.execute(cmd, state.buffer, state.cursor, ctx)
        # Sync modified flag unconditionally (allows :w to clear it)
        if ctx.modified and ctx.modified != state.modified:
            state.history.record(state.buffer, f":{action.text}")
        state.modified = ctx.modified
        if ctx.settings_changed and ctx.settings is not None:
            state.settings = ctx.settings
        if ctx.resolved_cards is not None and ctx.resolved_cards is not state.resolved_cards:
            state.resolved_cards = dict(ctx.resolved_cards)
        if ctx.tag_filter_set:
            state.tag_filter = ctx.tag_filter
        return HandlerResult(
            command_message=ctx.message,
            error=ctx.error,
            quit_requested=ctx.quit_requested,
            greeter_requested=ctx.greeter_requested,
            file_path=ctx.file_path,
            file_saved=ctx.file_saved,
            open_config_screen=ctx.open_config_screen,
            open_history_screen=ctx.open_history_screen,
            open_help_screen=ctx.open_help_screen,
            help_topic=ctx.help_topic,
            vcs_commit_description=ctx.vcs_commit_description,
            vcs_checkpoint_name=ctx.vcs_checkpoint_name,
            vcs_list_branches=ctx.vcs_list_branches,
            vcs_create_branch=ctx.vcs_create_branch,
            vcs_switch_branch=ctx.vcs_switch_branch,
            vcs_merge_target=ctx.vcs_merge_target,
            vcs_rebase_target=ctx.vcs_rebase_target,
            split_open=ctx.split_open,
            split_close=ctx.split_close,
            edhrec_open=ctx.edhrec_open,
        )
    except Exception as exc:
        return HandlerResult(command_message=f"E: {exc}", error=True)


def handle_normal_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process normal-mode special keys (u, p, +, -, x, ., q, @, m, ').

    A count prefix repeats or scales the action vim-style: 10+ adds 10
    to the quantity, 2x deletes two cards, 3p pastes three copies.
    """
    key = action.action
    count = action.count if action.count > 0 else 1
    if key == "u":
        for _ in range(count):
            restored = state.history.undo()
            if restored is None:
                break
            state.buffer = restored
            state.modified = True
    elif key == "ctrl_r":
        for _ in range(count):
            restored = state.history.redo()
            if restored is None:
                break
            state.buffer = restored
            state.modified = True
    elif key in ("p", "P"):
        before = state.buffer.line_count()
        # First row the paste block occupies — after the loop the cursor
        # sits on the LAST paste, which would leave marks below the
        # original line stranded inside the block on counted puts.
        first_insert_row = state.cursor.row + (0 if key == "P" else 1)
        for _ in range(count):
            state.buffer, state.cursor = put_lines(
                state.buffer, state.cursor, state.registers, action.register,
                above=(key == "P"),
            )
        inserted = state.buffer.line_count() - before
        if inserted > 0:
            state.marks = state.marks.update_for_insert(first_insert_row, inserted)
            state.modified = True
            state.history.record(
                state.buffer, "put" if key == "p" else "put above"
            )
    elif key == "+":
        state.buffer = increment_quantity(state.buffer, state.cursor, count)
        state.modified = True
        state.history.record(state.buffer, "increment")
        state.dot_repeat.record(
            RepeatableAction("quantity", operator="+", count=count)
        )
    elif key == "-":
        state.buffer, state.cursor = decrement_quantity(
            state.buffer, state.cursor, count,
        )
        state.modified = True
        state.history.record(state.buffer, "decrement")
        state.dot_repeat.record(
            RepeatableAction("quantity", operator="-", count=count)
        )
    elif key == "x":
        for _ in range(count):
            _delete_card_at_cursor(state)
        state.dot_repeat.record(
            RepeatableAction("operator", operator="x", count=count)
        )
    elif key == "?":
        return HandlerResult(help_requested=True)
    elif key == ".":
        # A count given to '.' replaces the recorded one (vim semantics);
        # count=1 is indistinguishable from "no count", so only >1 overrides.
        _replay_dot(state, count if count > 1 else None)
    elif key == "q_stop":
        register = state.macros.recording_register or "?"
        macro = state.macros.stop_recording()
        count = len(macro.keys) if macro else 0
        return HandlerResult(
            command_message=f"Recorded @{register} ({count} keys)"
        )
    elif key.startswith("q") and len(key) == 2:
        state.macros.start_recording(key[1])
        return HandlerResult(command_message=f"recording @{key[1]}")
    elif key.startswith("@") and len(key) == 2:
        keys = state.macros.play(key[1])
        if keys is None:
            return HandlerResult(
                command_message=f"Nothing recorded in @{key[1]}"
            )
        return HandlerResult(replay_keys=keys * count)
    elif key in ("ms", "mm", "md", "mc", "mp"):
        # Zone moves shadow marks s/m/d/c/p; action.count is read raw
        # because 0 means "no count given" — move every copy (see keymap).
        return _move_card_to_zone(state, key, action.count)
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
    elif key in ("Sv", "Sh", "Ss", "Sc", "Sr"):
        return _handle_split_key(key)
    elif key in ("gc", "gC", "gl"):
        return _handle_category_action(state, key[1])
    elif key.startswith("t") and len(key) == 2:
        return _handle_tag_action(state, key[1])
    elif key == "A":
        return _handle_comment_action(state)
    return HandlerResult()


def _handle_split_key(key: str) -> HandlerResult:
    """Dispatch S sub-key: v/h open a split prompt, s switch, c close,
    r EDHREC recommendations."""
    if key == "Sv":
        return HandlerResult(enter_command=True, command_prefill="vsplit ")
    if key == "Sh":
        return HandlerResult(enter_command=True, command_prefill="split ")
    if key == "Ss":
        return HandlerResult(focus_next_pane=True)
    if key == "Sc":
        return HandlerResult(split_close=True)
    return HandlerResult(run_ex_command="edhrec")


def _handle_comment_action(state: EditorState) -> HandlerResult:
    """Enter comment-input mode for the card under the cursor (A key)."""
    if not state.buffer.is_card_line(state.cursor.row):
        return HandlerResult(command_message="Comments attach to card lines")
    state.visual_anchor = None
    state.insert_submode = InsertSubmode.COMMENT_INPUT
    return HandlerResult(
        enter_comment_input=True,
        comment_prefill=state.buffer.comment_at(state.cursor.row),
    )


def handle_comment_input_special(
    state: EditorState, action: ParsedAction
) -> HandlerResult:
    """Process comment-input keys. Only Enter mutates the buffer, so
    Escape cancels for free via the shared exit-to-normal path."""
    key = action.action
    if key == "enter":
        text = (action.text or "").strip()
        row = state.cursor.row
        old = state.buffer.comment_at(row)
        state.insert_submode = InsertSubmode.CARD_SEARCH
        message = ""
        if text != old:
            state.buffer = state.buffer.set_comment(row, text)
            state.modified = True
            state.history.record(state.buffer, "edit comment")
            message = "Comment removed" if not text else "Comment set"
        return HandlerResult(exit_to_normal=True, command_message=message)
    return HandlerResult()


def _handle_category_action(state: EditorState, sub_key: str) -> HandlerResult:
    """Dispatch g sub-key: c (set category), C (clear), l (toggle layout)."""
    if sub_key == "c":
        state.tag_input_action = "category"
        state.insert_submode = InsertSubmode.TAG_INPUT
        state.category_candidates = completion_candidates(
            state.buffer.category_counts(), load_category_history()
        )
        return HandlerResult(
            enter_tag_input=True,
            tag_prompt="category: ",
        )
    if sub_key == "C":
        row = state.cursor.row
        if state.visual_anchor is not None:
            start = min(state.visual_anchor, row)
            end = max(state.visual_anchor, row)
            state.visual_anchor = None
        else:
            start = end = row
        state.buffer, count = clear_category_in_range(state.buffer, start, end)
        if count:
            state.modified = True
            state.history.record(state.buffer, "clear category")
            return HandlerResult(
                exit_to_normal=True,
                command_message=f"Cleared category from {count} card(s)",
            )
        return HandlerResult(
            exit_to_normal=True, command_message="No category to clear"
        )
    if sub_key == "l":
        return _toggle_layout(state)
    return HandlerResult()


def _toggle_layout(state: EditorState) -> HandlerResult:
    """gl — regroup the buffer between type and category layouts."""
    mode = (
        LAYOUT_TYPE
        if detect_layout(state.buffer) == LAYOUT_CATEGORY
        else LAYOUT_CATEGORY
    )
    if mode == LAYOUT_TYPE and not state.resolved_cards:
        return HandlerResult(
            command_message="E: Card data not available for type layout",
            error=True,
        )
    order_field = state.settings.sort_order
    if order_field not in SORT_FIELDS:
        order_field = "name"
    cursor_text = state.buffer.get_line(state.cursor.row).text
    state.buffer = regroup_buffer(
        state.buffer,
        mode,
        state.resolved_cards,
        order_field,
        price_source=state.settings.price_source,
    )
    new_row = state.cursor.row
    if cursor_text.strip():
        for i in range(state.buffer.line_count()):
            if state.buffer.get_line(i).text == cursor_text:
                new_row = i
                break
    state.cursor = state.cursor.move_to(
        min(new_row, max(0, state.buffer.line_count() - 1)), 0
    )
    state.modified = True
    state.history.record(state.buffer, f"layout by {mode}")
    return HandlerResult(
        command_message=f"Layout: by {mode} (ordered by {order_field})"
    )


def _handle_tag_action(state: EditorState, sub_key: str) -> HandlerResult:
    """Dispatch tag sub-key: a(dd), r(emove), t(oggle), f(ilter), l(ist), c(lear), n/p (jump)."""
    tag_prompts = {
        "a": "tag add: ",
        "r": "tag remove: ",
        "t": "tag toggle: ",
        "f": "filter: ",
    }
    if sub_key in tag_prompts:
        state.tag_input_action = sub_key
        state.insert_submode = InsertSubmode.TAG_INPUT
        return HandlerResult(
            enter_tag_input=True,
            tag_prompt=tag_prompts[sub_key],
        )
    if sub_key == "l":
        # List all tags inline
        return HandlerResult(command_message=format_tag_summary(state.buffer.tag_counts()))
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
    """Process tag-input mode keys (typing tag name, enter to confirm).

    Category input additionally ghosts the best completion (deck
    categories, then cross-deck history, then presets); Tab accepts it.
    """
    key = action.action
    text = action.text or ""
    is_category = state.tag_input_action == "category"

    if key in ("char", "backspace", "delete"):
        if is_category:
            ghost = complete_category(text, state.category_candidates)
            return HandlerResult(command_ghost=ghost)
        return HandlerResult()

    if key == "cursor_move":
        return HandlerResult()

    if key == "tab" and is_category:
        ghost = complete_category(text, state.category_candidates)
        if ghost:
            return HandlerResult(command_accept=ghost, command_ghost="")
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
        state.buffer, count = add_tags_in_range(state.buffer, start, end, [tag])
        if count:
            state.modified = True
            state.history.record(state.buffer, f"tag add #{tag}")
        return f"Tagged {count} card(s) with #{tag}" if count else "No card lines"

    if action == "r":
        state.buffer, count = remove_tags_in_range(state.buffer, start, end, [tag])
        if count:
            state.modified = True
            state.history.record(state.buffer, f"tag remove #{tag}")
        return f"Removed #{tag} from {count} card(s)" if count else f"No cards with #{tag}"

    if action == "t":
        state.buffer, added, removed = toggle_tag_in_range(
            state.buffer, start, end, tag
        )
        if added or removed:
            state.modified = True
            state.history.record(state.buffer, f"tag toggle #{tag}")
        return f"#{tag}: +{added} -{removed}"

    if action == "category":
        name = text.lstrip("@").lower()
        if not CATEGORY_NAME_RE.match(name):
            return (
                f"E: Invalid category: '{name}' "
                "(letters, digits, hyphens; 1-32 chars)"
            )
        state.buffer, count = set_category_in_range(
            state.buffer, start, end, name
        )
        if count:
            state.modified = True
            state.history.record(state.buffer, f"category @{name}")
            record_category(name)
            return f"Categorized {count} card(s) as @{name}"
        return "No card lines"

    if action == "f":
        from vimtg.domain.tags import parse_tag_filter
        from vimtg.editor.command_handlers.tag_cmds import (
            count_filter_matches,
            filter_status_message,
        )

        if not text.strip():
            state.tag_filter = None
            return "Filter cleared"
        state.tag_filter = parse_tag_filter(text)
        visible, total = count_filter_matches(state.buffer, state.tag_filter)
        return filter_status_message(visible, total)

    return ""


# ms/mm/md/mc/mp → the zone (line type) each move key targets
ZONE_TARGETS: dict[str, LineType] = {
    "md": LineType.CARD_ENTRY,
    "ms": LineType.SIDEBOARD_ENTRY,
    "mm": LineType.MAYBEBOARD_ENTRY,
    "mc": LineType.COMMANDER_ENTRY,
    "mp": LineType.COMPANION_ENTRY,
}


def _move_card_to_zone(state: EditorState, key: str, count: int) -> HandlerResult:
    """ms/mm/md — move the card at the cursor to another zone.

    count == 0 moves every copy; a positive count splits that many off.
    """
    target = ZONE_TARGETS[key]
    result = move_to_zone(state.buffer, state.cursor, target, count)
    if not result.moved:
        return HandlerResult(
            command_message=result.message,
            error=result.message.startswith("E:"),
        )
    if result.deleted_row is not None:
        state.marks = state.marks.update_for_delete(
            result.deleted_row, result.deleted_row
        )
    if result.inserted_row is not None:
        state.marks = state.marks.update_for_insert(
            result.inserted_row, result.inserted_count
        )
    state.buffer = result.buffer
    state.cursor = result.cursor
    state.modified = True
    state.history.record(state.buffer, f"move to {ZONE_LABELS[target]}")
    state.dot_repeat.record(RepeatableAction("zone", operator=key, count=count))
    return HandlerResult(command_message=result.message)


def _replay_dot(state: EditorState, count_override: int | None = None) -> None:
    """Replay the last repeatable action, optionally with a new count."""
    last = state.dot_repeat.last_action
    if last is None:
        return
    count = count_override if count_override is not None else last.count
    if last.action_type == "zone" and last.operator:
        _move_card_to_zone(state, last.operator, count)
        return
    if last.action_type == "operator" and last.operator:
        if last.operator == "x":
            for _ in range(count):
                _delete_card_at_cursor(state)
        else:
            result = execute_operator(
                last.operator, last.motion, state.cursor, state.buffer,
                count, state.registers, last.register,
            )
            state.buffer = result.buffer
            state.cursor = result.cursor
            state.registers = result.registers
            state.modified = True
            state.history.record(state.buffer, "dot repeat")
    elif last.action_type == "quantity":
        if last.operator == "+":
            state.buffer = increment_quantity(state.buffer, state.cursor, count)
        elif last.operator == "-":
            state.buffer, state.cursor = decrement_quantity(
                state.buffer, state.cursor, count,
            )
        state.modified = True
        state.history.record(state.buffer, "dot repeat")


def handle_insert_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process insert-mode special keys (typing, tab, enter)."""
    key = action.action
    if key in ("char", "backspace", "delete"):
        state.search_query = action.text or ""
        return HandlerResult(search_query=state.search_query)
    if key == "cursor_move":
        return HandlerResult()
    if key in ("ctrl_j", "ctrl_n", "tab", "down"):
        return HandlerResult(search_query="__next__")
    if key in ("ctrl_k", "ctrl_p", "shift_tab", "up"):
        return HandlerResult(search_query="__prev__")
    if key == "enter":
        return HandlerResult(insert_confirm=True)
    return HandlerResult()


def _is_format_line_edit(prefix: str) -> bool:
    """True when the locked line-edit prefix is the '// Format: ' key."""
    return prefix.strip().lower().replace(" ", "").startswith("//format:")


def _format_ghost(value: str) -> str:
    """First known format completing `value` ('' when none or exact)."""
    typed = value.strip().lower()
    if not typed:
        return ""
    for fmt in known_formats():
        if fmt.startswith(typed) and fmt != typed:
            return fmt
    return ""


def _unknown_format_notice(value: str) -> str:
    """Warning text for a format with no legality rules ('' when fine)."""
    typed = value.strip().lower()
    if not typed or get_format_rules(typed) is not None:
        return ""
    return (
        f"Unknown format '{typed}' — no legality checking "
        f"(known: {', '.join(known_formats())})"
    )


def handle_line_edit_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process line-edit insert-mode keys (typing updates buffer line in real-time).

    On the '// Format:' metadata line the value ghost-completes from the
    formats with legality rules (Tab accepts), and confirming an unknown
    format warns that legality checking is off for it.
    """
    key = action.action
    text = action.text or ""
    row = state.line_edit_row
    prefix = state.line_edit_prefix
    format_line = _is_format_line_edit(prefix)
    if key in ("char", "backspace", "delete"):
        if row is not None and row < state.buffer.line_count():
            state.buffer = state.buffer.set_line(row, prefix + text)
        if format_line:
            return HandlerResult(command_ghost=_format_ghost(text))
        return HandlerResult()
    if key == "cursor_move":
        return HandlerResult()
    if key == "tab" and format_line:
        accepted = _format_ghost(text)
        if not accepted:
            return HandlerResult()
        if row is not None and row < state.buffer.line_count():
            state.buffer = state.buffer.set_line(row, prefix + accepted)
        return HandlerResult(command_accept=accepted)
    if key == "enter":
        # Confirm: record history, clear original (signals "confirmed, don't restore")
        if row is not None:
            # A cleared metadata value leaves '// Format: ' — drop the
            # trailing space so the committed line is '// Format:'
            if row < state.buffer.line_count():
                committed = state.buffer.get_line(row).text
                if committed.rstrip() != committed:
                    state.buffer = state.buffer.set_line(row, committed.rstrip())
            state.history.record(state.buffer, "edit line")
            state.modified = True
        state.line_edit_original = None
        state.line_edit_row = None
        state.insert_submode = InsertSubmode.CARD_SEARCH
        message = _unknown_format_notice(text) if format_line else ""
        return HandlerResult(exit_to_normal=True, command_message=message)
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
    """Count total cards in the buffer.

    parse_deck_text is lenient by design and does not raise on user
    text, so no blanket except is needed — a real bug should surface.
    """
    deck = parse_deck_text(buffer.to_text())
    return sum(e.quantity for e in deck.entries)


def resolve_cards(buffer: Buffer, card_repo: CardRepository) -> dict[str, Card]:
    """Resolve card names in the buffer to Card objects.

    Bad data degrades to "nothing resolved" rather than crashing the
    render path: sqlite errors, and ValueError for corrupt JSON cells
    (row_to_card raises json.JSONDecodeError on an interrupted sync) —
    not arbitrary bugs.
    """
    deck = parse_deck_text(buffer.to_text())
    names = list(deck.unique_card_names())
    try:
        return card_repo.get_by_names(names)
    except (sqlite3.Error, ValueError):
        return {}


def _apply_insert_variant(state: EditorState, variant: str) -> None:
    """Apply buffer changes for insert mode variants (o, O).

    On a metadata line ('// Deck:', '// Format:', ...) both o and O
    open the line below the whole block instead — a card line must
    never split the metadata header.
    """
    row = state.cursor.row
    if state.buffer.get_line(row).line_type == LineType.METADATA:
        while (
            row < state.buffer.line_count()
            and state.buffer.get_line(row).line_type == LineType.METADATA
        ):
            row += 1
        state.buffer = state.buffer.insert_line(row, "")
        state.cursor = state.cursor.move_to(row, 0)
        return
    if variant == "o":
        state.buffer = state.buffer.insert_line(row + 1, "")
        state.cursor = state.cursor.move_to(row + 1, 0)
    elif variant == "O":
        state.buffer = state.buffer.insert_line(row, "")


def _delete_card_at_cursor(state: EditorState) -> None:
    """Delete the card line at cursor, storing in register."""
    if not state.buffer.is_card_line(state.cursor.row):
        return
    new_buf, deleted = state.buffer.delete_lines(state.cursor.row, state.cursor.row)
    state.marks = state.marks.update_for_delete(state.cursor.row, state.cursor.row)
    state.registers = state.registers.set_unnamed(deleted, is_delete=True)
    state.buffer = new_buf
    state.cursor = state.cursor.clamp(max(0, state.buffer.line_count() - 1))
    state.modified = True
    state.history.record(state.buffer, "delete card")
