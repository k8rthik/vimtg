"""Input slice: :map, :unmap, :set and :messages.

Expected values come from docs/commands.md (Configuration, Help),
docs/keybindings.md (Remapping) and the README's Configuration table.
:set is checked through config.toml, which the spec says it writes, and
through an effect the option has in the editor where one is cheap to see.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from textual.pilot import Pilot
from textual.widgets import Static

from tests.primitives.harness import DECK, Ed, editor
from vimtg.config.paths import config_dir
from vimtg.editor.modes import Mode
from vimtg.tui.screens.main_screen import MainScreen


def ex(ed: Ed, command: str) -> Ed:
    """Run `:command<CR>`; spaces in the command are typed as spaces."""
    return ed.press(":" + command.replace(" ", "<Space>") + "<CR>")


def config_file() -> Path:
    return config_dir() / "config.toml"


def editor_config() -> dict[str, object]:
    if not config_file().exists():
        return {}
    data = tomllib.loads(config_file().read_text(encoding="utf-8"))
    section = data.get("editor", {})
    assert isinstance(section, dict)
    return section


def press_named(ed: Ed, key: str) -> None:
    """Press a canonical key the harness notation has no name for
    (e.g. 'ctrl_s'), through the same path Ed.press uses."""
    def reraise(exc: Exception) -> None:
        raise exc

    ed.screen.recover_from_crash = reraise  # type: ignore[method-assign]
    ed.screen._process_key(key)


async def messages_window(ed: Ed) -> str:
    """Run :messages and return the text of the window it opens."""
    ex(ed, "messages")
    pilot = Pilot(ed.app)
    await pilot.pause()
    screen = ed.app.screen
    assert not isinstance(screen, MainScreen), ":messages opened no window"
    body = str(screen.query_one("#help-body", Static).render())
    await pilot.press("q")
    await pilot.pause()
    assert isinstance(ed.app.screen, MainScreen)
    return body


CREATURES_BY_NAME = [
    "3 Bonecrusher Giant // Stomp", "2 Eidolon of the Great Revel", "4 Goblin Guide",
]


# ── :map ─────────────────────────────────────────────────────────


@pytest.mark.primitive(":map")
@pytest.mark.asyncio
async def test_map_remaps_a_key_to_a_motion(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "map ; j")
        assert not ed.is_error
        ed.press("8G ;")
        assert ed.row == 8


@pytest.mark.primitive(":map")
@pytest.mark.asyncio
async def test_map_types_a_multi_key_action_key_by_key(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "map ; dd")
        ed.press("8G ;")
        assert ed.text == DECK.replace("    4 Goblin Guide\n", "")


@pytest.mark.primitive(":map")
@pytest.mark.asyncio
async def test_map_to_a_colon_action_runs_the_command(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "map ; :13")
        ed.press("8G ;")
        assert ed.row == 12
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive(":map")
@pytest.mark.asyncio
async def test_map_ctrl_s_which_is_free_to_map(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "map ctrl_s :13")
        ed.press("8G")
        press_named(ed, "ctrl_s")
        assert ed.row == 12


@pytest.mark.primitive(":map")
@pytest.mark.asyncio
async def test_map_applies_only_where_a_command_starts(tmp_path: Path) -> None:
    # keybindings.md: "a mapping applies only where a command starts:
    # mapping s leaves zs and "s alone"
    async with editor(tmp_path) as ed:
        ex(ed, "map a j")
        ed.press('8G "ayy')
        assert [line.strip() for line in ed.register("a")] == ["4 Goblin Guide"]
        assert ed.row == 7
        assert ed.text == DECK


@pytest.mark.primitive(":map")
@pytest.mark.xfail(
    strict=True,
    reason=(
        "DOC: keybindings.md Remapping says both that a mapping applies only where a "
        "command starts (s leaves \"s alone) and that it rewrites its key everywhere, "
        "including \"s; the editor does the former"
    ),
)
@pytest.mark.asyncio
async def test_map_rewrites_the_key_inside_a_register_name(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "map a b")
        ed.press('8G "ayy')
        assert [line.strip() for line in ed.register("b")] == ["4 Goblin Guide"]


@pytest.mark.primitive(":map")
@pytest.mark.asyncio
async def test_bare_map_lists_the_mappings(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "map ; :13")
        ex(ed, "map")
        assert ";" in ed.message
        assert ":13" in ed.message


@pytest.mark.primitive(":map")
@pytest.mark.asyncio
async def test_map_of_more_than_one_key_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "map ab j")
        assert ed.is_error
        ex(ed, "map")
        assert "ab" not in ed.message


@pytest.mark.primitive(":map")
@pytest.mark.asyncio
async def test_map_lasts_only_for_the_session(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "map ; j")
    async with editor(tmp_path, cards=False) as ed:
        ed.press("8G ;")
        assert ed.row == 7


@pytest.mark.primitive(":map")
@pytest.mark.asyncio
async def test_maps_in_config_toml_load_at_start(tmp_path: Path) -> None:
    config_file().write_text('[keybindings.normal]\n";" = "j"\n', encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press("8G ;")
        assert ed.row == 8


@pytest.mark.primitive(":map")
@pytest.mark.asyncio
async def test_map_changes_nothing_in_the_buffer(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "map ; dd")
        assert ed.text == DECK
        assert ed.modified is False


# ── :unmap ───────────────────────────────────────────────────────


@pytest.mark.primitive(":unmap", ":map")
@pytest.mark.asyncio
async def test_unmap_restores_the_key(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "map j k")
        ex(ed, "unmap j")
        assert not ed.is_error
        ed.press("8G j")
        assert ed.row == 8


@pytest.mark.primitive(":unmap", ":map")
@pytest.mark.asyncio
async def test_unmap_leaves_a_free_key_unbound(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "map ; dd")
        ex(ed, "unmap ;")
        ed.press("8G ;")
        assert ed.text == DECK
        assert ed.row == 7


@pytest.mark.primitive(":unmap", ":map")
@pytest.mark.asyncio
async def test_unmap_drops_the_key_from_the_listing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "map ; :13")
        ex(ed, "unmap ;")
        ex(ed, "map")
        assert ":13" not in ed.message


@pytest.mark.primitive(":unmap")
@pytest.mark.asyncio
async def test_unmap_of_an_unmapped_key_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "unmap ;")
        assert ed.is_error
        assert ed.text == DECK


@pytest.mark.primitive(":unmap")
@pytest.mark.asyncio
async def test_unmap_with_no_key_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "unmap")
        assert ed.is_error


# ── :set ─────────────────────────────────────────────────────────


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_no_bool_turns_it_off_and_saves_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "set nonumber")
        assert not ed.is_error
        assert editor_config()["show_line_numbers"] is False
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_bare_bool_turns_it_on(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "set nonumber")
        ex(ed, "set number")
        assert editor_config()["show_line_numbers"] is True


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_noautosync_from_the_docs(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "set noautosync")
        assert editor_config()["auto_sync_cards"] is False


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_bool_with_a_value(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "set auto_expand=off")
        assert editor_config()["auto_expand"] is False


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_bool_with_a_bad_value_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "set auto_expand=maybe")
        assert ed.is_error
        assert "auto_expand" not in editor_config()


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_choice_changes_what_sort_uses(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "set sort_order=name")
        assert editor_config()["sort_order"] == "name"
        ex(ed.press("8G"), "sort")
        assert ed.cards[:3] == CREATURES_BY_NAME


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_choice_outside_its_values_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "set sort_order=bogus")
        assert ed.is_error
        assert "sort_order" not in editor_config()


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_int_saves_the_number(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "set search_limit=100")
        assert not ed.is_error
        assert editor_config()["search_limit"] == 100


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["9", "501", "abc"])
async def test_set_int_outside_10_to_500_is_an_error(tmp_path: Path, value: str) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, f"set search_limit={value}")
        assert ed.is_error
        assert "search_limit" not in editor_config()


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_int_accepts_its_bounds(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "set search_limit=10")
        assert editor_config()["search_limit"] == 10
        ex(ed, "set search_limit=500")
        assert editor_config()["search_limit"] == 500


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_str_saves_the_text(tmp_path: Path) -> None:
    owned = tmp_path / "owned.csv"
    async with editor(tmp_path) as ed:
        ex(ed, f"set collection={owned}")
        assert editor_config()["collection"] == str(owned)
        assert ed.text == DECK


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_unknown_option_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "set bogus=1")
        assert ed.is_error
        assert not config_file().exists() or "bogus" not in config_file().read_text(
            encoding="utf-8"
        )


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_keeps_comments_and_other_sections(tmp_path: Path) -> None:
    config_file().write_text(
        "# my settings\n[editor]\nprice_source = \"eur\"  # euros\n\n"
        "[keybindings.normal]\n\";\" = \"j\"\n",
        encoding="utf-8",
    )
    async with editor(tmp_path) as ed:
        ex(ed, "set nonumber")
    text = config_file().read_text(encoding="utf-8")
    assert "# my settings" in text
    assert "# euros" in text
    data = tomllib.loads(text)
    assert data["editor"]["price_source"] == "eur"
    assert data["editor"]["show_line_numbers"] is False
    assert data["keybindings"]["normal"] == {";": "j"}


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_set_survives_a_restart(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "set sort_order=name")
    async with editor(tmp_path) as ed:
        ex(ed.press("8G"), "sort")
        assert ed.cards[:3] == CREATURES_BY_NAME


@pytest.mark.primitive(":set")
@pytest.mark.asyncio
async def test_bare_set_lists_every_option(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "set")
        assert not ed.is_error
        for default in ("usd", "cmc", "50"):
            assert default in ed.message
        assert not config_file().exists()


# ── :messages ────────────────────────────────────────────────────


@pytest.mark.primitive(":messages")
@pytest.mark.asyncio
async def test_messages_lists_recent_messages_and_errors(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "frobnicate")
        ex(ed, "13s/bolt/Helix/")
        body = await messages_window(ed)
        assert "frobnicate" in body
        assert "substitution" in body
        assert body.index("frobnicate") < body.index("substitution")


@pytest.mark.primitive(":messages")
@pytest.mark.asyncio
async def test_messages_keeps_a_listing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "g/bolt|ice/p")
        body = await messages_window(ed)
        assert "Lightning Bolt" in body
        assert "Fire // Ice" in body


@pytest.mark.primitive(":messages")
@pytest.mark.asyncio
async def test_messages_keeps_the_last_100(tmp_path: Path) -> None:
    def name(i: int) -> str:
        # letters only, so the E492 echo shows the whole word: 5 -> "nopefz"
        return "nope" + "".join("abcdefghij"[int(d)] for d in str(i)) + "z"

    async with editor(tmp_path) as ed:
        for i in range(105):
            ex(ed, name(i))
        body = await messages_window(ed)
        assert name(104) in body
        assert name(5) in body
        assert name(4) not in body
        assert name(0) not in body


@pytest.mark.primitive(":messages")
@pytest.mark.asyncio
async def test_messages_clear_empties_the_list(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "frobnicate")
        ex(ed, "messages clear")
        body = await messages_window(ed)
        assert "frobnicate" not in body


@pytest.mark.primitive(":messages")
@pytest.mark.asyncio
async def test_mes_is_an_alias(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ex(ed, "frobnicate")
        ex(ed, "mes")
        pilot = Pilot(ed.app)
        await pilot.pause()
        assert not isinstance(ed.app.screen, MainScreen)


@pytest.mark.primitive(":messages")
@pytest.mark.asyncio
async def test_messages_changes_nothing_in_the_buffer(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await messages_window(ed)
        assert ed.text == DECK
        assert ed.modified is False
