"""Tests for :category/:categories/:layout, the g-key flow, and wiring."""

from __future__ import annotations

import pytest

from vimtg.config.settings import Settings
from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.command_handlers.category_cmds import (
    cmd_categories,
    cmd_category,
    cmd_layout,
)
from vimtg.editor.commands import (
    CommandRange,
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult, ParsedAction
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import (
    EditorState,
    handle_normal_special,
    handle_tag_input_special,
)
from vimtg.services.history_service import HistoryService


def _card(name: str, type_line: str, cmc: float = 1.0) -> Card:
    return Card.from_scryfall({
        "id": "x", "name": name, "type_line": type_line, "cmc": cmc,
    })


def _ctx(**kwargs) -> EditorContext:  # type: ignore[no-untyped-def]
    kwargs.setdefault("settings", Settings())
    return EditorContext(**kwargs)


def _state(text: str, resolved: dict[str, Card] | None = None) -> EditorState:
    buf = Buffer.from_text(text)
    history = HistoryService()
    history.initialize(buf)
    return EditorState(
        buffer=buf,
        cursor=Cursor(row=0),
        mode_mgr=ModeManager(),
        registers=RegisterStore(),
        history=history,
        modified=False,
        resolved_cards=resolved or {},
    )


class TestCmdCategory:
    def test_sets_category(self) -> None:
        buf = Buffer.from_text("4 Cultivate\n")
        ctx = _ctx()
        buf, _ = cmd_category(
            buf, Cursor(), ParsedCommand(name="category", args="ramp"), ctx
        )
        assert buf.category_at(0) == "ramp"
        assert ctx.modified
        assert "@ramp" in ctx.message

    def test_range_support(self) -> None:
        buf = Buffer.from_text("4 Cultivate\n4 Opt\n4 Shock\n")
        cmd = ParsedCommand(
            name="category", args="ramp",
            cmd_range=CommandRange(start=0, end=1),
        )
        buf, _ = cmd_category(buf, Cursor(), cmd, _ctx())
        assert buf.category_at(0) == "ramp"
        assert buf.category_at(1) == "ramp"
        assert buf.category_at(2) == ""

    def test_bang_clears(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp\n")
        ctx = _ctx()
        buf, _ = cmd_category(
            buf, Cursor(), ParsedCommand(name="category", bang=True), ctx
        )
        assert buf.category_at(0) == ""
        assert ctx.modified

    def test_no_args_shows_current(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp\n")
        ctx = _ctx()
        cmd_category(buf, Cursor(), ParsedCommand(name="category"), ctx)
        assert "@ramp" in ctx.message
        assert not ctx.modified

    def test_invalid_name_fails(self) -> None:
        buf = Buffer.from_text("4 Cultivate\n")
        ctx = _ctx()
        cmd_category(
            buf, Cursor(), ParsedCommand(name="category", args="no spaces"), ctx
        )
        assert ctx.error

    def test_no_card_lines(self) -> None:
        buf = Buffer.from_text("// Creatures\n")
        ctx = _ctx()
        cmd_category(
            buf, Cursor(), ParsedCommand(name="category", args="ramp"), ctx
        )
        assert not ctx.modified
        assert "No card lines" in ctx.message


class TestCmdCategories:
    def test_lists_counts(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp\n4 Opt  @draw\n")
        ctx = _ctx()
        cmd_categories(buf, Cursor(), ParsedCommand(name="categories"), ctx)
        assert "@draw(1)" in ctx.message
        assert "@ramp(1)" in ctx.message

    def test_lists_cards_in_category(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp\n4 Opt  @draw\n")
        ctx = _ctx()
        cmd_categories(
            buf, Cursor(), ParsedCommand(name="categories", args="ramp"), ctx
        )
        assert "Cultivate" in ctx.message
        assert "Opt" not in ctx.message


class TestCmdLayout:
    def test_explicit_category_mode(self) -> None:
        buf = Buffer.from_text("1 Cultivate  @ramp\n1 Forest\n")
        ctx = _ctx()
        buf, _ = cmd_layout(
            buf, Cursor(), ParsedCommand(name="layout", args="category"), ctx
        )
        text = buf.to_text()
        assert "// @ramp" in text
        assert "// Uncategorized" in text
        assert ctx.modified

    def test_toggle_without_args(self) -> None:
        buf = Buffer.from_text("1 Cultivate  @ramp\n")
        ctx = _ctx()
        buf, _ = cmd_layout(buf, Cursor(), ParsedCommand(name="layout"), ctx)
        assert "// @ramp" in buf.to_text()

    def test_type_mode_needs_card_data(self) -> None:
        buf = Buffer.from_text("// @ramp\n1 Cultivate  @ramp\n")
        ctx = _ctx()
        cmd_layout(
            buf, Cursor(), ParsedCommand(name="layout", args="type"), ctx
        )
        assert ctx.error

    def test_type_mode_with_card_data(self) -> None:
        resolved = {"Cultivate": _card("Cultivate", "Sorcery", 3.0)}
        buf = Buffer.from_text("// @ramp\n1 Cultivate  @ramp\n")
        ctx = _ctx(resolved_cards=resolved)
        buf, _ = cmd_layout(buf, Cursor(), ParsedCommand(name="layout"), ctx)
        assert "// Sorceries" in buf.to_text()

    def test_invalid_mode_fails(self) -> None:
        ctx = _ctx()
        cmd_layout(
            Buffer.from_text("1 Opt\n"), Cursor(),
            ParsedCommand(name="layout", args="bogus"), ctx,
        )
        assert ctx.error

    def test_cursor_follows_card(self) -> None:
        buf = Buffer.from_text("1 Forest\n1 Cultivate  @ramp\n")
        ctx = _ctx()
        new_buf, new_cursor = cmd_layout(
            buf, Cursor(row=1),
            ParsedCommand(name="layout", args="category"), ctx,
        )
        assert "Cultivate" in new_buf.get_line(new_cursor.row).text


class TestRegistration:
    def test_commands_and_aliases_registered(self) -> None:
        registry = CommandRegistry()
        register_all_commands(registry)
        for name in ("category", "categories", "layout"):
            assert name in registry._commands
        for alias in ("cat", "cats"):
            assert alias in registry._aliases


class TestGKeymap:
    @pytest.mark.parametrize("sub", ["c", "C", "l"])
    def test_g_subkeys_parse(self, sub: str) -> None:
        km = KeyMap()
        result, _ = km.feed("g")
        assert result == KeyResult.PENDING
        result, action = km.feed(sub)
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == f"g{sub}"
        assert action.action_type == "special"

    def test_gg_still_motion(self) -> None:
        km = KeyMap()
        km.feed("g")
        _, action = km.feed("g")
        assert action is not None
        assert action.action_type == "motion"

    def test_visual_gc_not_swallowed_by_change_operator(self) -> None:
        km = KeyMap(Mode.VISUAL_LINE)
        result, _ = km.feed("g")
        assert result == KeyResult.PENDING
        result, action = km.feed("c")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "gc"


class TestGKeyFlow:
    def test_gc_enters_category_input(self) -> None:
        state = _state("4 Cultivate  @ramp\n4 Opt\n")
        hr = handle_normal_special(state, ParsedAction("special", "gc"))
        assert hr.enter_tag_input
        assert hr.tag_prompt == "category: "
        assert state.tag_input_action == "category"
        assert "ramp" in state.category_candidates

    def test_category_input_ghost_completion(self) -> None:
        state = _state("4 Cultivate\n")
        handle_normal_special(state, ParsedAction("special", "gc"))
        hr = handle_tag_input_special(
            state, ParsedAction("special", "char", text="ra")
        )
        assert hr.command_ghost == "ramp"

    def test_category_input_tab_accepts_ghost(self) -> None:
        state = _state("4 Cultivate\n")
        handle_normal_special(state, ParsedAction("special", "gc"))
        hr = handle_tag_input_special(
            state, ParsedAction("special", "tab", text="ra")
        )
        assert hr.command_accept == "ramp"

    def test_category_input_enter_applies(self) -> None:
        state = _state("4 Cultivate\n")
        handle_normal_special(state, ParsedAction("special", "gc"))
        hr = handle_tag_input_special(
            state, ParsedAction("special", "enter", text="ramp")
        )
        assert state.buffer.category_at(0) == "ramp"
        assert "@ramp" in hr.command_message
        assert state.modified

    def test_category_input_visual_range(self) -> None:
        state = _state("4 Cultivate\n4 Opt\n")
        state.visual_anchor = 0
        state.cursor = state.cursor.move_to(1, 0)
        handle_normal_special(state, ParsedAction("special", "gc"))
        handle_tag_input_special(
            state, ParsedAction("special", "enter", text="ramp")
        )
        assert state.buffer.category_at(0) == "ramp"
        assert state.buffer.category_at(1) == "ramp"

    def test_category_input_invalid_name_errors(self) -> None:
        state = _state("4 Cultivate\n")
        handle_normal_special(state, ParsedAction("special", "gc"))
        hr = handle_tag_input_special(
            state, ParsedAction("special", "enter", text="!!bad!!")
        )
        assert hr.command_message.startswith("E:")
        assert state.buffer.category_at(0) == ""

    def test_g_cap_c_clears(self) -> None:
        state = _state("4 Cultivate  @ramp\n")
        hr = handle_normal_special(state, ParsedAction("special", "gC"))
        assert state.buffer.category_at(0) == ""
        assert "Cleared" in hr.command_message

    def test_g_cap_c_nothing_to_clear(self) -> None:
        state = _state("4 Cultivate\n")
        hr = handle_normal_special(state, ParsedAction("special", "gC"))
        assert "No category" in hr.command_message
        assert not state.modified

    def test_gl_toggles_to_category_layout(self) -> None:
        state = _state("1 Cultivate  @ramp\n1 Opt  @draw\n")
        hr = handle_normal_special(state, ParsedAction("special", "gl"))
        assert "// @ramp" in state.buffer.to_text()
        assert "category" in hr.command_message
        assert state.modified

    def test_gl_back_to_type_needs_card_data(self) -> None:
        state = _state("// @ramp\n1 Cultivate  @ramp\n")
        hr = handle_normal_special(state, ParsedAction("special", "gl"))
        assert hr.error
        assert "// @ramp" in state.buffer.to_text()

    def test_gl_roundtrip_with_card_data(self) -> None:
        resolved = {"Cultivate": _card("Cultivate", "Sorcery", 3.0)}
        state = _state("1 Cultivate  @ramp\n", resolved)
        handle_normal_special(state, ParsedAction("special", "gl"))
        assert "// @ramp" in state.buffer.to_text()
        handle_normal_special(state, ParsedAction("special", "gl"))
        assert "// Sorceries" in state.buffer.to_text()
        assert "@ramp" in state.buffer.to_text()  # token survives

    def test_gl_undoable(self) -> None:
        state = _state("1 Cultivate  @ramp\n")
        original = state.buffer.to_text()
        handle_normal_special(state, ParsedAction("special", "gl"))
        assert state.buffer.to_text() != original
        handle_normal_special(state, ParsedAction("special", "u"))
        assert state.buffer.to_text() == original


class TestSortDefaultsToSetting:
    def test_default_field_from_settings(self) -> None:
        from vimtg.editor.command_handlers.sort import cmd_sort

        resolved = {
            "Opt": _card("Opt", "Instant", 1.0),
            "Cultivate": _card("Cultivate", "Sorcery", 3.0),
        }
        buf = Buffer.from_text("1 Cultivate\n1 Opt\n")
        ctx = _ctx(resolved_cards=resolved)
        buf, _ = cmd_sort(buf, Cursor(), ParsedCommand(name="sort"), ctx)
        assert "by cmc" in ctx.message
        assert buf.get_line(0).text == "1 Opt"

    def test_sort_order_setting_respected(self) -> None:
        from vimtg.editor.command_handlers.sort import cmd_sort

        buf = Buffer.from_text("1 Opt\n1 Cultivate\n")
        ctx = _ctx(settings=Settings(sort_order="name"))
        buf, _ = cmd_sort(buf, Cursor(), ParsedCommand(name="sort"), ctx)
        assert "by name" in ctx.message
        assert buf.get_line(0).text == "1 Cultivate"


class TestCategoryEditsRefile:
    """In a category-grouped deck a card's @token and the header it sits
    under are one fact: setting or clearing the category moves the card
    to the matching section, and the cursor follows."""

    DECK = "// @ramp\n1 Cultivate  @ramp\n1 Opt  @ramp\n\n// @draw\n1 Ponder  @draw\n"

    def test_cmd_category_moves_card_to_its_section(self) -> None:
        buf = Buffer.from_text(self.DECK)
        buf, cursor = cmd_category(
            buf, Cursor(row=2), ParsedCommand(name="category", args="draw"), _ctx()
        )
        lines = buf.to_text().splitlines()
        assert lines == [
            "// @ramp", "1 Cultivate  @ramp", "",
            "// @draw", "1 Ponder  @draw", "1 Opt  @draw",
        ]
        assert cursor.row == lines.index("1 Opt  @draw")

    def test_cmd_category_bang_moves_card_to_uncategorized(self) -> None:
        buf = Buffer.from_text(self.DECK)
        buf, cursor = cmd_category(
            buf, Cursor(row=2), ParsedCommand(name="category", bang=True), _ctx()
        )
        lines = buf.to_text().splitlines()
        assert lines[-2:] == ["// Uncategorized", "1 Opt"]
        assert cursor.row == len(lines) - 1

    def test_gc_moves_card_and_cursor(self) -> None:
        state = _state(self.DECK)
        state.cursor = state.cursor.move_to(2, 0)
        handle_normal_special(state, ParsedAction("special", "gc"))
        handle_tag_input_special(
            state, ParsedAction("special", "enter", text="draw")
        )
        lines = state.buffer.to_text().splitlines()
        assert lines[-2:] == ["1 Ponder  @draw", "1 Opt  @draw"]
        assert state.cursor.row == len(lines) - 1

    def test_gc_new_category_creates_section(self) -> None:
        state = _state(self.DECK)
        state.cursor = state.cursor.move_to(2, 0)
        handle_normal_special(state, ParsedAction("special", "gc"))
        handle_tag_input_special(
            state, ParsedAction("special", "enter", text="cantrip")
        )
        lines = state.buffer.to_text().splitlines()
        assert lines[-2:] == ["// @cantrip", "1 Opt  @cantrip"]

    def test_g_cap_c_moves_to_uncategorized(self) -> None:
        state = _state(self.DECK)
        state.cursor = state.cursor.move_to(2, 0)
        handle_normal_special(state, ParsedAction("special", "gC"))
        lines = state.buffer.to_text().splitlines()
        assert lines[-2:] == ["// Uncategorized", "1 Opt"]

    def test_refile_is_one_undo_step(self) -> None:
        state = _state(self.DECK)
        state.cursor = state.cursor.move_to(2, 0)
        handle_normal_special(state, ParsedAction("special", "gc"))
        handle_tag_input_special(
            state, ParsedAction("special", "enter", text="draw")
        )
        handle_normal_special(state, ParsedAction("special", "u"))
        assert state.buffer.to_text() == self.DECK

    def test_type_layout_only_edits_the_token(self) -> None:
        state = _state("// Sorceries\n1 Ponder\n1 Opt\n")
        state.cursor = state.cursor.move_to(2, 0)
        handle_normal_special(state, ParsedAction("special", "gc"))
        handle_tag_input_special(
            state, ParsedAction("special", "enter", text="draw")
        )
        assert state.buffer.to_text() == "// Sorceries\n1 Ponder\n1 Opt  @draw\n"
