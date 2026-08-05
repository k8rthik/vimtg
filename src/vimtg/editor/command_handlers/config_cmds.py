"""Config and keybinding commands — :set, :config, :map, :unmap."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import CommandRegistry, EditorContext, ParsedCommand
from vimtg.editor.config_options import (
    CONFIG_OPTIONS,
    apply_setting,
    get_setting_display,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.modes import Mode

# Map vim-style shorthand names to Settings field names
_BOOL_ALIASES: dict[str, str] = {
    "number": "show_line_numbers",
    "whichkey": "show_which_key",
    "autoexpand": "auto_expand",
    "autosort": "auto_sort",
    "prices": "show_prices",
    "confirmquit": "confirm_quit",
}


def cmd_set(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:set option=value — View or change settings.

    :set                         Show all current settings
    :set number / :set nonumber  Toggle line numbers
    :set price_source=eur        Set price source
    :set search_limit=100        Set search limit
    """
    if ctx.settings is None:
        ctx.fail("Settings not available")
        return buffer, cursor

    args = cmd.args.strip()
    if not args:
        parts = [get_setting_display(ctx.settings, o.key) for o in CONFIG_OPTIONS]
        ctx.message = "  ".join(parts)
        return buffer, cursor

    # Handle "no" prefix for bool toggles: :set nonumber
    if args.startswith("no"):
        alias = args[2:]
        key = _BOOL_ALIASES.get(alias, alias)
        try:
            ctx.settings = apply_setting(ctx.settings, key, "off")
            ctx.settings_changed = True
            ctx.message = f"{key} = off"
        except ValueError as e:
            ctx.fail(str(e))
        return buffer, cursor

    # Handle key=value syntax: :set price_source=eur
    if "=" in args:
        key, value = args.split("=", 1)
        key = key.strip()
        value = value.strip()
    else:
        # Bool enable shorthand: :set number
        alias = args.strip()
        key = _BOOL_ALIASES.get(alias, alias)
        value = "on"

    try:
        ctx.settings = apply_setting(ctx.settings, key, value)
        ctx.settings_changed = True
        ctx.message = f"{key} = {value}"
    except ValueError as e:
        ctx.fail(str(e))

    return buffer, cursor


def cmd_config(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:config — Open the configuration menu."""
    ctx.open_config_screen = True
    return buffer, cursor


def cmd_map(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:map from to — Create a NORMAL-mode key remapping for this session.

    :map s :w           Map 's' to ':w' (save)
    :map Q :q!          Map 'Q' to ':q!' (force quit)
    :map (no args)      Show all current mappings

    Mappings made here last for the session; add them to
    ~/.config/vimtg/config.toml [keybindings] to persist.
    """
    if ctx.remapper is None:
        ctx.fail("Key remapping not available")
        return buffer, cursor

    args = cmd.args.strip()
    if not args:
        pairs = sorted(
            {(m.from_key, m.to_key) for m in ctx.remapper.get_mappings()}
        )
        if not pairs:
            ctx.message = "No mappings defined"
        else:
            ctx.message = "  ".join(f"{f} → {t}" for f, t in pairs)
        return buffer, cursor

    parts = args.split(None, 1)
    if len(parts) < 2:
        ctx.fail("Usage: :map {key} {action}")
        return buffer, cursor

    from_key, to_key = parts
    ctx.remapper.remap(from_key, to_key.strip(), Mode.NORMAL)
    ctx.message = f"Mapped: {from_key} → {to_key} (config.toml to persist)"
    return buffer, cursor


def cmd_unmap(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:unmap key — Remove a key remapping (all modes)."""
    if ctx.remapper is None:
        ctx.fail("Key remapping not available")
        return buffer, cursor

    args = cmd.args.strip()
    if not args:
        ctx.fail("Usage: :unmap {key}")
        return buffer, cursor

    if not any(m.from_key == args for m in ctx.remapper.get_mappings()):
        ctx.fail(f"No mapping for: {args}")
        return buffer, cursor

    ctx.remapper.unmap(args)
    ctx.message = f"Unmapped: {args}"
    return buffer, cursor


def register_config_commands(registry: CommandRegistry) -> None:
    registry.register("set", cmd_set)
    registry.register("config", cmd_config, aliases=["settings", "preferences"])
    registry.register("map", cmd_map)
    registry.register("unmap", cmd_unmap)
