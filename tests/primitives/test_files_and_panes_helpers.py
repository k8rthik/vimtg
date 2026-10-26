"""Helpers shared by the files-and-panes primitive cases (no cases here).

`Ed.press` feeds MainScreen._process_key, which is the editor's key path
but not the whole terminal path: F1, the g? cheat sheet's close keys,
Esc hiding the tips, Ctrl-Q, and every key typed into an overlay are
handled in `on_key` handlers or app bindings above it. Those cases send
the key through Textual's Pilot instead, as a terminal would.
"""

from __future__ import annotations

from textual.pilot import Pilot

from tests.primitives.harness import Ed
from vimtg.tui.screens.main_screen import MainScreen

# A legal modern deck: 60 cards in the mainboard, a 2-card sideboard.
LEGAL_MODERN = (
    "// Deck: Burn\n// Format: modern\n\n"
    "DCK:\n"
    "    4 Goblin Guide\n"
    "    4 Eidolon of the Great Revel\n"
    "    4 Bonecrusher Giant // Stomp\n"
    "    4 Lightning Bolt\n"
    "    4 Lava Spike\n"
    "    4 Fire // Ice\n"
    "    4 Sacred Foundry\n"
    "    32 Mountain\n"
    "\n"
    "SB:\n"
    "    2 Rest in Peace\n"
)

# A Commander deck: the EDHREC pane needs a CMD: line.
COMMANDER_DECK = (
    "// Deck: Guide\n// Format: commander\n\n"
    "CMD:\n"
    "    1 Goblin Guide\n"
    "\n"
    "DCK:\n"
    "    1 Lightning Bolt\n"
    "    1 Mountain\n"
)


def ex(command: str) -> str:
    """':' + command + Enter, in Ed.press notation (spaces typed as <Space>)."""
    return ":" + command.replace(" ", "<Space>") + "<CR>"


async def settle(ed: Ed) -> Pilot[object]:
    """Let pushed screens mount and posted messages run; returns a Pilot."""
    pilot: Pilot[object] = Pilot(ed.app)
    await pilot.pause()
    await pilot.pause()
    return pilot


async def keys(ed: Ed, *names: str) -> None:
    """Send Textual key names through the app, as a terminal would."""
    pilot = await settle(ed)
    for name in names:
        await pilot.press(name)
        await pilot.pause()
    await pilot.pause()


def in_editor(ed: Ed) -> bool:
    return isinstance(ed.app.screen, MainScreen)


def overlay_title(ed: Ed) -> str:
    """The top-border title of the floating window on top."""
    window = ed.app.screen.window  # type: ignore[attr-defined]
    return str(window.border_title).strip()


def shown(ed: Ed, selector: str) -> str:
    """The plain text a widget of the top screen shows."""
    return str(ed.app.screen.query_one(selector).render())


async def app_ended(ed: Ed) -> bool:
    """True once the app stopped running (it ended the session)."""
    await settle(ed)
    return not ed.app.is_running
