""":hand / :goldfish and the Space h key: argument parsing, the library the
request carries (plan, commander, settings format), and the wiring from
ex command to HandlerResult."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from vimtg.config.settings import Settings
from vimtg.domain.card import Card
from vimtg.domain.card_names import CardMap
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.command_handlers.hand_cmds import HandOpen, parse_seed
from vimtg.editor.commands import CommandRegistry, EditorContext, parse_command
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult, ParsedAction
from vimtg.editor.keyspec import EDITOR_BINDINGS
from vimtg.editor.modes import ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import (
    EditorState,
    handle_command,
    handle_normal_special,
)
from vimtg.services.history_service import HistoryService

FIXTURES = Path(__file__).parent.parent / "fixtures"

DECK = """\
// Deck: Burn
// Format: modern

DCK:
4 Goblin Guide
4 Sacred Foundry
16 Mountain

SB: 4 Skullcrack

VS: Tron
    -4 Goblin Guide
    +4 Skullcrack
"""


@pytest.fixture
def registry() -> CommandRegistry:
    reg = CommandRegistry()
    register_all_commands(reg)
    return reg


def _run(
    registry: CommandRegistry, line: str, text: str = DECK, **ctx_kwargs: object
) -> EditorContext:
    buffer = Buffer.from_text(text)
    ctx = EditorContext(**ctx_kwargs)  # type: ignore[arg-type]
    cmd = parse_command(line, 0, buffer.line_count())
    registry.execute(cmd, buffer, Cursor(), ctx)
    return ctx


class TestParseSeed:
    @pytest.mark.parametrize(
        ("args", "seed"),
        [("", None), ("  ", None), ("seed=42", 42), ("SEED = 7", 7), ("42", 42), ("-3", -3)],
    )
    def test_valid(self, args: str, seed: int | None) -> None:
        assert parse_seed(args) == seed

    @pytest.mark.parametrize("args", ["seed=", "seed=abc", "abc", "foo=1", "1.5"])
    def test_invalid(self, args: str) -> None:
        with pytest.raises(ValueError):
            parse_seed(args)


class TestHandCommand:
    def test_requests_overlay(self, registry: CommandRegistry) -> None:
        ctx = _run(registry, "hand")
        assert not ctx.error
        req = ctx.hand_open
        assert isinstance(req, HandOpen)
        assert req.seed is None
        assert Counter(req.source.library) == {
            "Goblin Guide": 4, "Sacred Foundry": 4, "Mountain": 16,
        }
        assert req.source.plan == ""

    def test_goldfish_alias_and_seed(self, registry: CommandRegistry) -> None:
        ctx = _run(registry, "goldfish seed=42")
        assert isinstance(ctx.hand_open, HandOpen)
        assert ctx.hand_open.seed == 42

    def test_bad_argument_fails(self, registry: CommandRegistry) -> None:
        ctx = _run(registry, "hand banana")
        assert ctx.error
        assert "Usage: :hand [seed=N]" in ctx.message
        assert ctx.hand_open is None

    def test_empty_main_deck_fails(self, registry: CommandRegistry) -> None:
        ctx = _run(registry, "hand", text="// Deck: Empty\nSB: 4 Duress\n")
        assert ctx.error
        assert "No cards in the main deck" in ctx.message
        assert ctx.hand_open is None

    def test_active_plan_boards_the_deck(self, registry: CommandRegistry) -> None:
        ctx = _run(registry, "hand", active_plan="tron")
        assert isinstance(ctx.hand_open, HandOpen)
        counts = Counter(ctx.hand_open.source.library)
        assert counts["Skullcrack"] == 4
        assert "Goblin Guide" not in counts
        assert ctx.hand_open.source.plan == "Tron"

    def test_unknown_active_plan_uses_main_deck(self, registry: CommandRegistry) -> None:
        ctx = _run(registry, "hand", active_plan="nope")
        assert isinstance(ctx.hand_open, HandOpen)
        assert "Goblin Guide" in ctx.hand_open.source.library

    def test_commander_from_settings_default_format(
        self, registry: CommandRegistry
    ) -> None:
        text = "CMD: 1 Atraxa, Praetors' Voice\nDCK:\n99 Forest\n"
        ctx = _run(
            registry, "hand", text=text,
            settings=Settings(default_format="commander"),
        )
        assert isinstance(ctx.hand_open, HandOpen)
        src = ctx.hand_open.source
        assert src.command_zone == ("Atraxa, Praetors' Voice",)
        assert len(src.library) == 99
        assert src.free_mulligan

    def test_resolved_cards_give_lands_and_costs(self, registry: CommandRegistry) -> None:
        with open(FIXTURES / "scryfall_sample.json", encoding="utf-8") as f:
            cards = CardMap((c.name, c) for c in map(Card.from_scryfall, json.load(f)))
        ctx = _run(registry, "hand", resolved_cards=cards)
        assert isinstance(ctx.hand_open, HandOpen)
        assert ctx.hand_open.source.lands == {"Sacred Foundry", "Mountain"}
        assert ctx.hand_open.mana_costs["Goblin Guide"] == "{R}"
        assert "Mountain" not in ctx.hand_open.mana_costs  # lands have no cost


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


class TestWiring:
    def test_ex_command_reaches_handler_result(self, registry: CommandRegistry) -> None:
        state = _state()
        state.active_plan = "Tron"
        action = ParsedAction("command_submit", ":", text="hand seed=3")
        hr = handle_command(state, action, registry, None)
        assert isinstance(hr.hand_open, HandOpen)
        assert hr.hand_open.seed == 3
        assert hr.hand_open.source.plan == "Tron"
        assert not state.modified

    def test_leader_h_runs_hand(self) -> None:
        km = KeyMap()
        assert km.feed(" ")[0] == KeyResult.PENDING
        result, action = km.feed("h")
        assert result == KeyResult.COMPLETE
        assert action is not None and action.action == "space h"
        hr = handle_normal_special(_state(), action)
        assert hr.run_ex_command == "hand"

    def test_leader_h_is_documented_once(self) -> None:
        rows = [b for b in EDITOR_BINDINGS if "space h" in b.keys]
        assert len(rows) == 1
        assert ":hand" in rows[0].action
