"""Tests for :set and :config command handlers."""

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.config_cmds import (
    cmd_config,
    cmd_map,
    cmd_set,
    cmd_unmap,
    register_config_commands,
)
from vimtg.editor.commands import CommandRegistry, EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor

_BUF = Buffer.from_text("test\n")


def _make_ctx(settings: Settings | None = None) -> EditorContext:
    return EditorContext(settings=settings or Settings())


class TestCmdSet:
    def test_no_args_lists_settings(self) -> None:
        buf = Buffer.from_text("test\n")
        ctx = _make_ctx()
        cmd_set(buf, Cursor(), ParsedCommand(name="set"), ctx)
        assert ctx.message  # Non-empty list of settings
        assert "Price Source" in ctx.message

    def test_set_key_value(self) -> None:
        ctx = _make_ctx()
        cmd_set(
            Buffer.from_text("test\n"), Cursor(),
            ParsedCommand(name="set", args="price_source=eur"), ctx,
        )
        assert ctx.settings_changed is True
        assert ctx.settings.price_source == "eur"
        assert "price_source" in ctx.message

    def test_set_bool_enable(self) -> None:
        ctx = _make_ctx(Settings(show_which_key=False))
        cmd_set(
            Buffer.from_text("test\n"), Cursor(),
            ParsedCommand(name="set", args="whichkey"), ctx,
        )
        assert ctx.settings_changed is True
        assert ctx.settings.show_which_key is True

    def test_set_bool_disable_no_prefix(self) -> None:
        ctx = _make_ctx()
        cmd_set(
            Buffer.from_text("test\n"), Cursor(),
            ParsedCommand(name="set", args="nowhichkey"), ctx,
        )
        assert ctx.settings_changed is True
        assert ctx.settings.show_which_key is False

    def test_set_invalid_value(self) -> None:
        ctx = _make_ctx()
        cmd_set(
            Buffer.from_text("test\n"), Cursor(),
            ParsedCommand(name="set", args="price_source=cardkingdom"), ctx,
        )
        assert ctx.settings_changed is False
        assert "E:" in ctx.message

    def test_set_no_settings_available(self) -> None:
        ctx = EditorContext()  # No settings
        cmd_set(
            Buffer.from_text("test\n"), Cursor(),
            ParsedCommand(name="set"), ctx,
        )
        assert "E:" in ctx.message

    def test_original_settings_unchanged(self) -> None:
        original = Settings()
        ctx = _make_ctx(original)
        cmd_set(
            Buffer.from_text("test\n"), Cursor(),
            ParsedCommand(name="set", args="price_source=tix"), ctx,
        )
        assert original.price_source == "usd"  # Immutable


class TestCmdConfig:
    def test_opens_config_screen(self) -> None:
        ctx = _make_ctx()
        cmd_config(
            Buffer.from_text("test\n"), Cursor(),
            ParsedCommand(name="config"), ctx,
        )
        assert ctx.open_config_screen is True


class TestCmdSetNoPrefixInvalid:
    def test_no_prefix_unknown_key_reports_error(self) -> None:
        ctx = _make_ctx()
        cmd_set(_BUF, Cursor(), ParsedCommand(name="set", args="nobogus"), ctx)
        assert ctx.message.startswith("E:")


class TestCmdMap:
    def test_no_args_shows_hint(self) -> None:
        ctx = _make_ctx()
        cmd_map(_BUF, Cursor(), ParsedCommand(name="map"), ctx)
        assert "No mappings" in ctx.message

    def test_missing_action_reports_usage(self) -> None:
        ctx = _make_ctx()
        cmd_map(_BUF, Cursor(), ParsedCommand(name="map", args="s"), ctx)
        assert "Usage" in ctx.message

    def test_valid_mapping(self) -> None:
        ctx = _make_ctx()
        cmd_map(_BUF, Cursor(), ParsedCommand(name="map", args="s :w"), ctx)
        assert "Mapped" in ctx.message
        assert "s" in ctx.message


class TestCmdUnmap:
    def test_no_args_reports_usage(self) -> None:
        ctx = _make_ctx()
        cmd_unmap(_BUF, Cursor(), ParsedCommand(name="unmap"), ctx)
        assert "Usage" in ctx.message

    def test_valid_unmap(self) -> None:
        ctx = _make_ctx()
        cmd_unmap(_BUF, Cursor(), ParsedCommand(name="unmap", args="Q"), ctx)
        assert "Unmapped: Q" in ctx.message


class TestRegisterConfigCommands:
    def test_registers_all_commands(self) -> None:
        registry = CommandRegistry()
        register_config_commands(registry)
        for name in ("set", "config", "map", "unmap", "settings", "preferences"):
            ctx = _make_ctx()
            registry.execute(ParsedCommand(name=name), _BUF, Cursor(), ctx)
            assert not ctx.error, f"{name} should be registered"
