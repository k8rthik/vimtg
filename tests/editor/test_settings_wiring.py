"""Settings must actually change behavior — not just persist.

Regression tests for a class of bug where options were editable in the
config screen but read by nothing.
"""

from __future__ import annotations

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.buffer_cmds import cmd_quit
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor
from vimtg.domain.card import Card
from vimtg.tui.deck_renderer import render_line


def _card(name: str = "Lightning Bolt") -> Card:
    return Card.from_scryfall(
        {
            "id": "x",
            "name": name,
            "mana_cost": "{R}",
            "cmc": 1.0,
            "type_line": "Instant",
            "oracle_text": "Deal 3 damage to any target.",
        }
    )


class TestConfirmQuit:
    def test_modified_quit_blocked_by_default(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        ctx = EditorContext(modified=True, settings=Settings())
        cmd_quit(buf, Cursor(), ParsedCommand(name="q"), ctx)
        assert ctx.error
        assert not ctx.quit_requested

    def test_confirm_quit_off_allows_quit(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        ctx = EditorContext(
            modified=True, settings=Settings(confirm_quit=False)
        )
        cmd_quit(buf, Cursor(), ParsedCommand(name="q"), ctx)
        assert ctx.quit_requested


class TestRendererSettings:
    def test_auto_expand_off_suppresses_expansion(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        card = _card()
        resolved = {"Lightning Bolt": card}
        expanded = render_line(0, buf, 0, resolved, auto_expand=True)
        collapsed = render_line(0, buf, 0, resolved, auto_expand=False)
        assert len(expanded) > 1
        assert len(collapsed) == 1

    def test_show_line_numbers_off_removes_gutter(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n2 Goblin Guide\n")
        with_numbers = render_line(1, buf, 0, {}, show_line_numbers=True)
        without = render_line(1, buf, 0, {}, show_line_numbers=False)
        assert with_numbers[0].plain != without[0].plain
