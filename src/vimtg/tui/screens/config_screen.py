"""Config screen — modal settings editor with vim-like navigation.

Pushed via :config command. Displays grouped settings with the shared
navigation keys (j/k, gg/G, Ctrl-D/U, wheel), h/l/Space/Enter cycling,
s to save, and q/Esc to close (guarded when unsaved).
"""

from __future__ import annotations

from collections.abc import Callable

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.events import Key
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Static

from vimtg.config.settings import Settings
from vimtg.editor.config_options import (
    ConfigOption,
    cycle_setting,
    get_setting_value,
    groups,
    navigable_options,
    options_for_group,
)
from vimtg.tui.key_translator import translate
from vimtg.tui.keys import CLOSE_KEYS, FULL_HELP_KEY, HELP_KEY, PENDING, VimNav, render_hints
from vimtg.tui.theme import COLORS

HINTS = (
    ("j/k", "navigate"), ("gg/G", "top/bottom"), ("h/l", "cycle"),
    ("Space/Enter", "cycle"), ("s", "save"), ("q/Esc", "close"), ("?", "help"),
)


class ConfigView(Static):
    """Renders the config menu content with Rich Text."""

    settings: reactive[Settings] = reactive(Settings, recompose=False)
    selected_index: reactive[int] = reactive(0)
    unsaved: reactive[bool] = reactive(False)
    warning: reactive[str] = reactive("")

    def render(self) -> Text:
        t = Text()

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

        if self.warning:
            t.append(f"  {self.warning}\n", style=f"bold {COLORS['error']}")
        elif self.unsaved:
            t.append("  * unsaved changes\n", style=f"bold {COLORS['error']}")

        t.append_text(render_hints(HINTS, self.size.width, leading="  "))
        t.append("\n")
        return t

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        self.selected_index = min(self.selected_index + 1, len(navigable_options()) - 1)

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        self.selected_index = max(self.selected_index - 1, 0)


class ConfigScreen(Screen[None]):
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
        self._discard_armed = False  # first q with unsaved changes warns
        self._nav = VimNav()

    def compose(self) -> ComposeResult:
        yield ConfigView(id="config-view")

    def on_mount(self) -> None:
        view = self.query_one("#config-view", ConfigView)
        view.settings = self._settings

    def on_key(self, event: Key) -> None:
        event.prevent_default()
        event.stop()

        key = translate(event.key)
        view = self.query_one("#config-view", ConfigView)
        all_options = navigable_options()
        max_idx = len(all_options) - 1
        # Ctrl-C closes like q, so unsaved changes still get their warning
        if key == "ctrl_c":
            key = "q"

        if key not in CLOSE_KEYS and self._discard_armed:
            self._discard_armed = False
            view.warning = ""

        step = self._nav.feed(key, max(1, max_idx + 1))
        if step == PENDING:
            return
        if step == "home":
            view.selected_index = 0
        elif step == "end":
            view.selected_index = max_idx
        elif step is not None:
            view.selected_index = max(0, min(view.selected_index + int(step), max_idx))
        elif key in ("l", " ", "enter"):  # translate() maps Space to " "
            self._cycle_current(view, all_options, direction=1)
        elif key == "h":
            self._cycle_current(view, all_options, direction=-1)
        elif key == "s":
            self._save_and_close()
        elif key in CLOSE_KEYS:
            self._close(view)
        elif key in (HELP_KEY, FULL_HELP_KEY):
            from vimtg.tui.screens.help_screen import HelpScreen

            self.app.push_screen(HelpScreen(topic="config" if key == HELP_KEY else None))

    def _cycle_current(
        self, view: ConfigView, all_options: list[ConfigOption], direction: int
    ) -> None:
        if view.selected_index >= len(all_options):
            return
        opt = all_options[view.selected_index]
        self._settings = cycle_setting(self._settings, opt.key, direction)
        view.settings = self._settings
        view.unsaved = self._settings != self._original

    def _save_and_close(self) -> None:
        self._on_save(self._settings)
        self.app.pop_screen()

    def _close(self, view: ConfigView) -> None:
        """Close, but warn once before discarding unsaved changes."""
        if view.unsaved and not self._discard_armed:
            self._discard_armed = True
            view.warning = "Unsaved changes — press q again to discard, s to save"
            return
        self.app.pop_screen()
