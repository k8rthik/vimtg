"""Tests for :vsplit / :split / :close / :edhrec command handlers."""

from __future__ import annotations

from pathlib import Path

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    parse_command,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.splits import SplitDirection, resolve_deck_path


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


class TestSplitCommands:
    def test_vsplit_requires_argument(self):
        ctx = _run("vsplit")
        assert ctx.error
        assert "Usage" in ctx.message

    def test_vsplit_missing_file_fails(self, tmp_path: Path):
        ctx = _run(f"vsplit {tmp_path}/nope.deck")
        assert ctx.error
        assert "not found" in ctx.message

    def test_vsplit_opens_vertical(self, tmp_path: Path):
        other = tmp_path / "other.deck"
        other.write_text("4 Opt\n")
        ctx = _run(f"vsplit {other}")
        assert not ctx.error
        assert ctx.split_open is not None
        assert ctx.split_open.direction is SplitDirection.VERTICAL
        assert ctx.split_open.path == other

    def test_split_opens_horizontal(self, tmp_path: Path):
        other = tmp_path / "other.deck"
        other.write_text("4 Opt\n")
        ctx = _run(f"split {other}")
        assert ctx.split_open is not None
        assert ctx.split_open.direction is SplitDirection.HORIZONTAL

    def test_relative_path_resolves_against_deck_dir(self, tmp_path: Path):
        (tmp_path / "other.deck").write_text("4 Opt\n")
        current = tmp_path / "mine.deck"
        ctx = _run("vsplit other.deck", file_path=current)
        assert ctx.split_open is not None
        assert ctx.split_open.path == tmp_path / "other.deck"

    def test_close_sets_flag(self):
        ctx = _run("close")
        assert ctx.split_close

    def test_only_is_close_alias(self):
        ctx = _run("only")
        assert ctx.split_close


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


class TestResolveDeckPath:
    def test_absolute_path(self, tmp_path: Path):
        deck = tmp_path / "a.deck"
        deck.write_text("x")
        assert resolve_deck_path(str(deck), None) == deck

    def test_absolute_missing_returns_none(self, tmp_path: Path):
        assert resolve_deck_path(str(tmp_path / "no.deck"), None) is None

    def test_relative_falls_back_to_cwd(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "b.deck").write_text("x")
        assert resolve_deck_path("b.deck", None) == tmp_path / "b.deck"


class TestAnalyticsCommand:
    def test_analytics_sets_open_request(self):
        ctx = _run("analytics")
        assert not ctx.error
        assert ctx.analytics_open is not None
        assert ctx.analytics_open.direction is SplitDirection.VERTICAL

    def test_ana_alias(self):
        ctx = _run("ana")
        assert ctx.analytics_open is not None
