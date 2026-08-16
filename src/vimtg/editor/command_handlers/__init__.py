"""Ex-command handler modules — TUI-agnostic, zero Textual imports.

`register_all_commands` is the single place that wires every handler
module into a registry, so a module can't silently go unregistered.
"""

from __future__ import annotations

from vimtg.editor.command_handlers.buffer_cmds import register_buffer_commands
from vimtg.editor.command_handlers.category_cmds import register_category_commands
from vimtg.editor.command_handlers.config_cmds import register_config_commands
from vimtg.editor.command_handlers.deck_cmds import register_deck_commands
from vimtg.editor.command_handlers.export_cmds import register_export_commands
from vimtg.editor.command_handlers.global_cmd import register_global_commands
from vimtg.editor.command_handlers.help_cmd import register_help_commands
from vimtg.editor.command_handlers.history_cmds import register_history_commands
from vimtg.editor.command_handlers.search_cmds import register_search_commands
from vimtg.editor.command_handlers.sort import register_sort_commands
from vimtg.editor.command_handlers.split_cmds import register_split_commands
from vimtg.editor.command_handlers.substitute import register_substitute_commands
from vimtg.editor.command_handlers.tag_cmds import register_tag_commands
from vimtg.editor.commands import CommandRegistry

_REGISTRARS = (
    register_buffer_commands,
    register_sort_commands,
    register_deck_commands,
    register_help_commands,
    register_config_commands,
    register_history_commands,
    register_export_commands,
    register_tag_commands,
    register_category_commands,
    register_search_commands,
    register_substitute_commands,
    register_global_commands,
    register_split_commands,
)


def register_all_commands(registry: CommandRegistry) -> None:
    """Register every command handler module into `registry`."""
    for registrar in _REGISTRARS:
        registrar(registry)
