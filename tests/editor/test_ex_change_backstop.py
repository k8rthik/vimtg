"""Session-level data safety: every ex command that changes the deck
dirties it and is one undo step (the handle_command backstop), cc plus
its card is one change, and ':' on a visual selection pre-types '<,'>.

TUI-agnostic: drives EditorState through the session handlers.
"""

from __future__ import annotations

from pathlib import Path

from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import CommandRegistry, EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import (
    EditorState,
    confirm_card_search,
    handle_command,
    handle_mode_switch,
    handle_normal_special,
    handle_operator,
)
from vimtg.services.history_service import HistoryService

DECK = (
    "// Deck: Burn\n\n// Instant\n4 Skullcrack\n4 Lightning Bolt\n"
    "4 Searing Blaze\n\n// Land\n20 Mountain\n"
)


def _state(text: str = DECK, row: int = 3) -> EditorState:
    buf = Buffer.from_text(text)
    history = HistoryService()
    history.initialize(buf)
    return EditorState(
        buffer=buf, cursor=Cursor(row=row), mode_mgr=ModeManager(),
        registers=RegisterStore(), history=history, modified=False,
        resolved_cards={}, clean_text=buf.to_text(),
    )


def _registry() -> CommandRegistry:
    registry = CommandRegistry()
    register_all_commands(registry)
    return registry


def _ex(st: EditorState, text: str, registry: CommandRegistry | None = None) -> str:
    action = ParsedAction("command_submit", "enter", text=text)
    return handle_command(st, action, registry or _registry(), None).command_message


def _undo(st: EditorState) -> None:
    handle_normal_special(st, ParsedAction("special", "u"))


def _card(name: str) -> Card:
    return Card.from_scryfall({
        "id": name, "name": name, "mana_cost": "{R}", "cmc": 1.0,
        "type_line": "Instant", "oracle_text": "",
    })


class TestBackstop:
    def test_a_handler_that_forgets_to_mark_modified_is_caught(self) -> None:
        """A future handler that rewrites the buffer without setting
        ctx.modified still dirties the deck and gets an undo step."""

        def sloppy(
            buf: Buffer, cur: Cursor, cmd: ParsedCommand, ctx: EditorContext
        ) -> tuple[Buffer, Cursor]:
            return buf.set_line(3, "4 Shock"), cur

        registry = _registry()
        registry.register("sloppy", sloppy)
        st = _state()
        _ex(st, "sloppy", registry)
        assert st.modified is True
        assert "4 Shock" in st.buffer.to_text()
        _undo(st)
        assert st.buffer.to_text() == DECK
        assert st.modified is False

    def test_a_handler_claiming_a_change_that_made_none_is_ignored(self) -> None:
        def liar(
            buf: Buffer, cur: Cursor, cmd: ParsedCommand, ctx: EditorContext
        ) -> tuple[Buffer, Cursor]:
            ctx.modified = True
            return Buffer.from_text(buf.to_text()), cur

        registry = _registry()
        registry.register("liar", liar)
        st = _state()
        _ex(st, "liar", registry)
        assert st.modified is False
        assert not st.history.can_undo

    def test_sort_is_modified_and_undoable(self) -> None:
        st = _state()
        _ex(st, "sort name")
        assert st.buffer.get_line(3).text == "4 Lightning Bolt"
        assert st.modified is True
        _undo(st)
        assert st.buffer.to_text() == DECK

    def test_write_still_clears_modified(self, tmp_path: Path) -> None:
        st = _state()
        _ex(st, "sort name")
        saved: list[str] = []
        action = ParsedAction("command_submit", "enter", text=f"w {tmp_path / 'x'}")
        hr = handle_command(
            st, action, _registry(), None, lambda _p, t: saved.append(t),
        )
        assert hr.file_saved and saved
        assert st.modified is False

    def test_range_error_is_reported(self) -> None:
        st = _state()
        assert "E20" in _ex(st, "'x,'yd")
        assert st.buffer.to_text() == DECK


class TestVisualColon:
    def test_colon_in_visual_prefills_marks(self) -> None:
        st = _state()
        handle_mode_switch(st, ParsedAction("mode_switch", "V"))
        st.mode_mgr.transition(Mode.VISUAL_LINE)
        st.cursor = st.cursor.move_to(5, 0)
        hr = handle_mode_switch(st, ParsedAction("mode_switch", ":"))
        assert hr.enter_command and hr.command_prefill == "'<,'>"
        assert st.visual_anchor is None
        lt, gt = st.marks.get("<"), st.marks.get(">")
        assert lt is not None and gt is not None
        assert (lt.row, gt.row) == (3, 5)
        _ex(st, "'<,'>d")
        assert "Skullcrack" not in st.buffer.to_text()
        assert "Searing Blaze" not in st.buffer.to_text()

    def test_colon_in_normal_has_no_prefill(self) -> None:
        hr = handle_mode_switch(_state(), ParsedAction("mode_switch", ":"))
        assert hr.enter_command and hr.command_prefill == ""


class TestChangeFoldsTheCard:
    def test_cc_and_card_are_one_undo_step(self) -> None:
        st = _state(row=4)
        hr = handle_operator(st, ParsedAction("operator", "cc", count=1))
        assert hr.enter_insert
        confirm_card_search(st, _card("Shock"))
        assert "Shock" in st.buffer.to_text()
        assert "Lightning Bolt" not in st.buffer.to_text()
        _undo(st)
        assert st.buffer.to_text() == DECK

    def test_dot_repeat_of_cc_is_one_undo_step(self) -> None:
        st = _state(row=3)
        handle_operator(st, ParsedAction("operator", "cc", count=1))
        confirm_card_search(st, _card("Shock"))
        after_first = st.buffer.to_text()
        row = next(
            i for i in range(st.buffer.line_count())
            if st.buffer.get_line(i).text == "4 Searing Blaze"
        )
        st.cursor = st.cursor.move_to(row, 0)
        handle_normal_special(st, ParsedAction("special", "."))
        assert "Searing Blaze" not in st.buffer.to_text()
        _undo(st)
        assert st.buffer.to_text() == after_first

    def test_o_after_a_cancelled_cc_does_not_fold(self) -> None:
        from vimtg.editor.card_insert import discard_pending_insert

        st = _state(row=4)
        handle_operator(st, ParsedAction("operator", "cc", count=1))
        discard_pending_insert(st)  # Esc
        after_delete = st.buffer.to_text()
        handle_mode_switch(st, ParsedAction("mode_switch", "o"))
        confirm_card_search(st, _card("Shock"))
        _undo(st)
        assert st.buffer.to_text() == after_delete
