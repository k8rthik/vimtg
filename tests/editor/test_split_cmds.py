"""Tests for the :close / :edhrec / :analytics pane command handlers."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    parse_command,
)
from vimtg.editor.cursor import Cursor


def _run(
    line: str,
    buffer_text: str = "4 Lightning Bolt\n",
    file_path: Path | None = None,
    settings: Settings | None = None,
) -> EditorContext:
    registry = CommandRegistry()
    register_all_commands(registry)
    buffer = Buffer.from_text(buffer_text)
    ctx = EditorContext(
        file_path=file_path, settings=settings or Settings()
    )
    cmd = parse_command(line, 0, buffer.line_count())
    registry.execute(cmd, buffer, Cursor(), ctx)
    return ctx


_COMMANDER_DECK = (
    "// Format: commander\n"
    "CMD: 1 Atraxa, Praetors' Voice\n"
    "99 Forest\n"
)


class TestCloseCommand:
    def test_close_sets_flag(self):
        ctx = _run("close")
        assert ctx.split_close

    @pytest.mark.parametrize(
        "line",
        ["vsplit other.deck", "vsp x", "vs x", "split other.deck", "sp x", "hsplit x", "only"],
    )
    def test_second_deck_commands_are_gone(self, line: str):
        ctx = _run(line)
        assert ctx.error
        assert ctx.message == f"E492: Not an editor command: {line}"


class TestEdhrecCommand:
    def test_requires_commander_line(self):
        ctx = _run("edhrec", buffer_text="// Format: commander\n99 Forest\n")
        assert ctx.error
        assert "No commander" in ctx.message

    def test_rejects_non_commander_format(self):
        ctx = _run(
            "edhrec",
            buffer_text="// Format: modern\nCMD: 1 Atraxa\n59 Forest\n",
        )
        assert ctx.error
        assert "Commander-only" in ctx.message

    def test_opens_with_commander_names(self):
        ctx = _run("edhrec", buffer_text=_COMMANDER_DECK)
        assert not ctx.error
        assert ctx.edhrec_open is not None
        assert ctx.edhrec_open.commanders == ("Atraxa, Praetors' Voice",)

    def test_partners_both_included(self):
        deck = (
            "// Format: commander\n"
            "CMD: 1 Thrasios, Triton Hero\n"
            "CMD: 1 Tymna the Weaver\n"
            "98 Forest\n"
        )
        ctx = _run("edhrec", buffer_text=deck)
        assert ctx.edhrec_open is not None
        assert ctx.edhrec_open.commanders == (
            "Thrasios, Triton Hero", "Tymna the Weaver",
        )

    def test_no_declared_format_with_cmd_line_is_allowed(self):
        ctx = _run("edhrec", buffer_text="CMD: 1 Atraxa\n99 Forest\n")
        assert not ctx.error
        assert ctx.edhrec_open is not None

    def test_default_format_setting_applies(self):
        settings = Settings(default_format="modern")
        ctx = _run(
            "edhrec",
            buffer_text="CMD: 1 Atraxa\n99 Forest\n",
            settings=settings,
        )
        assert ctx.error

    def test_tab_argument_selects_tab(self):
        ctx = _run("edhrec creatures", buffer_text=_COMMANDER_DECK)
        assert ctx.edhrec_open is not None
        assert ctx.edhrec_open.initial_tab == "Creatures"

    def test_unknown_tab_argument_fails(self):
        ctx = _run("edhrec vehicles", buffer_text=_COMMANDER_DECK)
        assert ctx.error
        assert "Unknown card type" in ctx.message

    def test_rec_alias(self):
        ctx = _run("rec", buffer_text=_COMMANDER_DECK)
        assert ctx.edhrec_open is not None


class TestAnalyticsCommand:
    def test_analytics_sets_open_request(self):
        ctx = _run("analytics")
        assert not ctx.error
        assert ctx.analytics_open is True

    def test_ana_alias(self):
        ctx = _run("ana")
        assert ctx.analytics_open is True
