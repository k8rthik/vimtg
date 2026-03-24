"""Config screen — modal settings editor with vim-like navigation.

Pushed via :config command. Displays grouped settings with j/k navigation,
h/l/Space cycling, and s to save. Follows the GreeterScreen pattern.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from rich.text import Text
from textual.events import Key
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Static

from vimtg.config.settings import Settings
from vimtg.editor.config_options import (
    cycle_setting,
    get_setting_value,
    groups,
    navigable_options,
    options_for_group,
)
from vimtg.tui.key_translator import translate
from vimtg.tui.theme import COLORS


class ConfigView(Static):
    """Renders the config menu content with Rich Text."""

    settings: reactive[Settings] = reactive(Settings, recompose=False)
    selected_index: reactive[int] = reactive(0)
    unsaved: reactive[bool] = reactive(False)

    def render(self) -> Text:
        t = Text()
        all_options = navigable_options()

        # Title
        t.append("\n")
        title = Text("  vimtg settings\n")
        title.stylize(f"bold {COLORS['mana_blue']}")
        t.append_text(title)
        t.append(f"  {'─' * 40}\n", style=f"dim {COLORS['comment']}")
        t.append("\n")

        # Render grouped options
        option_idx = 0
        for group in groups():
            group_opts = options_for_group(group)
            t.append(f"  {group}\n", style=f"bold {COLORS['mana_red']}")

            for opt in group_opts:
                is_selected = option_idx == self.selected_index
                prefix = "  > " if is_selected else "    "
                value = get_setting_value(self.settings, opt.key)
                label = value if value else "none"

                line = Text()
                if is_selected:
                    line.append(prefix, style=f"bold {COLORS['quantity']}")
                    line.append(f"{opt.display_name:<20}", style="bold")
                else:
                    line.append(prefix, style="")
                    line.append(f"{opt.display_name:<20}", style="")

                # Value with brackets
                val_text = f"[{label}]"
                if is_selected:
                    val_text_obj = Text(val_text, style=f"bold {COLORS['mana_blue']}")
                else:
                    val_text_obj = Text(val_text, style="dim")
                line.append_text(val_text_obj)

                # Show arrows for selected choice/int options
                if is_selected and opt.option_type in ("choice", "int"):
                    line.append("  \u25c4 \u25ba", style=f"dim {COLORS['comment']}")

                line.append("\n")
                t.append_text(line)
                option_idx += 1

            t.append("\n")

        # Footer
        t.append(f"  {'─' * 40}\n", style=f"dim {COLORS['comment']}")

        if self.unsaved:
            t.append("  * unsaved changes\n", style=f"bold {COLORS['mana_red']}")

        hints = Text()
        hints.append("  j", style=f"bold {COLORS['quantity']}")
        hints.append("/", style="dim")
        hints.append("k", style=f"bold {COLORS['quantity']}")
        hints.append(" navigate  ", style="dim")
        hints.append("h", style=f"bold {COLORS['quantity']}")
        hints.append("/", style="dim")
        hints.append("l", style=f"bold {COLORS['quantity']}")
        hints.append(" cycle  ", style="dim")
        hints.append("Space", style=f"bold {COLORS['quantity']}")
        hints.append(" toggle\n", style="dim")
        t.append_text(hints)

        hints2 = Text()
        hints2.append("  s", style=f"bold {COLORS['quantity']}")
        hints2.append(" save  ", style="dim")
        hints2.append("Esc", style=f"bold {COLORS['quantity']}")
        hints2.append("/", style="dim")
        hints2.append("q", style=f"bold {COLORS['quantity']}")
        hints2.append(" close\n", style="dim")
        t.append_text(hints2)

        return t


class ConfigScreen(Screen):
    """Modal config screen, pushed via :config command."""

    CSS = f"""
    ConfigView {{
        height: 1fr;
        content-align: center middle;
        background: {COLORS['bg']};
    }}
    """

    def __init__(
        self,
        settings: Settings,
        on_save: Callable[[Settings], None],
    ) -> None:
        super().__init__()
        self._original = settings
        self._settings = settings
        self._on_save = on_save

    def compose(self):  # noqa: ANN201
        yield ConfigView(id="config-view")

    def on_mount(self) -> None:
        view = self.query_one("#config-view", ConfigView)
        view.settings = self._settings

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+c":
            self.app.exit()
            return
        event.prevent_default()
        event.stop()

        key = translate(event.key)
        view = self.query_one("#config-view", ConfigView)
        all_options = navigable_options()
        max_idx = len(all_options) - 1

        if key == "j":
            view.selected_index = min(view.selected_index + 1, max_idx)
        elif key == "k":
            view.selected_index = max(view.selected_index - 1, 0)
        elif key in ("l", "space", "enter"):
            self._cycle_current(view, all_options, direction=1)
        elif key == "h":
            self._cycle_current(view, all_options, direction=-1)
        elif key == "s":
            self._save_and_close()
        elif key in ("escape", "q"):
            self._close()

    def _cycle_current(self, view: ConfigView, all_options: list, direction: int) -> None:
        if view.selected_index >= len(all_options):
            return
        opt = all_options[view.selected_index]
        self._settings = cycle_setting(self._settings, opt.key, direction)
        view.settings = self._settings
        view.unsaved = self._settings != self._original

    def _save_and_close(self) -> None:
        self._on_save(self._settings)
        self.app.pop_screen()

    def _close(self) -> None:
        self.app.pop_screen()
