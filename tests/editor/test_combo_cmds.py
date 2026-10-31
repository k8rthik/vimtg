""":combos / :combo and the Space c key: the request reaches the TUI,
an empty deck or a stray argument is refused on the command line."""

from __future__ import annotations

import pytest

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import CommandRegistry
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult, ParsedAction
from vimtg.editor.keyspec import EDITOR_BINDINGS
from vimtg.editor.modes import ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import EditorState, handle_command, handle_normal_special
from vimtg.services.history_service import HistoryService

DECK = "CMD: 1 Krenko, Mob Boss\n1 Skirk Prospector\n"


@pytest.fixture
def registry() -> CommandRegistry:
    reg = CommandRegistry()
    register_all_commands(reg)
    return reg


def _state(text: str = DECK) -> EditorState:
    buffer = Buffer.from_text(text)
    state = EditorState(
        buffer=buffer,
        cursor=Cursor(),
        mode_mgr=ModeManager(),
        registers=RegisterStore(),
        history=HistoryService(),
        modified=False,
        resolved_cards={},
        settings=Settings(),
    )
    state.history.initialize(buffer)
    return state


@pytest.mark.parametrize("name", ["combos", "combo"])
def test_command_requests_the_overlay(registry: CommandRegistry, name: str) -> None:
    hr = handle_command(_state(), ParsedAction("command_submit", ":", text=name), registry, None)
    assert hr.ui_request == "combos"
    assert not hr.error


def test_commander_only_deck_is_enough(registry: CommandRegistry) -> None:
    state = _state("CMD: 1 Krenko, Mob Boss\n")
    hr = handle_command(state, ParsedAction("command_submit", ":", text="combos"), registry, None)
    assert hr.ui_request == "combos"


def test_deck_without_playable_cards_is_refused(registry: CommandRegistry) -> None:
    state = _state("// Deck: x\nSB: 1 Duress\n")
    hr = handle_command(state, ParsedAction("command_submit", ":", text="combos"), registry, None)
    assert hr.error
    assert hr.ui_request == ""
    assert "No cards in the deck" in hr.command_message


def test_argument_is_refused(registry: CommandRegistry) -> None:
    hr = handle_command(
        _state(), ParsedAction("command_submit", ":", text="combos all"), registry, None,
    )
    assert hr.error
    assert hr.ui_request == ""


def test_leader_c_runs_combos() -> None:
    km = KeyMap()
    assert km.feed(" ")[0] == KeyResult.PENDING
    result, action = km.feed("c")
    assert result == KeyResult.COMPLETE
    assert action is not None and action.action == "space c"
    assert handle_normal_special(_state(), action).run_ex_command == "combos"


def test_leader_c_is_documented_once() -> None:
    rows = [b for b in EDITOR_BINDINGS if "space c" in b.keys]
    assert len(rows) == 1
    assert ":combos" in rows[0].action
