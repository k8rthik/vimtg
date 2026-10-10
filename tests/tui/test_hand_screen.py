"""Sample-hand overlay (Textual pilot): :hand / Sd open it, n/Space
draw, m + b run a London mulligan, r reshuffles, q/Esc close, and the
seed makes it repeatable. Plus the pure render function."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from vimtg.domain.sample_hand import HandSource, deal, mulligan
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.hand_screen import HandScreen, render_hand
from vimtg.tui.screens.main_screen import MainScreen

_DECK = (
    "// Deck: Burn\n"
    "// Format: modern\n"
    "\n"
    "DCK:\n"
    "4 Goblin Guide\n"
    "36 Lava Spike\n"
    "20 Mountain\n"
    "\n"
    "SB: 4 Skullcrack\n"
    "\n"
    "VS: Tron\n"
    "    -4 Goblin Guide\n"
    "    +4 Skullcrack\n"
)


def _deck(tmp_path: Path, text: str = _DECK) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(text, encoding="utf-8")
    return path


async def _type_command(pilot, text: str) -> None:  # type: ignore[no-untyped-def]
    await pilot.press("colon")
    for ch in text:
        await pilot.press("space" if ch == " " else ch)
    await pilot.press("enter")
    await pilot.pause()


def _hand_screen(app: VimTGApp) -> HandScreen:
    screen = app.screen
    assert isinstance(screen, HandScreen)
    return screen


def _body(app: VimTGApp) -> str:
    return str(app.screen.query_one("#hand-body").render())


@pytest.mark.asyncio
async def test_hand_command_opens_overlay(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await _type_command(pilot, "hand seed=42")
        screen = _hand_screen(app)
        assert len(screen.state.hand) == 7
        assert len(screen.state.library) == 53
        assert "Skullcrack" not in screen.state.cards()
        body = _body(app)
        assert "Sample hand" in body and "seed=42" in body
        assert "Hand (7 cards," in body
        assert "P(>=2 lands in 7)" in body


@pytest.mark.asyncio
async def test_sd_key_opens_overlay(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await pilot.press("S", "d")
        await pilot.pause()
        assert isinstance(app.screen, HandScreen)


@pytest.mark.asyncio
async def test_seed_is_repeatable(tmp_path: Path) -> None:
    hands = []
    for _ in range(2):
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await _type_command(pilot, "hand seed=7")
            await pilot.press("n", "space")
            await pilot.pause()
            hands.append(_hand_screen(app).state.hand)
    assert hands[0] == hands[1]
    assert len(hands[0]) == 9


@pytest.mark.asyncio
async def test_draw_mulligan_bottom_reshuffle(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await _type_command(pilot, "hand seed=1")
        screen = _hand_screen(app)

        await pilot.press("m")
        await pilot.pause()
        assert screen.state.mulligans == 1 and screen.state.to_bottom == 1
        assert "Put 1 card on the bottom" in _body(app)

        # Drawing is refused until the bottom debt is paid
        await pilot.press("n")
        await pilot.pause()
        assert len(screen.state.hand) == 7
        assert "bottom first" in _body(app)

        await pilot.press("j", "j")
        chosen = screen.state.hand[2]
        await pilot.press("b")
        await pilot.pause()
        assert len(screen.state.hand) == 6
        assert screen.state.library[-1] == chosen
        assert screen.state.kept

        await pilot.press("n")
        await pilot.pause()
        assert len(screen.state.hand) == 7 and screen.state.draws == 1

        # Mulligan after keeping is refused, the hand stays
        await pilot.press("m")
        await pilot.pause()
        assert "already kept" in _body(app)
        assert screen.state.draws == 1

        await pilot.press("r")
        await pilot.pause()
        assert screen.state.mulligans == 0 and screen.state.draws == 0
        assert len(screen.state.hand) == 7
        assert len(screen.state.cards()) == 60


@pytest.mark.asyncio
async def test_selection_is_clamped(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await _type_command(pilot, "hand")
        screen = _hand_screen(app)
        await pilot.press("k")
        assert screen.selected == 0
        for _ in range(10):
            await pilot.press("j")
        assert screen.selected == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["q", "escape"])
async def test_close_keys(tmp_path: Path, key: str) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await _type_command(pilot, "hand")
        await pilot.press(key)
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)


@pytest.mark.asyncio
async def test_active_plan_used(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await _type_command(pilot, "plan Tron")
        await _type_command(pilot, "hand")
        screen = _hand_screen(app)
        cards = screen.state.cards()
        assert "Goblin Guide" not in cards
        assert cards.count("Skullcrack") == 4
        assert "vs Tron" in _body(app)


@pytest.mark.asyncio
async def test_bad_seed_stays_in_editor(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await _type_command(pilot, "hand seed=x")
        assert isinstance(app.screen, MainScreen)


# ── render_hand ───────────────────────────────────────────


def test_render_shows_zones_lands_costs_and_selection() -> None:
    source = HandSource(
        library=("Forest",) * 30 + ("Elf",) * 69,
        command_zone=("Atraxa",),
        companions=("Lurrus",),
        lands=frozenset({"Forest"}),
    )
    state = deal(source.library, random.Random(0))
    lands = state.hand.count("Forest")
    text = render_hand(source, state, 0, seed=5, mana_costs={"Elf": "{G}"}).plain
    assert "seed=5" in text
    assert "Command zone: Atraxa" in text
    assert "Companion: Lurrus" in text
    assert f"{lands} land" in text
    assert " > " + state.hand[0] in text
    assert ("{G}" in text) == ("Elf" in state.hand)
    assert "Library: 92 cards" in text
    assert "Lands: 30 of 99" in text


def test_render_shows_mulligan_debt_and_message() -> None:
    source = HandSource(library=tuple(f"C{i}" for i in range(20)))
    rng = random.Random(0)
    state = mulligan(mulligan(deal(source.library, rng), rng), rng)
    text = render_hand(source, state, 0, message="nope").plain
    assert "mulligans: 2" in text
    assert "Put 2 cards on the bottom" in text
    assert "nope" in text
    assert "seed=" not in text


@pytest.mark.asyncio
async def test_unbound_key_changes_nothing(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await _type_command(pilot, "hand seed=3")
        screen = _hand_screen(app)
        before = screen.state
        await pilot.press("x", "colon")
        await pilot.pause()
        assert screen.state is before
        assert app.screen is screen
