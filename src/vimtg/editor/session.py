"""Editor session: EditorState and the key-action handlers.

This is the editor engine — pure state + handlers with zero Textual
imports. The TUI layer (MainScreen) feeds it ParsedActions and applies
the returned HandlerResult side effects to widgets.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vimtg.config.category_history import load_category_history, record_category
from vimtg.config.settings import Settings
from vimtg.data.deck_repository import missing_quantity_lines, parse_deck_text
from vimtg.domain.card import Card
from vimtg.domain.card_names import CardMap
from vimtg.domain.categories import (
    CATEGORY_NAME_RE,
    complete_category,
    completion_candidates,
)
from vimtg.domain.deck_lines import parse_zone_header, split_metadata_prefix, zone_context_at
from vimtg.domain.formats import get_format_rules, known_formats
from vimtg.domain.tags import TagFilter
from vimtg.domain.validation import commander_refusal
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.card_insert import (
    PendingInsert,
    discard_pending_insert,
    insert_card,
    open_insert_line,
)
from vimtg.editor.card_insert import (
    take_insert_position as take_insert_position,  # re-exported for the TUI
)
from vimtg.editor.category_ops import (
    clear_category_in_range,
    set_category_in_range,
)
from vimtg.editor.cmdline_history import COMMAND, SEARCH, CommandHistory
from vimtg.editor.command_completer import CommandCompleter, CompletionState
from vimtg.editor.command_handlers.search_cmds import (
    find_card_row,
    search_message,
    wrapped,
)
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    Listing,
    NewBuffer,
    ParsedCommand,
    RangeError,
    parse_command,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.dot_repeat import DotRepeat, RepeatableAction
from vimtg.editor.jumplist import JumpList
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.layout import (
    LAYOUT_CATEGORY,
    LAYOUT_MODES,
    LAYOUT_TYPE,
    detect_layout,
    follow_line,
    regroup_following_cursor,
)
from vimtg.editor.macros import MacroRecorder
from vimtg.editor.marks import MarkStore
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.motions import (
    MOTION_REGISTRY,
    VIEW_MOTIONS,
    motion_goto_line,
)
from vimtg.editor.operators import (
    ZONE_LABELS,
    decrement_quantity,
    execute_operator,
    increment_quantity,
    move_to_zone,
    put_lines,
    resolve_line_range,
    store_lines,
)
from vimtg.editor.placement import PlacementPolicy, reconcile_category_sections
from vimtg.editor.plan_ops import (
    block_at,
    board,
    next_plan_row,
    plan_blocks,
    plan_label,
)
from vimtg.editor.registers import (
    RegisterStore,
    is_clipboard_register,
)
from vimtg.editor.sort_keys import SORT_FIELDS
from vimtg.editor.splits import AnalyticsOpen, EdhrecOpen, SplitOpen, WindowCommand
from vimtg.editor.tag_ops import (
    add_tags_in_range,
    remove_tags_in_range,
    toggle_tag_in_range,
)
from vimtg.services.history_service import HistoryService

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository
    from vimtg.data.file_io import FileStamp
    from vimtg.editor.command_handlers.hand_cmds import HandOpen


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
    jumps: JumpList = field(default_factory=JumpList)  # Ctrl-O / Ctrl-I
    visual_anchor: int | None = None
    # The kind of the selection visual_anchor belongs to; None for a '.'
    # replay's line span, which is not a selection gv can bring back
    visual_kind: Mode | None = None
    # Copies the next confirmed card insert writes ('4o' -> 4); every
    # entry into card search sets it, so it can never go stale
    insert_quantity: int = 1
    # The scratch blank line an o/O opened for card search. Owned by
    # the card-search flow: discarded on escape, consumed on confirm —
    # see discard_pending_insert / take_insert_position.
    pending_insert: PendingInsert | None = None
    insert_submode: InsertSubmode = InsertSubmode.CARD_SEARCH
    line_edit_original: str | None = None
    line_edit_row: int | None = None
    line_edit_prefix: str = ""
    tag_input_action: str = ""
    tag_filter: TagFilter | None = None
    # Ordered completion pool for category input, built on entry
    category_candidates: tuple[str, ...] = ()
    remapper: Any = None  # KeyRemapper, passed through to :map/:unmap
    # The sideboard plan zi/zo write into and the deck view annotates
    active_plan: str | None = None
    # Pattern of the last / ? * # or :find, repeated by n / N; n goes
    # the way the search went (backward after ? and #), N the other way
    last_find: str = ""
    # How messages show last_find: '*' / '#' search by a regex built
    # around the card name, and the name is what the user should see
    last_find_label: str = ""
    last_find_backward: bool = False
    # Direction of the search prompt being typed: ? is backward
    search_backward: bool = False
    # : and / history (Up/Down); the TUI loads the persisted one
    cmd_history: CommandHistory = field(default_factory=CommandHistory)
    # The c / o / O whose card search is open: confirming it records
    # the change, with the card, for '.'
    pending_change: RepeatableAction | None = None
    # Undo node of the delete a c operator made before its card search:
    # the confirmed card folds into it (one change per u)
    change_node: str | None = None
    # Text a "+ / "* yank or delete queued for the system clipboard; the
    # handler returns it as HandlerResult.clipboard_text (the TUI copies)
    clipboard_out: str | None = None
    # Inclusive (top, bottom) buffer rows the cursor can occupy without
    # scrolling the deck view — set by the TUI before H / M / L. None
    # means no view is known and the whole buffer counts as visible.
    view_band: tuple[int, int] | None = None
    # Text of the buffer as last loaded or written; None when unknown.
    # Undo/redo compare against it so returning to it is unmodified.
    clean_text: str | None = None
    # (mtime, size, hash) of the deck file as last read or written — :w
    # uses it to refuse clobbering outside changes. None disables the check.
    disk_stamp: FileStamp | None = None
    # Id of an unnamed buffer's crash-recovery copy (see services.recovery)
    recovery_id: str | None = None
    # The last ex command line typed, which @: runs again
    last_ex: str = ""
    # How the last visual selection ended — its mode, and whether the
    # cursor was at its end (the rows are the '< and '> marks); gv
    last_visual: tuple[Mode, bool] | None = None
    # K flipped the auto_expand setting for the card on this row; it
    # lasts until the cursor leaves the row, like vim's K popup
    details_row: int | None = None

    def remember_selection(self, anchor: int, row: int, mode: Mode) -> None:
        """Keep an ending selection for gv: its rows as the '< and '>
        marks (which follow edits), its mode and which end the cursor was."""
        self.marks = self.marks.set("<", min(anchor, row)).set(">", max(anchor, row))
        self.last_visual = (mode, row >= anchor)

    def end_selection(self) -> None:
        """End the visual selection, keeping it for gv, whichever route
        left visual mode (Esc, an operator, i, /, :, a tag prompt)."""
        if self.visual_anchor is not None and self.visual_kind is not None:
            self.remember_selection(self.visual_anchor, self.cursor.row, self.visual_kind)
        self.visual_anchor = None
        self.visual_kind = None


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
    analytics_open: AnalyticsOpen | None = None
    hand_open: HandOpen | None = None  # sample-hand overlay (:hand)
    import_url: str = ""  # deck-site URL to fetch asynchronously
    clipboard_text: str | None = None  # text to put on the system clipboard
    clipboard_label: str = ""  # what clipboard_text is, for the message
    card_sync: str = ""  # "sync" / "force": start a background card sync
    window: WindowCommand | None = None  # a Ctrl-W window command
    # A pane the Space leader toggles: closes it when it is the one open,
    # else opens it ("analytics" / "edhrec", as _SplitPane.kind)
    toggle_pane: str = ""
    command_prefill: str = ""  # pre-typed text when entering command mode
    run_ex_command: str = ""  # execute an ex command as if typed
    ex_repeat: int = 1  # how many times to run it (3@:)
    plan_changed: bool = False  # active plan or its entries changed
    # zz / zt / zb: put the cursor line at the view's "center"/"top"/"bottom"
    scroll_view: str = ""
    # Replace the command-line text (history recall); None leaves it
    command_replace: str | None = None
    # :e — open this deck in place of the current one
    edit_file: Path | None = None
    ui_request: str = ""  # screen-level view (:messages, :tips)
    # :q! / :e! / :home! dropped unsaved changes on purpose
    discard_changes: bool = False
    search_open: str | None = None  # :search — open the card search overlay
    # A listing's lines; command_message is its one-line form (see Listing)
    listing: Listing | None = None
    # :enew / :import — open this unnamed buffer in place of the deck
    new_buffer: NewBuffer | None = None
    import_force: bool = False  # :import! <url> — the fetch may drop changes


# Motions vim counts as jumps: Ctrl-O comes back from them
JUMP_MOTIONS = frozenset({"G", "gg", "{", "}", "[[", "]]", "H", "M", "L"})


def note_jump(state: EditorState, origin: int, *, far_only: bool = False) -> None:
    """The cursor jumped from row `origin`: Ctrl-O and '' come back to
    it. `far_only` (an insert or zone move filing a card elsewhere)
    counts only a move past the neighbouring lines."""
    row = state.cursor.row
    if row == origin or (far_only and abs(row - origin) <= 1):
        return
    state.jumps = state.jumps.jump(origin)
    state.marks = state.marks.set("'", origin)


def handle_motion(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process motion actions (j, k, G, gg, etc.); the jump motions are
    recorded in the jumplist."""
    origin = state.cursor.row
    result = _motion(state, action)
    if action.action in JUMP_MOTIONS:
        note_jump(state, origin)
    return result


def _motion(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process motion actions (j, k, G, gg, etc.).

    A counted ``G`` (e.g. ``5G``) jumps to that line number; bare ``G`` falls
    through to the registry handler (last line). The registry's ``G`` ignores
    its count, so the counted case must be intercepted here.
    """
    count = action.count if action.count > 0 else 1
    # The keymap sends G with count 0 when no count was typed, so a typed
    # 1G really means line 1.
    if action.action == "G" and action.count >= 1:
        state.cursor = motion_goto_line(state.cursor, state.buffer, action.count)
        return HandlerResult()
    view_fn = VIEW_MOTIONS.get(action.action)
    if view_fn:
        band = state.view_band or (0, state.buffer.line_count() - 1)
        state.cursor = view_fn(state.cursor, state.buffer, band, count)
        return HandlerResult()
    motion_fn = MOTION_REGISTRY.get(action.action)
    if motion_fn:
        state.cursor = motion_fn(state.cursor, state.buffer, count)
    return HandlerResult()


def _take_selection(state: EditorState) -> tuple[int, int] | None:
    """The visual selection as (start, end) rows, ending it; None when
    there is no selection."""
    if state.visual_anchor is None:
        return None
    last = max(0, state.buffer.line_count() - 1)
    anchor = min(state.visual_anchor, last)
    row = min(state.cursor.row, last)
    state.end_selection()
    return min(anchor, row), max(anchor, row)


def _mirror_clipboard(state: EditorState, register: str | None) -> None:
    """A yank or delete into "+ / "* also goes to the system clipboard:
    queue the text; _with_clipboard hands it to the TUI, which copies."""
    if is_clipboard_register(register):
        state.clipboard_out = "\n".join(state.registers.get("+").content) + "\n"


def _with_clipboard(state: EditorState, hr: HandlerResult) -> HandlerResult:
    """Attach queued "+ register text to `hr` for the TUI to copy."""
    text = state.clipboard_out
    if text is None:
        return hr
    state.clipboard_out = None
    lines = text.count("\n")
    return replace(
        hr, clipboard_text=text,
        clipboard_label=f"register + ({lines} line{'s' if lines != 1 else ''})",
    )


def handle_operator(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process operator actions (dd, yy, cc, dj, etc.).

    In visual mode, operates on the selected range (anchor → cursor).
    """
    return _with_clipboard(state, _operator(state, action))


def _operator(state: EditorState, action: ParsedAction) -> HandlerResult:
    selection = _take_selection(state)
    if selection is not None:
        start, end = selection
        lines = end - start + 1
        op = action.action[0]
        # Recorded as the doubled operator over the selection's size,
        # so '.' after Vjd deletes two lines again
        repeat = RepeatableAction(
            "operator", operator=op + op, count=lines, register=action.register,
        )
        result = execute_operator(
            op + op, None, state.cursor.move_to(start, 0),
            state.buffer, lines, state.registers, action.register,
        )
        affected = (start, end)
    else:
        # G keeps a raw 0 ("no count": dG to the end, d8G to line 8)
        count = action.count if action.motion == "G" else (action.count or 1)
        affected = resolve_line_range(
            action.action, action.motion, state.cursor, state.buffer, count,
        )
        repeat = RepeatableAction(
            "operator", operator=action.action,
            motion=action.motion, count=count,
            register=action.register,
        )
        result = execute_operator(
            action.action, action.motion, state.cursor, state.buffer,
            count, state.registers, action.register,
        )
    changed = result.buffer is not state.buffer
    stored = result.registers is not state.registers
    if result.buffer.line_count() < state.buffer.line_count():
        state.marks = state.marks.update_for_delete(*affected)
    state.buffer = result.buffer
    state.cursor = result.cursor
    state.registers = result.registers
    if stored:
        _mirror_clipboard(state, action.register)
    if changed:
        state.modified = True
        state.history.record(state.buffer, f"{action.action} operation")
    if repeat.operator and repeat.operator[0] != "y":
        state.dot_repeat.record(repeat)
    if result.enter_insert:
        # 'c' enters card search; its count means lines, not copies.
        # Confirming a card upgrades the recorded change to include it.
        state.insert_quantity = 1
        state.pending_change = repeat
        state.change_node = state.history.current_id if changed else None
        return HandlerResult(enter_insert=True)
    # Exit visual mode after operation
    if state.mode_mgr.current in (Mode.VISUAL, Mode.VISUAL_LINE):
        return HandlerResult(exit_to_normal=True)
    return HandlerResult()


def _line_edit_prefix(buffer: Buffer, row: int) -> str:
    """The part of a line `i` keeps locked: the whole '// Key: ' prefix
    of a metadata line, the '// ' marker of a comment, the indentation
    of a line inside a zone or plan block (deleting it would silently
    rezone the line and every line beneath it), else nothing."""
    line_text = buffer.get_line(row).text
    meta = split_metadata_prefix(line_text)
    if meta is not None:
        return meta[0]
    # Protect the // comment marker — user edits only the content after it
    if line_text.lstrip().startswith("//"):
        idx = line_text.index("//") + 2
        # Include trailing space after // if present
        if idx < len(line_text) and line_text[idx] == " ":
            idx += 1
        return line_text[:idx]
    texts = [bl.text for bl in buffer.get_lines()]
    if zone_context_at(texts, row) is not None:
        return line_text[: len(line_text) - len(line_text.lstrip())]
    return ""


def handle_mode_switch(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process mode switch actions (i, o, :, v, escape)."""
    key = action.action
    if key == "escape":
        state.end_selection()
        return HandlerResult(exit_to_normal=True)
    if key == "i":
        line_text = state.buffer.get_line(state.cursor.row).text
        zone = parse_zone_header(line_text)
        if zone is not None:
            return HandlerResult(
                command_message=(
                    f"E21: Cannot edit the {zone}: zone header "
                    "(it opens the block below; edit the cards in it)"
                ),
                error=True,
            )
        state.insert_submode = InsertSubmode.LINE_EDIT
        state.line_edit_original = line_text
        state.line_edit_row = state.cursor.row
        state.line_edit_prefix = _line_edit_prefix(state.buffer, state.cursor.row)
        return HandlerResult(enter_line_edit=True)
    if key in ("o", "O"):
        # Visual o/O swaps the selection's ends, vim-style — it must
        # never open a line (doing so used to mutate the buffer and
        # then crash on the VISUAL->INSERT transition)
        if state.mode_mgr.is_visual() and state.visual_anchor is not None:
            # An edit inside the selection (e.g. '.') can leave the
            # anchor past the end of a shrunken buffer
            anchor = min(state.visual_anchor, state.buffer.line_count() - 1)
            state.visual_anchor = state.cursor.row
            state.cursor = state.cursor.move_to(anchor, 0)
            return HandlerResult()
        # Vim-style count as copies: 4o opens a card search whose
        # confirmed card is added as '4 <name>'
        state.insert_quantity = max(1, action.count)
        state.change_node = None  # an o/O card is a change of its own
        open_insert_line(state, key)
        state.pending_change = RepeatableAction(
            "insert", operator=key, quantity=state.insert_quantity,
        )
        return HandlerResult(enter_insert=True)
    if key == ":":
        state.cmd_history.reset_browse()
        selection = _take_selection(state)
        if selection is not None:
            # Vim: ':' on a selection pre-types its range, '<,'>
            state.marks = state.marks.set("<", selection[0]).set(">", selection[1])
            return HandlerResult(enter_command=True, command_prefill="'<,'>")
        return HandlerResult(enter_command=True)
    if key in ("/", "?"):
        state.search_backward = key == "?"
        state.cmd_history.reset_browse()
        return HandlerResult(enter_search=True)
    if key in ("v", "V"):
        target = Mode.VISUAL if key == "v" else Mode.VISUAL_LINE
        current = state.mode_mgr.current
        # Vim: the same visual key again ends the selection; the other
        # one switches kind and keeps the selection's anchor
        if current == target:
            state.end_selection()
            return HandlerResult(exit_to_normal=True)
        if not state.mode_mgr.is_visual() or state.visual_anchor is None:
            state.visual_anchor = state.cursor.row
        state.visual_kind = target
        return HandlerResult(enter_visual=target)
    return HandlerResult()


def _submit_search(state: EditorState, text: str) -> HandlerResult:
    """/pattern or ?pattern <Enter>: jump to the next (previous) card
    matching, wrapping around. An empty pattern reuses the last one."""
    backward = state.search_backward
    state.search_backward = False
    pattern = text or state.last_find
    prefix = "?" if backward else "/"
    if not pattern:
        return HandlerResult(
            command_message="E35: No previous regular expression", error=True,
        )
    try:
        row = find_card_row(state.buffer, state.cursor.row, pattern, backward=backward)
    except re.error:
        return HandlerResult(command_message=f"E: Invalid pattern: {pattern}", error=True)
    state.last_find = pattern
    if text:  # an empty pattern reuses the last one, label and all
        state.last_find_label = ""
    shown = state.last_find_label or pattern
    state.last_find_backward = backward
    if row is None:
        return HandlerResult(command_message=f"Pattern not found: {shown}")
    origin = state.cursor.row
    wrap = wrapped(origin, row, backward=backward)
    state.cursor = state.cursor.move_to(row, 0)
    note_jump(state, origin)
    return HandlerResult(
        command_message=search_message(prefix + shown, wrap=wrap, backward=backward),
    )


def handle_command(
    state: EditorState,
    action: ParsedAction,
    registry: CommandRegistry,
    file_path: Path | None,
    save_fn: Callable[[Path, str], None] | None = None,
    *,
    record_history: bool = True,
    pane_open: bool = False,
) -> HandlerResult:
    """Process ex command or search submission.

    Typed lines go into the : / search history; commands a key runs on
    the user's behalf (ZZ is :x) pass record_history=False. `pane_open`
    says a split pane is open, so :q closes it rather than the app.
    """
    if state.mode_mgr.current == Mode.SEARCH:
        state.cmd_history.add(SEARCH, action.text or "")
        return _submit_search(state, action.text or "")
    if not action.text:
        return HandlerResult()
    if record_history:
        state.cmd_history.add(COMMAND, action.text)
        state.last_ex = action.text
    raw_text = action.text

    try:
        try:
            cmd = parse_command(
                raw_text, state.cursor.row, state.buffer.line_count(),
                {name: mark.row for name, mark in state.marks.items()},
            )
        except RangeError as exc:
            return HandlerResult(command_message=f"E: {exc}", error=True)
        ctx = EditorContext(
            file_path=file_path, modified=state.modified,
            save_fn=save_fn, settings=state.settings,
            resolved_cards=state.resolved_cards,
            history=state.history,
            card_repo=state.card_repo,
            remapper=state.remapper,
            active_plan=state.active_plan,
            disk_stamp=state.disk_stamp,
            registers=state.registers,
            marks=state.marks,
            last_pattern=state.last_find,
            recovery_id=state.recovery_id,
            pane_open=pane_open,
        )
        before = state.buffer
        before_text = before.to_text()
        origin = state.cursor.row
        state.buffer, state.cursor = registry.execute(cmd, state.buffer, state.cursor, ctx)
        if not cmd.name and cmd.cmd_range is not None:
            note_jump(state, origin)  # :{n}
        if cmd.name in ("find", "f") and cmd.args and not ctx.error:
            state.last_find = cmd.args
            state.last_find_label = ""
            state.last_find_backward = False
        if ctx.registers is not None:
            state.registers = ctx.registers
        if ctx.marks is not None:
            state.marks = ctx.marks
        # Backstop for every handler: a command whose buffer text differs
        # afterwards changed the deck — it is modified and gets one undo
        # step, whether or not the handler remembered to say so (:sort
        # once forgot, so u could not revert it and :q lost it). Text
        # that did not change never dirties the buffer, whatever the
        # handler claims; only a write clears the flag.
        changed = state.buffer is not before and state.buffer.to_text() != before_text
        if changed:
            state.history.record(state.buffer, f":{action.text}")
            if registry.resolve(cmd.name) == "s":
                state.dot_repeat.record(RepeatableAction("ex", text=cmd.args))
        if changed:
            state.modified = True
        elif ctx.file_saved:
            state.modified = ctx.modified
        if ctx.undo_request:
            step = state.history.undo if ctx.undo_request == "undo" else state.history.redo
            restored = step()
            if restored is not None:
                restore_buffer(state, restored)
        if ctx.file_saved:
            state.clean_text = state.buffer.to_text()
        state.disk_stamp = ctx.disk_stamp
        plan_changed = False
        if ctx.active_plan_set:
            state.active_plan = ctx.active_plan
            plan_changed = True
        if ctx.settings_changed and ctx.settings is not None:
            state.settings = ctx.settings
        if ctx.resolved_cards is not None and ctx.resolved_cards is not state.resolved_cards:
            state.resolved_cards = CardMap(ctx.resolved_cards)
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
            split_open=ctx.split_open,
            split_close=ctx.split_close,
            edhrec_open=ctx.edhrec_open,
            analytics_open=ctx.analytics_open,
            hand_open=ctx.hand_open,
            import_url=ctx.import_url,
            clipboard_text=ctx.clipboard_text,
            clipboard_label=ctx.clipboard_label,
            card_sync=ctx.card_sync,
            plan_changed=plan_changed,
            edit_file=ctx.edit_path,
            ui_request=ctx.ui_request,
            discard_changes=ctx.discard_requested,
            search_open=ctx.search_open,
            listing=ctx.listing,
            new_buffer=ctx.new_buffer,
            import_force=ctx.import_force,
        )
    except Exception as exc:
        return HandlerResult(command_message=f"E: {exc}", error=True)


def handle_normal_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process normal-mode special keys (u, p, +, -, x, ., q, @, m, ').

    A count prefix repeats or scales the action vim-style: 10+ adds 10
    to the quantity, 2x deletes two cards, 3p pastes three copies.
    With a visual selection, + - and the z zone keys act on every card
    in it and end the selection.
    """
    return _with_clipboard(state, _normal_special(state, action))


def _normal_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    key = action.action
    count = action.count if action.count > 0 else 1
    if key in ("u", "ctrl_r"):
        step = state.history.undo if key == "u" else state.history.redo
        for _ in range(count):
            restored = step()
            if restored is None:
                break
            restore_buffer(state, restored)
    elif key in ("p", "P") and state.visual_anchor is not None and state.mode_mgr.is_visual():
        return _put_over_selection(state, key, count, action.register)
    elif key in ("p", "P"):
        if _put(state, key, count, action.register):
            state.dot_repeat.record(RepeatableAction(
                "put", operator=key, count=count, register=action.register,
            ))
    elif key in ("+", "-"):
        return _change_quantity(state, key, count)
    elif key == "x":
        _delete_cards_at_cursor(state, count, action.register)
        state.dot_repeat.record(
            RepeatableAction("operator", operator="x", count=count, register=action.register)
        )
    elif key in ("n", "N"):
        return _repeat_find(
            state, backward=state.last_find_backward != (key == "N"), count=count,
        )
    elif key in ("*", "#"):
        return _search_card_under_cursor(state, backward=(key == "#"), count=count)
    elif key == ".":
        # A count given to '.' replaces the recorded one (vim semantics);
        # count=1 is indistinguishable from "no count", so only >1 overrides.
        return _replay_dot(state, count if count > 1 else None) or HandlerResult()
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
    elif key == "@:" or (key == "@@" and state.macros.last_played == ":"):
        if not state.last_ex:
            return HandlerResult(command_message="E30: No previous command line", error=True)
        state.macros.played_command_line()
        return HandlerResult(run_ex_command=state.last_ex, ex_repeat=count)
    elif key.startswith("@") and len(key) == 2:
        keys = state.macros.play(key[1])
        if keys is None:
            return HandlerResult(
                command_message=f"Nothing recorded in @{key[1]}"
            )
        return HandlerResult(replay_keys=keys * count)
    elif key in ("zz", "zt", "zb"):
        position = {"zz": "center", "zt": "top", "zb": "bottom"}[key]
        return HandlerResult(scroll_view=position)
    elif key in ("zs", "zm", "zd", "zc", "zp"):
        # Zone moves; action.count is read raw because 0 means "no count
        # given" — move every copy (see keymap).
        return _move_card_to_zone(state, key, action.count)
    elif key in ("zi", "zo"):
        # Board in/out of the active sideboard plan
        return _board_card(state, key, action.count)
    elif key in ("]v", "[v"):
        return _jump_plan(state, forward=(key == "]v"))
    elif key.startswith("m") and len(key) == 2:
        mark_name = key[1]
        state.marks = state.marks.set(mark_name, state.cursor.row)
        return HandlerResult(
            command_message=f"Mark '{mark_name}' set",
        )
    elif key in ("ctrl_o", "tab"):
        return _walk_jumps(state, back=key == "ctrl_o", count=count)
    elif key.startswith("'") and len(key) == 2:
        mark_name = key[1]
        mark = state.marks.get(mark_name)
        if mark is not None:
            origin = state.cursor.row
            row = min(mark.row, state.buffer.line_count() - 1)
            state.cursor = state.cursor.move_to(row, 0)
            note_jump(state, origin)
        elif key == "''":
            return HandlerResult(command_message="E20: Mark not set", error=True)
        else:
            return HandlerResult(
                command_message=f"Mark '{mark_name}' not set",
            )
    elif key in WINDOW_KEYS:
        return WINDOW_KEYS[key]
    elif key == "space f":
        return _open_filter_prompt(state)
    elif key in LEADER_KEYS:
        return LEADER_KEYS[key]
    elif key in ("gc", "gC", "gl"):
        return _handle_category_action(state, key[1])
    elif key == "gh":
        return HandlerResult(open_history_screen=True)
    elif key == "g?":
        return HandlerResult(help_requested=True)
    elif key == "gv":
        return _reselect(state)
    elif key in ("ZZ", "ZQ"):
        # Vim's ZZ / ZQ are exactly :x / :q! (ZZ writes only when modified)
        return HandlerResult(run_ex_command="x" if key == "ZZ" else "q!")
    elif key == "A":
        return _handle_comment_action(state)
    elif key == "K":
        return _toggle_details(state)
    return HandlerResult()


def _walk_jumps(state: EditorState, *, back: bool, count: int) -> HandlerResult:
    """Ctrl-O / Ctrl-I (Tab): `count` places back / forward in the jumplist."""
    if back:
        state.jumps, row = state.jumps.back(state.cursor.row, count)
    else:
        state.jumps, row = state.jumps.forward(count)
    if row is not None:
        state.cursor = state.cursor.move_to(min(row, max(0, state.buffer.line_count() - 1)), 0)
    return HandlerResult()


def _reselect(state: EditorState) -> HandlerResult:
    """gv — select the last visual selection again, in its mode and with
    the cursor at the same end; in visual mode the two swap, as in vim."""
    start_mark, end_mark = state.marks.get("<"), state.marks.get(">")
    if state.last_visual is None or start_mark is None or end_mark is None:
        return HandlerResult(command_message="No previous visual selection")
    mode, cursor_at_end = state.last_visual
    last = max(0, state.buffer.line_count() - 1)
    start, end = min(start_mark.row, last), min(end_mark.row, last)
    current = state.mode_mgr.current
    if state.mode_mgr.is_visual() and state.visual_anchor is not None:
        state.remember_selection(state.visual_anchor, state.cursor.row, current)
    state.visual_anchor = start if cursor_at_end else end
    state.visual_kind = mode
    state.cursor = state.cursor.move_to(end if cursor_at_end else start, 0)
    return HandlerResult(enter_visual=None if mode == current else mode)


def _toggle_details(state: EditorState) -> HandlerResult:
    """K — vim's keyword lookup: show or hide the cursor card's details
    (the opposite of what the auto_expand setting does there)."""
    row = state.cursor.row
    name = state.buffer.card_name_at(row)
    if not name:
        return HandlerResult(command_message="E348: No card under cursor", error=True)
    if name not in state.resolved_cards:
        return HandlerResult(command_message=f"No card data for {name} (:sync)", error=True)
    state.details_row = None if state.details_row == row else row
    return HandlerResult()


def _put(state: EditorState, key: str, count: int, register: str | None) -> bool:
    """p / P count times from `register`; True when lines went in."""
    before = state.buffer.line_count()
    first_insert_row = state.cursor.row + (0 if key == "P" else 1)
    # One block of count copies (9999p is one insert, not 9999)
    state.buffer, state.cursor = put_lines(
        state.buffer, state.cursor, state.registers, register,
        above=(key == "P"), count=count,
    )
    inserted = state.buffer.line_count() - before
    if inserted <= 0:
        return False
    if key == "p":
        # p leaves the cursor on the last pasted row; P stays on the
        # top of the stack it put above the line
        state.cursor = state.cursor.move_to(first_insert_row + inserted - 1, 0)
    state.marks = state.marks.update_for_insert(first_insert_row, inserted)
    state.modified = True
    state.history.record(state.buffer, "put" if key == "p" else "put above")
    return True


UNNAMED = '"'  # the unnamed register


def _put_over_selection(
    state: EditorState, key: str, count: int, register: str | None,
) -> HandlerResult:
    """Visual p / P: replace the selected lines with the register, `count`
    times, as one change, and leave visual mode. p keeps the replaced
    lines in the unnamed register (and "1); P leaves the registers be."""
    content = state.registers.get(register or UNNAMED).content
    selection = _take_selection(state)
    assert selection is not None
    if not content:
        return HandlerResult(
            command_message=f"E353: Nothing in register {register or UNNAMED}",
            error=True, exit_to_normal=True,
        )
    start, end = selection
    buffer, deleted = state.buffer.delete_lines(start, end)
    state.marks = state.marks.update_for_delete(start, end)
    if key == "p":
        state.registers = store_lines(state.registers, None, deleted, is_delete=True)
    lines = content * count
    for offset, text in enumerate(lines):
        buffer = buffer.insert_line(start + offset, text)
    state.marks = state.marks.update_for_insert(start, len(lines))
    state.buffer = buffer
    state.cursor = state.cursor.move_to(start, 0)
    state.modified = True
    state.history.record(state.buffer, "put over selection")
    return HandlerResult(exit_to_normal=True)


def _change_quantity(state: EditorState, key: str, count: int) -> HandlerResult:
    """+ / - on the cursor card, or on every card in a visual selection
    (one undo step; a card reaching 0 is deleted)."""
    selection = _take_selection(state)
    start, end = selection if selection is not None else (state.cursor.row,) * 2
    before = state.buffer
    # Bottom-up, so a deleted line never shifts the rows still to do
    for row in range(end, start - 1, -1):
        cursor = state.cursor.move_to(row, 0)
        if key == "+":
            state.buffer = increment_quantity(state.buffer, cursor, count)
            continue
        old_count = state.buffer.line_count()
        state.buffer, _ = decrement_quantity(state.buffer, cursor, count)
        if state.buffer.line_count() < old_count:
            state.marks = state.marks.update_for_delete(row, row)
    last = max(0, state.buffer.line_count() - 1)
    if selection is not None:
        state.cursor = state.cursor.move_to(min(start, last), 0)
    else:
        state.cursor = state.cursor.clamp(last)
    lines = end - start + 1 if selection is not None else 0
    if state.buffer is not before:
        state.modified = True
        state.history.record(
            state.buffer, "increment" if key == "+" else "decrement", rows=(start, end),
        )
    state.dot_repeat.record(
        RepeatableAction("quantity", operator=key, count=count, lines=lines)
    )
    return HandlerResult(exit_to_normal=selection is not None)


def _search_card_under_cursor(
    state: EditorState, *, backward: bool, count: int
) -> HandlerResult:
    """* / # — search forward / backward for the card under the cursor
    (the whole name, so Shock never stops on Shock Troops); n / N repeat."""
    name = state.buffer.card_name_at(state.cursor.row)
    if not name:
        return HandlerResult(command_message="E348: No card under cursor", error=True)
    # Quantity (and any zone prefix), the exact name, then only the end
    # of the line or its @category / #tags / // comment
    state.last_find = (
        rf"^\s*(?:(?:SB|MB|CMD|CMP):\s*)?\d+\s+{re.escape(name)}"
        r"(?=\s*(?:$|[@#]|//))"
    )
    state.last_find_label = name
    state.last_find_backward = backward
    return _repeat_find(state, backward=backward, count=count)


def _first_changed_row(old: Buffer, new: Buffer) -> int | None:
    """The first row where `new` differs from `old`; None if identical."""
    old_lines = [line.text for line in old.get_lines()]
    new_lines = [line.text for line in new.get_lines()]
    for row, (a, b) in enumerate(zip(old_lines, new_lines, strict=False)):
        if a != b:
            return row
    return None if len(old_lines) == len(new_lines) else min(len(old_lines), len(new_lines))


def restore_buffer(state: EditorState, buffer: Buffer) -> None:
    """Swap in a buffer from history (undo/redo), keeping every row
    reference inside it.

    The cursor goes to the first line the step changed, as in vim; the
    restored buffer can be shorter than the one it replaces, so the
    cursor and visual anchor are clamped, and the modified flag follows
    whether the text differs from the last loaded/saved state — undoing
    back to it is clean again, as in vim.
    """
    changed = _first_changed_row(state.buffer, buffer)
    state.buffer = buffer
    last = max(0, buffer.line_count() - 1)
    if changed is not None:
        state.cursor = state.cursor.move_to(changed, 0)
    state.cursor = state.cursor.clamp(last)
    if state.visual_anchor is not None:
        state.visual_anchor = max(0, min(state.visual_anchor, last))
    state.pending_insert = None
    if state.clean_text is None:
        state.modified = True
    else:
        state.modified = buffer.to_text() != state.clean_text


def _repeat_find(state: EditorState, *, backward: bool, count: int) -> HandlerResult:
    """n / N — jump to the next / previous card matching the last / or
    :find pattern, wrapping around the buffer."""
    pattern = state.last_find
    if not pattern:
        return HandlerResult(command_message="No previous search pattern", error=True)
    shown = state.last_find_label or pattern
    row = state.cursor.row
    wrap = False
    for _ in range(count):
        found = find_card_row(state.buffer, row, pattern, backward=backward)
        if found is None:
            return HandlerResult(
                command_message=f"Pattern not found: {shown}", error=True,
            )
        wrap = wrap or wrapped(row, found, backward=backward)
        row = found
    origin = state.cursor.row
    state.cursor = state.cursor.move_to(row, 0)
    note_jump(state, origin)
    echo = ("?" if backward else "/") + shown
    return HandlerResult(
        command_message=search_message(echo, wrap=wrap, backward=backward),
    )


# Ctrl-W {key}: vim's window commands. v / s prompt for the deck to
# split with; the rest act on the editor and its one pane.
WINDOW_KEYS: dict[str, HandlerResult] = {
    "ctrl_w v": HandlerResult(enter_command=True, command_prefill="vsplit "),
    "ctrl_w s": HandlerResult(enter_command=True, command_prefill="split "),
    "ctrl_w w": HandlerResult(window=WindowCommand.NEXT),
    "ctrl_w W": HandlerResult(window=WindowCommand.NEXT),
    "ctrl_w h": HandlerResult(window=WindowCommand.LEFT),
    "ctrl_w j": HandlerResult(window=WindowCommand.DOWN),
    "ctrl_w k": HandlerResult(window=WindowCommand.UP),
    "ctrl_w l": HandlerResult(window=WindowCommand.RIGHT),
    "ctrl_w c": HandlerResult(window=WindowCommand.CLOSE),
    "ctrl_w q": HandlerResult(window=WindowCommand.QUIT),
    "ctrl_w o": HandlerResult(window=WindowCommand.ONLY),
}

# <Space>{key}: the leader. The panes toggle; the hand is an overlay;
# Space f (the filter prompt) needs the state, see _open_filter_prompt.
LEADER_KEYS: dict[str, HandlerResult] = {
    "space a": HandlerResult(toggle_pane="analytics"),
    "space r": HandlerResult(toggle_pane="edhrec"),
    "space h": HandlerResult(run_ex_command="hand"),
}


def _handle_comment_action(state: EditorState) -> HandlerResult:
    """Enter comment-input mode for the card under the cursor (A key)."""
    if not state.buffer.is_card_line(state.cursor.row):
        return HandlerResult(command_message="Comments attach to card lines")
    state.end_selection()
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
        state.dot_repeat.record(RepeatableAction("comment", text=text))
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
            state.end_selection()
        else:
            start = end = row
        state.buffer, count = clear_category_in_range(state.buffer, start, end)
        if count:
            _refile_categories(state)
            state.modified = True
            state.history.record(state.buffer, "clear category")
            state.dot_repeat.record(RepeatableAction(
                "category", lines=end - start + 1 if end > start else 0,
            ))
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


def _refile_categories(state: EditorState) -> None:
    """After a category edit in a category-grouped deck, move the edited
    cards under the headers their tokens name (the cursor follows)."""
    refiled = reconcile_category_sections(state.buffer)
    if refiled is state.buffer:
        return
    row = follow_line(state.buffer, refiled, state.cursor.row)
    state.buffer = refiled
    state.cursor = state.cursor.move_to(
        min(row, max(0, refiled.line_count() - 1)), 0
    )


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
    state.buffer, new_row = regroup_following_cursor(
        state.buffer,
        state.cursor.row,
        mode,
        state.resolved_cards,
        order_field,
        state.settings.price_source,
    )
    state.cursor = state.cursor.move_to(new_row, 0)
    state.modified = True
    state.history.record(state.buffer, f"layout by {mode}")
    return HandlerResult(
        command_message=f"Layout: by {mode} (ordered by {order_field})"
    )


def _open_filter_prompt(state: EditorState) -> HandlerResult:
    """Space f: prompt for a view filter expression (Enter on an empty
    prompt clears the filter, as :filter does)."""
    state.tag_input_action = "f"
    state.insert_submode = InsertSubmode.TAG_INPUT
    return HandlerResult(enter_tag_input=True, tag_prompt="filter: ")


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
        # An empty filter clears it (as :filter does); other prompts cancel
        clears_filter = state.tag_input_action == "f"
        state.tag_input_action = ""
        state.insert_submode = InsertSubmode.CARD_SEARCH
        if clears_filter:
            state.tag_filter = None
            return HandlerResult(exit_to_normal=True, command_message="Filter cleared")
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
        state.end_selection()
    else:
        start = end = row
    if action in ("a", "r", "t", "category"):
        # '.' re-applies the same tag/category, over as many lines
        state.dot_repeat.record(RepeatableAction(
            "category" if action == "category" else "tag",
            operator=action, text=text,
            lines=end - start + 1 if end > start else 0,
        ))

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
            _refile_categories(state)
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

        state.tag_filter = parse_tag_filter(text)
        visible, total = count_filter_matches(state.buffer, state.tag_filter)
        return filter_status_message(visible, total)

    return ""


# zs/zm/zd/zc/zp → the zone (line type) each move key targets
ZONE_TARGETS: dict[str, LineType] = {
    "zd": LineType.CARD_ENTRY,
    "zs": LineType.SIDEBOARD_ENTRY,
    "zm": LineType.MAYBEBOARD_ENTRY,
    "zc": LineType.COMMANDER_ENTRY,
    "zp": LineType.COMPANION_ENTRY,
}


def _placement_policy(state: EditorState) -> PlacementPolicy:
    """The mainboard placement policy for the card under the cursor."""
    name = state.buffer.card_name_at(state.cursor.row)
    card = state.resolved_cards.get(name) if name else None
    return PlacementPolicy(
        auto_sort=state.settings.auto_sort,
        type_line=card.type_line if card is not None else None,
    )


def _commander_warning(state: EditorState, row: int) -> str:
    """Why the card zc just put at `row` can't be the deck's commander
    ('' when it can, or its card or format is unknown)."""
    name = state.buffer.card_name_at(row)
    card = state.resolved_cards.get(name) if name else None
    if name is None or card is None:
        return ""
    deck = parse_deck_text(state.buffer.to_text())
    fmt = (deck.metadata.format or state.settings.default_format).strip().lower()
    rules = get_format_rules(fmt) if fmt else None
    if rules is None:
        return ""
    return commander_refusal(name, card, rules.name) or ""


def _zone_refusal(state: EditorState, target: LineType) -> tuple[str, bool]:
    """(message, refuse) when the deck's format lacks the target zone:
    a command zone outside commander formats is refused; a sideboard in
    a format without one is allowed with a warning. ('', False) when
    the format is unknown or has the zone."""
    if target not in (LineType.COMMANDER_ENTRY, LineType.SIDEBOARD_ENTRY):
        return "", False
    deck = parse_deck_text(state.buffer.to_text())
    fmt = (deck.metadata.format or state.settings.default_format).strip().lower()
    rules = get_format_rules(fmt) if fmt else None
    if rules is None:
        return "", False
    if target == LineType.COMMANDER_ENTRY and not rules.requires_commander:
        return f"E: {fmt} has no command zone (set // Format: to a commander format)", True
    if target == LineType.SIDEBOARD_ENTRY and not rules.allows_sideboard:
        return f"{fmt} has no sideboard", False
    return "", False


def _move_card_to_zone(state: EditorState, key: str, count: int) -> HandlerResult:
    """zs/zm/zd/zc/zp — move the card at the cursor (or every card in a
    visual selection) to another zone.

    count == 0 moves every copy; a positive count splits that many off.
    With auto-sort on, a move into the mainboard lands where the
    placement policy says (its type section, its category's section,
    or the uncategorized group) — never the bottom of the zone. A move
    into a zone the deck's format does not have is refused (command
    zone) or warned about (sideboard).
    """
    target = ZONE_TARGETS[key]
    selection = _take_selection(state)
    warning, refuse = _zone_refusal(state, target)
    if refuse:
        return HandlerResult(
            command_message=warning, error=True, exit_to_normal=selection is not None,
        )
    if selection is None:
        rows = [state.cursor.row]
    else:
        rows = [
            r for r in range(selection[0], selection[1] + 1)
            if state.buffer.is_card_line(r)
        ]
    moved = 0
    first_message = ""
    first_error = False
    origin = state.cursor
    for i, row in enumerate(rows):
        state.cursor = state.cursor.move_to(row, 0)
        result = move_to_zone(
            state.buffer, state.cursor, target, count,
            policy=_placement_policy(state),
        )
        if not first_message:
            first_message, first_error = result.message, result.message.startswith("E:")
        if not result.moved:
            continue
        moved += 1
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
        # Later selected rows shift with the lines this move removed/added
        for j in range(i + 1, len(rows)):
            if result.deleted_row is not None and rows[j] > result.deleted_row:
                rows[j] -= 1
            if result.inserted_row is not None and rows[j] >= result.inserted_row:
                rows[j] += result.inserted_count
    if selection is not None:
        last = max(0, state.buffer.line_count() - 1)
        state.cursor = origin.move_to(min(selection[0], last), 0)
    else:
        note_jump(state, origin.row, far_only=True)  # the cursor went with the card
    if moved == 0:
        if selection is not None and not rows:
            first_message = "No card lines selected"
        return HandlerResult(
            command_message=first_message, error=first_error,
            exit_to_normal=selection is not None,
        )
    state.modified = True
    state.history.record(state.buffer, f"move to {ZONE_LABELS[target]}")
    lines = selection[1] - selection[0] + 1 if selection is not None else 0
    state.dot_repeat.record(
        RepeatableAction("zone", operator=key, count=count, lines=lines)
    )
    message = (
        first_message if selection is None
        else f"Moved {moved} card(s) to {ZONE_LABELS[target]}"
    )
    if target == LineType.COMMANDER_ENTRY and selection is None:
        warning = _commander_warning(state, state.cursor.row)
    if warning:
        message = f"{message} — warning: {warning}"
    return HandlerResult(command_message=message, exit_to_normal=selection is not None)


def _resolve_active_plan(state: EditorState) -> str | None:
    """The plan zi/zo write into: the active one, else the deck's only
    plan (activated as a side effect). None when there is no unambiguous
    choice."""
    if state.active_plan is not None:
        return state.active_plan
    blocks = plan_blocks(state.buffer)
    if len(blocks) == 1:
        state.active_plan = blocks[0].name
        return blocks[0].name
    return None


def _board_card(state: EditorState, key: str, count: int) -> HandlerResult:
    """zi/zo — board the cursor card (or every card in a visual
    selection) in/out of the active sideboard plan.

    count == 0 boards every copy; a positive count boards that many.
    The plan block is edited in place (an undoable text edit); the
    cursor stays on the deck card so the next zi/zo is one key away.
    """
    selection = _take_selection(state)
    exit_visual = selection is not None
    plan = _resolve_active_plan(state)
    if plan is None:
        if plan_blocks(state.buffer):
            msg = "E: Several sideboard plans — :plan <matchup> or ]v to pick one"
        else:
            msg = "E: No sideboard plan — :plan <matchup> to start one"
        return HandlerResult(command_message=msg, error=True, exit_to_normal=exit_visual)
    if selection is None:
        rows = [state.cursor.row]
    else:
        rows = [
            r for r in range(selection[0], selection[1] + 1)
            if state.buffer.is_card_line(r)
        ]
    cursor_row = state.cursor.row if selection is None else selection[0]
    boarded = 0
    message = ""
    error = False
    for i, row in enumerate(rows):
        result = board(
            state.buffer, row, plan,
            direction="in" if key == "zi" else "out", count=count,
        )
        if not message or (error and not result.error):
            message, error = result.message, result.error
        if result.error or result.buffer is state.buffer:
            continue
        boarded += 1
        shifted = [cursor_row, *rows[i + 1:]]
        if result.inserted_row is not None:
            state.marks = state.marks.update_for_insert(result.inserted_row, 1)
            shifted = [r + 1 if result.inserted_row <= r else r for r in shifted]
        if result.deleted_row is not None:
            state.marks = state.marks.update_for_delete(
                result.deleted_row, result.deleted_row
            )
            shifted = [r - 1 if result.deleted_row < r else r for r in shifted]
        cursor_row = shifted[0]
        rows[i + 1:] = shifted[1:]
        state.buffer = result.buffer
    state.cursor = state.cursor.move_to(
        max(0, min(cursor_row, state.buffer.line_count() - 1)), 0
    )
    if boarded == 0:
        return HandlerResult(command_message=message, error=error, exit_to_normal=exit_visual)
    state.modified = True
    state.history.record(
        state.buffer, "board in" if key == "zi" else "board out"
    )
    lines = selection[1] - selection[0] + 1 if selection is not None else 0
    state.dot_repeat.record(
        RepeatableAction("board", operator=key, count=count, lines=lines)
    )
    if selection is not None:
        verb = "in" if key == "zi" else "out"
        message = f"Boarded {boarded} card(s) {verb} — vs {plan}"
    return HandlerResult(
        command_message=message, plan_changed=True, exit_to_normal=exit_visual,
    )


def _jump_plan(state: EditorState, forward: bool) -> HandlerResult:
    """]v / [v — move to the next/previous plan header and activate it."""
    row = next_plan_row(state.buffer, state.cursor.row, forward)
    if row is None:
        which = "next" if forward else "previous"
        return HandlerResult(command_message=f"No {which} sideboard plan")
    state.cursor = state.cursor.move_to(row, 0)
    block = block_at(state.buffer, row)
    if block is None:
        return HandlerResult()
    state.active_plan = block.name
    return HandlerResult(
        command_message=plan_label(state.buffer, block), plan_changed=True
    )


def _replay_dot(
    state: EditorState, count_override: int | None = None
) -> HandlerResult | None:
    """Replay the last repeatable change, optionally with a new count.

    A change made on a visual selection replays on as many lines from
    the cursor; the replayed change is recorded again, so a count given
    to '.' sticks, as in vim. Returns the replayed handler's result
    (so '.' on a visual selection leaves visual mode like the change
    it repeats did), or None.
    """
    last = state.dot_repeat.last_action
    if last is None:
        return None
    count = count_override if count_override is not None else last.count
    if last.lines > 0:
        last_row = max(0, state.buffer.line_count() - 1)
        state.visual_anchor = min(state.cursor.row + last.lines - 1, last_row)
    try:
        return _replay(state, last, count, count_override)
    finally:
        state.visual_anchor = None
        state.pending_change = None


def _replay(
    state: EditorState, last: RepeatableAction, count: int, count_override: int | None
) -> HandlerResult | None:
    op = last.operator or ""
    kind = last.action_type
    if kind == "zone":
        return _move_card_to_zone(state, op, count)
    if kind == "board":
        return _board_card(state, op, count)
    if kind == "quantity":
        return _change_quantity(state, op, count)
    if kind == "put":
        if _put(state, op, count, last.register):
            state.dot_repeat.record(replace(last, count=count))
    elif kind == "operator" and op == "x":
        _delete_cards_at_cursor(state, count, last.register)
        state.dot_repeat.record(replace(last, count=count))
    elif kind == "operator":
        _replay_operator(state, last, count)
    elif kind == "insert":
        quantity = count_override if count_override is not None else last.quantity
        open_insert_line(state, op)
        if last.card_name:
            insert_card(state, last.card_name, last.card, quantity)
        else:
            discard_pending_insert(state)
        state.dot_repeat.record(replace(last, quantity=quantity))
    elif kind in ("tag", "category") and last.text is not None:
        state.tag_input_action = op or "category"
        _apply_tag_input(state, last.text)
        state.tag_input_action = ""
    elif kind == "category":
        _handle_category_action(state, "C")
    elif kind == "comment":
        _replay_comment(state, last.text or "")
    elif kind == "line_edit":
        _replay_line_edit(state, last.text or "")
    elif kind == "ex":
        _replay_substitute(state, last.text or "")
    return None


def _replay_operator(state: EditorState, last: RepeatableAction, count: int) -> None:
    """'.' after d/c + motion (and c with the card it inserted)."""
    op = last.operator or ""
    affected = resolve_line_range(op, last.motion, state.cursor, state.buffer, count)
    result = execute_operator(
        op, last.motion, state.cursor, state.buffer,
        count, state.registers, last.register,
    )
    # Deletes must shift marks exactly like the live operator did
    if result.buffer.line_count() < state.buffer.line_count():
        state.marks = state.marks.update_for_delete(*affected)
    if result.registers is not state.registers:
        state.registers = result.registers
        _mirror_clipboard(state, last.register)
    fold_into = None
    if result.buffer is not state.buffer:
        state.buffer = result.buffer
        state.cursor = result.cursor
        state.modified = True
        state.history.record(state.buffer, "dot repeat")
        fold_into = state.history.current_id
    if result.enter_insert and last.card_name:
        state.pending_insert = None
        insert_card(state, last.card_name, last.card, last.quantity, fold_into=fold_into)
    state.dot_repeat.record(replace(last, count=count))


def _replay_comment(state: EditorState, text: str) -> None:
    row = state.cursor.row
    state.dot_repeat.record(RepeatableAction("comment", text=text))
    if not state.buffer.is_card_line(row) or state.buffer.comment_at(row) == text:
        return
    state.buffer = state.buffer.set_comment(row, text)
    state.modified = True
    state.history.record(state.buffer, "edit comment")


def _replay_line_edit(state: EditorState, text: str) -> None:
    """'.' after i: give this line the same value, keeping its own
    locked prefix (metadata key, // marker, block indentation)."""
    row = state.cursor.row
    state.dot_repeat.record(RepeatableAction("line_edit", text=text))
    line = state.buffer.get_line(row).text
    new = (_line_edit_prefix(state.buffer, row) + text).rstrip()
    if new == line:
        return
    state.buffer = state.buffer.set_line(row, new)
    state.modified = True
    state.history.record(state.buffer, "edit line")


def _replay_substitute(state: EditorState, args: str) -> None:
    """'.' after :s — the same substitute on the cursor line (vim's &&)."""
    from vimtg.editor.command_handlers.substitute import cmd_substitute

    ctx = EditorContext(last_pattern=state.last_find)
    cmd = ParsedCommand(name="s", args=args)
    new_buf, _ = cmd_substitute(state.buffer, state.cursor, cmd, ctx)
    state.dot_repeat.record(RepeatableAction("ex", text=args))
    if new_buf is state.buffer or ctx.error:
        return
    state.buffer = new_buf
    state.modified = True
    state.history.record(state.buffer, "dot repeat :s")


def confirm_card_search(state: EditorState, card: Card) -> str:
    """Write the card chosen in the o/O/c search and return the status
    message. Records the change — with the card and its copies — for
    '.', so 'o eidolon<CR> j .' adds Eidolon again and 'cc fire<CR> .'
    changes the next line to it too."""
    copies = state.insert_quantity
    state.insert_quantity = 1
    origin = state.pending_insert.origin if state.pending_insert else state.cursor.row
    pending = state.pending_change
    fold_into = state.change_node if pending is not None else None
    state.change_node = None
    message = insert_card(state, card.name, card, copies, fold_into=fold_into)
    note_jump(state, origin, far_only=True)  # auto-filed into another section
    state.pending_change = None
    if pending is not None:
        state.dot_repeat.record(
            replace(pending, card_name=card.name, card=card, quantity=copies)
        )
    return message


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
            changed = True
            # A cleared metadata value leaves '// Format: ' — drop the
            # trailing space so the committed line is '// Format:'
            if row < state.buffer.line_count():
                committed = state.buffer.get_line(row).text
                if committed.rstrip() != committed:
                    committed = committed.rstrip()
                    state.buffer = state.buffer.set_line(row, committed)
                # i then Enter on an untouched line is not a change: no
                # undo step, and the deck is not dirty for it
                changed = committed != state.line_edit_original
            if changed:
                state.history.record(state.buffer, "edit line")
                state.modified = True
                state.dot_repeat.record(RepeatableAction("line_edit", text=text))
        state.line_edit_original = None
        state.line_edit_row = None
        state.insert_submode = InsertSubmode.CARD_SEARCH
        message = _unknown_format_notice(text) if format_line else ""
        return HandlerResult(exit_to_normal=True, command_message=message)
    return HandlerResult()


def command_argument_candidates(state: EditorState, command: str) -> tuple[str, ...]:
    """Tab-completion candidates for `command`'s argument, best first:
    layout modes, sort fields, the deck's tags (most used first) for
    :filter, and the category pool gc uses for :category."""
    if command == "layout":
        return LAYOUT_MODES
    if command == "sort":
        return tuple(sorted(SORT_FIELDS))
    if command == "filter":
        counts = state.buffer.tag_counts()
        return tuple(sorted(counts, key=lambda tag: (-counts[tag], tag)))
    if command == "category":
        return completion_candidates(
            state.buffer.category_counts(), load_category_history(),
        )
    return ()


def handle_command_special(state: EditorState, action: ParsedAction) -> HandlerResult:
    """Process command-mode special keys for fuzzy completion."""
    key = action.action
    text = action.text or ""
    completer = state.cmd_completer

    if key in ("up", "down"):
        kind = SEARCH if state.mode_mgr.current == Mode.SEARCH else COMMAND
        if key == "up":
            recalled = state.cmd_history.older(kind, text)
        else:
            recalled = state.cmd_history.newer(kind)
        if recalled is None:
            return HandlerResult()
        return HandlerResult(command_replace=recalled, command_ghost="")

    if key in ("char", "backspace", "delete"):
        # Editing ends a history browse: the next Up matches the new text
        state.cmd_history.reset_browse()

    if state.mode_mgr.current == Mode.SEARCH:
        # A / pattern is not an ex command: no ghost, and Tab must not
        # rewrite the pattern as one
        return HandlerResult()

    if completer is None:
        return HandlerResult()

    if key in ("char", "backspace", "delete"):
        state.cmd_completion = completer.complete(
            text, lambda command: command_argument_candidates(state, command),
        )
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
    # Plan entries name cards too — they render with mana/type and lint
    # unknown names like any card line
    plan_names = {e.card_name for plan in deck.plans for e in plan.entries}
    # A card written without a quantity is linted when it names a card
    missing_names = {m.card_name for m in missing_quantity_lines(buffer.to_text())}
    names = list(deck.unique_card_names() | plan_names | missing_names)
    try:
        return card_repo.get_by_names(names)
    except (sqlite3.Error, ValueError):
        return {}


def _delete_cards_at_cursor(
    state: EditorState, count: int = 1, register: str | None = None
) -> None:
    """x / Nx: delete the card line at the cursor and up to count-1
    card lines directly below it as ONE change — one undo step and
    one register entry holding every line, as vim's Nx — stopping at
    the first non-card line."""
    row = state.cursor.row
    if not state.buffer.is_card_line(row):
        return
    end = row
    while end - row + 1 < count and state.buffer.is_card_line(end + 1):
        end += 1
    new_buf, deleted = state.buffer.delete_lines(row, end)
    state.marks = state.marks.update_for_delete(row, end)
    state.registers = store_lines(state.registers, register, deleted, is_delete=True)
    _mirror_clipboard(state, register)
    state.buffer = new_buf
    state.cursor = state.cursor.clamp(max(0, state.buffer.line_count() - 1))
    state.modified = True
    label = "delete card" if len(deleted) == 1 else f"delete {len(deleted)} cards"
    state.history.record(state.buffer, label)
