"""Overlay primitives: help (:help, F1, g?), :tips, :config, :hand and
Space h, :combos and Space c.

Each overlay opens with its documented title, closes with its documented
keys, and returns to the editor with the deck unchanged (docs/commands.md
Help / Configuration / Sample hand / Combos, docs/keybindings.md Screens).
Keys typed into an overlay go through the app, as a terminal sends them.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from tests.primitives.harness import DECK, FIXTURES, Ed, editor
from tests.primitives.test_files_and_panes_helpers import (
    ex,
    in_editor,
    keys,
    overlay_title,
    settle,
    shown,
)
from vimtg.config.paths import config_dir

pytestmark = pytest.mark.asyncio

HELP_TITLE = "vimtg Help"
CLOSE_KEYS = ["q", "escape"]


def _help_panel_open(ed: Ed) -> bool:
    return bool(ed.screen.query_one("#help-panel").display)


def _tips_shown(ed: Ed) -> bool:
    return bool(ed.screen.query_one("#tips-panel").display)


# ── :help ───────────────────────────────────────────────────────────


@pytest.mark.primitive(":help")
@pytest.mark.parametrize("close", ["q", "escape", "question_mark"])
async def test_help_opens_the_overview_and_closes_back_to_the_deck(
    tmp_path: Path, close: str
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("help"))
        await settle(ed)
        assert overlay_title(ed) == HELP_TITLE
        assert "GETTING STARTED" in shown(ed, "#help-body")
        await keys(ed, close)
        assert in_editor(ed)
        assert ed.text == DECK


@pytest.mark.primitive(":help")
async def test_help_command_opens_that_commands_topic(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("help sort"))
        await settle(ed)
        assert overlay_title(ed) == f"{HELP_TITLE}: sort"
        assert ":sort" in shown(ed, "#help-body")


@pytest.mark.primitive(":help")
async def test_help_an_alias_opens_its_commands_topic(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("help exp"))
        await settle(ed)
        assert overlay_title(ed) == f"{HELP_TITLE}: export"


@pytest.mark.primitive(":help", "f1")
async def test_f1_on_a_help_topic_switches_to_the_overview(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("help sort"))
        await keys(ed, "f1")
        assert overlay_title(ed) == HELP_TITLE
        assert "GETTING STARTED" in shown(ed, "#help-body")


@pytest.mark.primitive(":help")
async def test_help_for_an_unknown_topic_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("help nosuchthing"))
        await settle(ed)
        assert in_editor(ed)
        assert ed.is_error is True
        assert ed.text == DECK


# ── F1 ──────────────────────────────────────────────────────────────


@pytest.mark.primitive("f1")
async def test_f1_opens_the_help_overview_and_q_closes_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await keys(ed, "f1")
        assert overlay_title(ed) == HELP_TITLE
        await keys(ed, "q")
        assert in_editor(ed)
        assert ed.text == DECK


# ── g? ──────────────────────────────────────────────────────────────


@pytest.mark.primitive("g?")
@pytest.mark.parametrize("close", ["q", "escape", "question_mark"])
async def test_g_question_opens_the_cheat_sheet_and_closes_it(
    tmp_path: Path, close: str
) -> None:
    async with editor(tmp_path) as ed:
        await keys(ed, "g", "question_mark")
        assert _help_panel_open(ed)
        await keys(ed, close)
        assert not _help_panel_open(ed)
        assert in_editor(ed)
        assert ed.text == DECK


@pytest.mark.primitive("g?")
async def test_g_question_twice_toggles_the_cheat_sheet_off(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await keys(ed, "g", "question_mark", "g", "question_mark")
        assert not _help_panel_open(ed)
        assert ed.text == DECK


@pytest.mark.primitive("g?", "f1")
async def test_f1_trades_the_cheat_sheet_for_the_full_help(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await keys(ed, "g", "question_mark", "f1")
        assert overlay_title(ed) == HELP_TITLE
        await keys(ed, "q")
        assert in_editor(ed)
        assert not _help_panel_open(ed)


@pytest.mark.primitive("g?")
async def test_cheat_sheet_keys_never_edit_the_deck(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await keys(ed, "g", "question_mark", "d", "d", "x")
        assert _help_panel_open(ed)
        assert ed.text == DECK


# ── :tips ───────────────────────────────────────────────────────────

EMPTY_NAMED = "// Deck: Empty\n// Format: modern\n"


@pytest.mark.primitive(":tips")
async def test_tips_shows_the_tips_panel_and_esc_hides_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        assert not _tips_shown(ed)  # a deck with cards, already written
        ed.press(ex("tips"))
        await settle(ed)
        assert _tips_shown(ed)
        await keys(ed, "escape")
        assert not _tips_shown(ed)
        assert ed.text == DECK


@pytest.mark.primitive(":tips")
async def test_tips_off_hides_them_under_empty_decks_for_good(tmp_path: Path) -> None:
    async with editor(tmp_path, EMPTY_NAMED) as ed:
        assert _tips_shown(ed)
        ed.press(ex("tips off"))
        await settle(ed)
        assert not _tips_shown(ed)
    async with editor(tmp_path, EMPTY_NAMED) as ed:
        assert not _tips_shown(ed)


@pytest.mark.primitive(":tips")
async def test_tips_on_brings_them_back(tmp_path: Path) -> None:
    async with editor(tmp_path, EMPTY_NAMED) as ed:
        ed.press(ex("tips off") + ex("tips on"))
        await settle(ed)
        assert _tips_shown(ed)
    async with editor(tmp_path, EMPTY_NAMED) as ed:
        assert _tips_shown(ed)


@pytest.mark.primitive(":tips")
async def test_tips_with_an_unknown_argument_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("tips sometimes"))
        assert ed.is_error is True
        assert not _tips_shown(ed)


# ── :config ─────────────────────────────────────────────────────────


def _saved_config() -> dict[str, object]:
    path = config_dir() / "config.toml"
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8")).get("editor", {})


@pytest.mark.primitive(":config")
@pytest.mark.parametrize("close", CLOSE_KEYS)
async def test_config_opens_the_settings_and_closes_back_to_the_deck(
    tmp_path: Path, close: str
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("config"))
        await settle(ed)
        assert overlay_title(ed) == "Settings"
        await keys(ed, close)
        assert in_editor(ed)
        assert ed.text == DECK


@pytest.mark.primitive(":config")
async def test_config_s_saves_a_changed_setting_and_closes(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("config"))
        await keys(ed, "l", "s")  # first row: price_source, usd -> usd_foil
        assert in_editor(ed)
    assert _saved_config().get("price_source") == "usd_foil"


@pytest.mark.primitive(":config")
async def test_config_asks_once_more_before_closing_over_unsaved_changes(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("config"))
        await keys(ed, "l", "q")
        assert overlay_title(ed) == "Settings"
        await keys(ed, "q")
        assert in_editor(ed)
    assert _saved_config().get("price_source") != "usd_foil"


# ── :hand and Space h ───────────────────────────────────────────────

MAIN_ONLY_HAND = (
    "// Deck: Lands\n// Format: modern\n\n"
    "DCK:\n    60 Mountain\n\n"
    "SB:\n    15 Rest in Peace\n"
)


@pytest.mark.primitive(":hand")
@pytest.mark.parametrize("close", CLOSE_KEYS)
async def test_hand_opens_the_sample_hand_and_closes_back_to_the_deck(
    tmp_path: Path, close: str
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("hand"))
        await settle(ed)
        assert overlay_title(ed) == "Sample hand"
        await keys(ed, close)
        assert in_editor(ed)
        assert ed.text == DECK


@pytest.mark.primitive(":hand")
async def test_hand_draws_seven_from_the_main_deck_only(tmp_path: Path) -> None:
    async with editor(tmp_path, MAIN_ONLY_HAND) as ed:
        ed.press(ex("hand"))
        await settle(ed)
        body = shown(ed, "#hand-body")
        assert "Hand (7 cards" in body
        assert "Mountain" in body
        assert "Rest in Peace" not in body


@pytest.mark.primitive(":hand")
async def test_hand_n_draws_the_next_card(tmp_path: Path) -> None:
    async with editor(tmp_path, MAIN_ONLY_HAND) as ed:
        ed.press(ex("hand"))
        await keys(ed, "n")
        assert "Hand (8 cards" in shown(ed, "#hand-body")


@pytest.mark.primitive(":hand")
async def test_hand_with_the_same_seed_deals_the_same_hand(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("hand seed=42"))
        await settle(ed)
        first = shown(ed, "#hand-body")
        await keys(ed, "q")
        ed.press(ex("hand 42"))
        await settle(ed)
        assert shown(ed, "#hand-body") == first
        assert "seed=42" in first


@pytest.mark.primitive(":hand")
@pytest.mark.parametrize("arg", ["seed=x", "draws=3"])
async def test_hand_with_a_bad_seed_is_an_error(tmp_path: Path, arg: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex(f"hand {arg}"))
        await settle(ed)
        assert in_editor(ed)
        assert ed.is_error is True
        assert ed.text == DECK


@pytest.mark.primitive(":hand")
async def test_hand_with_no_main_deck_is_an_error(tmp_path: Path) -> None:
    deck = "// Deck: Side\n// Format: modern\n\nSB:\n    2 Rest in Peace\n"
    async with editor(tmp_path, deck) as ed:
        ed.press(ex("hand"))
        await settle(ed)
        assert in_editor(ed)
        assert ed.is_error is True


@pytest.mark.primitive("space h")
async def test_space_h_opens_the_sample_hand(tmp_path: Path) -> None:
    async with editor(tmp_path, MAIN_ONLY_HAND) as ed:
        ed.press("<Space>h")
        await settle(ed)
        assert overlay_title(ed) == "Sample hand"
        assert "Hand (7 cards" in shown(ed, "#hand-body")
        await keys(ed, "q")
        assert in_editor(ed)


# ── :combos and Space c ─────────────────────────────────────────────

THORACLE = (
    "// Deck: Thoracle\n// Format: commander\n\n"
    "DCK:\n    1 Thassa's Oracle\n    1 Demonic Consultation\n    1 Mountain\n"
)
SPELLBOOK_FIXTURE = FIXTURES / "spellbook" / "find_my_combos_thassa.json"


@pytest.fixture
def recorded_spellbook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIMTG_SPELLBOOK_FIXTURE", str(SPELLBOOK_FIXTURE))


async def _combos(ed: Ed, opener: str) -> str:
    """Open the combos overlay, wait for the lookup, return its body."""
    ed.press(opener)
    await settle(ed)
    await ed.app.workers.wait_for_complete()
    await settle(ed)
    return shown(ed, "#combo-body")


@pytest.mark.primitive(":combos")
@pytest.mark.parametrize("close", CLOSE_KEYS)
@pytest.mark.usefixtures("recorded_spellbook")
async def test_combos_lists_held_and_one_away_combos_then_closes(
    tmp_path: Path, close: str
) -> None:
    async with editor(tmp_path, THORACLE) as ed:
        before = ed.text
        body = await _combos(ed, ex("combos"))
        assert overlay_title(ed).startswith("Combos — ")
        held, _, away = body.partition("One card away")
        assert "In this deck" in held
        assert "Demonic Consultation" in held
        assert "Tainted Pact" in away
        await keys(ed, close)
        assert in_editor(ed)
        assert ed.text == before


@pytest.mark.primitive(":combos")
@pytest.mark.usefixtures("recorded_spellbook")
async def test_combos_enter_on_a_one_away_combo_adds_the_missing_card(tmp_path: Path) -> None:
    async with editor(tmp_path, THORACLE) as ed:
        before = ed.text
        await _combos(ed, ex("combos"))
        await keys(ed, "j", "enter")  # the second row is the one-away combo
        assert in_editor(ed)
        assert "1 Tainted Pact" in ed.cards
        ed.press("u")
        assert ed.text == before


@pytest.mark.primitive(":combos")
async def test_combos_with_lookups_disabled_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIMTG_NO_SPELLBOOK", "1")
    async with editor(tmp_path, THORACLE) as ed:
        body = await _combos(ed, ex("combos"))
        assert "VIMTG_NO_SPELLBOOK" in body
        await keys(ed, "q")
        assert in_editor(ed)


@pytest.mark.primitive(":combos")
async def test_combos_with_an_argument_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("combos all"))
        await settle(ed)
        assert in_editor(ed)
        assert ed.is_error is True


@pytest.mark.primitive(":combos")
async def test_combos_of_a_deck_without_cards_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path, "// Deck: Empty\n// Format: modern\n") as ed:
        ed.press(ex("combos"))
        await settle(ed)
        assert in_editor(ed)
        assert ed.is_error is True


@pytest.mark.primitive("space c")
@pytest.mark.usefixtures("recorded_spellbook")
async def test_space_c_opens_the_combos_overlay(tmp_path: Path) -> None:
    async with editor(tmp_path, THORACLE) as ed:
        body = await _combos(ed, "<Space>c")
        assert overlay_title(ed).startswith("Combos — ")
        assert "One card away" in body
        await keys(ed, "q")
        assert in_editor(ed)

