"""Argument completion for :layout, :sort, :filter, and :category, plus
--format shell completion for `vimtg new`."""

from __future__ import annotations

import click
import pytest

from vimtg.cli import _complete_format
from vimtg.domain.formats import known_formats
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_completer import CommandCompleter
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import CommandRegistry
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.modes import ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import (
    EditorState,
    command_argument_candidates,
    handle_command_special,
)
from vimtg.editor.sort_keys import SORT_FIELDS
from vimtg.services.history_service import HistoryService

DECK = (
    "// Creatures\n"
    "4 Llanowar Elves  @ramp  #core\n"
    "4 Elvish Mystic  @ramp  #core #flex\n"
    "2 Harmonize  @draw  #flex\n"
    "1 Craterhoof Behemoth  @wincon  #core\n"
)


def _registry() -> CommandRegistry:
    reg = CommandRegistry()
    register_all_commands(reg)
    return reg


def _state() -> EditorState:
    buf = Buffer.from_text(DECK)
    history = HistoryService()
    history.initialize(buf)
    st = EditorState(
        buffer=buf, cursor=Cursor(row=1), mode_mgr=ModeManager(),
        registers=RegisterStore(), history=history, modified=False,
        resolved_cards={},
    )
    st.cmd_completer = CommandCompleter(_registry())
    return st


def _type(st: EditorState, text: str) -> str:
    """Type `text` into the command line; return the ghost."""
    return handle_command_special(st, ParsedAction("special", "char", text=text)).command_ghost


def _tab(st: EditorState) -> str:
    return handle_command_special(st, ParsedAction("special", "tab")).command_accept


class TestCandidates:
    def test_layout(self) -> None:
        assert command_argument_candidates(_state(), "layout") == ("type", "category")

    def test_sort(self) -> None:
        assert set(command_argument_candidates(_state(), "sort")) == SORT_FIELDS

    def test_filter_categories_most_used_first(self) -> None:
        assert command_argument_candidates(_state(), "filter") == ("ramp", "draw", "wincon")

    def test_category_deck_first_then_presets(self) -> None:
        candidates = command_argument_candidates(_state(), "category")
        assert candidates[:3] == ("ramp", "draw", "wincon")
        assert len(candidates) > 3  # presets follow

    def test_other_commands_have_none(self) -> None:
        assert command_argument_candidates(_state(), "write") == ()


class TestCompleteArguments:
    def test_sort_prefix(self) -> None:
        st = _state()
        assert _type(st, "sort ca") == "sort category"

    def test_layout_cycle(self) -> None:
        st = _state()
        assert _type(st, "layout ") == "layout type"
        assert _tab(st) == "layout type"
        assert _tab(st) == "layout category"

    def test_alias_resolves(self) -> None:
        st = _state()
        assert _type(st, "cat dr") == "cat draw"

    def test_category_at_sigil_kept(self) -> None:
        st = _state()
        assert _type(st, "category @wi") == "category @wincon"

    def test_bang_ignored_for_lookup(self) -> None:
        st = _state()
        assert _type(st, "sort! na") == "sort! name"

    def test_range_prefix_kept(self) -> None:
        st = _state()
        assert _type(st, "%sort qt") == "%sort qty"

    def test_filter_completes_last_term(self) -> None:
        st = _state()
        assert _type(st, "filter ramp+dr") == "filter ramp+draw"
        assert _type(st, "filter ramp|dr") == "filter ramp|draw"
        assert _type(st, "filter ramp -dr") == "filter ramp -draw"
        assert _type(st, "filter @wi") == "filter @wincon"

    def test_complete_word_gives_no_ghost(self) -> None:
        st = _state()
        assert _type(st, "layout type") == ""

    def test_unknown_argument_gives_no_ghost(self) -> None:
        st = _state()
        assert _type(st, "sort zzz") == ""

    def test_command_without_candidates(self) -> None:
        st = _state()
        assert _type(st, "write fo") == ""

    def test_command_names_still_complete(self) -> None:
        st = _state()
        assert _type(st, "lay") == "layout"

    def test_without_arg_source_arguments_are_not_completed(self) -> None:
        completer = CommandCompleter(_registry())
        state = completer.complete("sort ca")
        assert state.matches == ()
        assert state.typed_command == "sort ca"


class TestNewFormatShellCompletion:
    @pytest.fixture
    def ctx(self) -> click.Context:
        from vimtg.cli import new

        return click.Context(new)

    def test_prefix(self, ctx: click.Context) -> None:
        names = [item.value for item in _complete_format(ctx, ctx.command.params[0], "mod")]
        assert names == ["modern"]

    def test_empty_lists_all(self, ctx: click.Context) -> None:
        items = _complete_format(ctx, ctx.command.params[0], "")
        assert [item.value for item in items] == list(known_formats())

    def test_case_insensitive(self, ctx: click.Context) -> None:
        items = _complete_format(ctx, ctx.command.params[0], "COMM")
        assert "commander" in [item.value for item in items]
