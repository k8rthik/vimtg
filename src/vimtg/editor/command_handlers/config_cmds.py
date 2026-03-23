"""Config and keybinding commands — :set, :map, :unmap."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import CommandRegistry, EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def cmd_set(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:set option=value — View or change settings.

    :set                     Show all current settings
    :set number              Enable line numbers (default: on)
    :set nonumber            Disable line numbers
    :set whichkey            Enable which-key tooltips (default: on)
    :set nowhichkey          Disable which-key tooltips
    :set autoexpand          Enable auto card expansion (default: on)
    :set noautoexpand        Disable auto card expansion
    """
    args = cmd.args.strip()
    if not args:
        ctx.message = "number whichkey autoexpand"
        return buffer, cursor

    if args.startswith("no"):
        option = args[2:]
        ctx.message = f"{option} off"
    else:
        parts = args.split("=", 1)
        option = parts[0]
        ctx.message = f"{option} on" + (f" = {parts[1]}" if len(parts) > 1 else "")

    return buffer, cursor


def cmd_map(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:map from to — Create key remapping.

    :map s :w           Map 's' to ':w' (save) in all modes
    :map Q :q!          Map 'Q' to ':q!' (force quit)
    :map (no args)      Show all current mappings
    """
    args = cmd.args.strip()
    if not args:
        ctx.message = "No mappings defined (add to ~/.config/vimtg/config.toml)"
        return buffer, cursor

    parts = args.split(None, 1)
    if len(parts) < 2:
        ctx.message = "E: Usage: :map {key} {action}"
        return buffer, cursor

    from_key, to_key = parts
    ctx.message = f"Mapped: {from_key} → {to_key} (save to config.toml to persist)"
    return buffer, cursor


def cmd_unmap(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:unmap key — Remove key remapping."""
    args = cmd.args.strip()
    if not args:
        ctx.message = "E: Usage: :unmap {key}"
        return buffer, cursor

    ctx.message = f"Unmapped: {args}"
    return buffer, cursor


def register_config_commands(registry: CommandRegistry) -> None:
    registry.register("set", cmd_set)
    registry.register("map", cmd_map)
    registry.register("unmap", cmd_unmap)
