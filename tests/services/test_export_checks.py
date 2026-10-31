"""check_export: what each destination checks before a deck is written.
Pure and offline, so the cards are built from small Scryfall dicts."""

from __future__ import annotations

from typing import Any

import pytest

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.services.export_targets import (
    TARGETS,
    ExportIssue,
    ExportTarget,
    IssueLevel,
    check_export,
    exported_card_count,
    target_named,
)

ERROR, WARNING = IssueLevel.ERROR, IssueLevel.WARNING


def _card(
    name: str,
    *,
    timeless: str | None = "legal",
    tix: str | None = "0.05",
    type_line: str = "Instant",
) -> Card:
    legalities = {"modern": "legal"} | ({"timeless": timeless} if timeless else {})
    data: dict[str, Any] = {
        "id": name,
        "name": name,
        "type_line": type_line,
        "legalities": legalities,
        "prices": {"usd": "1.00", "tix": tix},
    }
    return Card.from_scryfall(data)


def _target(name: str) -> ExportTarget:
    target = target_named(name)
    assert target is not None
    return target


def _check(text: str, cards: list[Card] | None, name: str) -> tuple[ExportIssue, ...]:
    resolved = None if cards is None else {c.name: c for c in cards}
    return check_export(parse_deck_text(text), resolved, _target(name))


def _levels(issues: tuple[ExportIssue, ...]) -> list[IssueLevel]:
    return [i.level for i in issues]


BOLT = _card("Lightning Bolt")
GUIDE = _card("Goblin Guide", timeless="not_legal", type_line="Creature — Goblin Scout")
MOUNTAIN = _card("Mountain", tix=None, type_line="Basic Land — Mountain")


# ── every destination ──────────────────────────────────────────────


@pytest.mark.parametrize("name", ["arena", "mtgo", "dek", "moxfield", "list", "mpc"])
def test_no_card_database_is_one_warning_that_checks_were_limited(name: str) -> None:
    issues = _check("4 Goblin Guide\n4 Notacard\n", None, name)
    assert _levels(issues) == [WARNING]
    assert "limited" in issues[0].message
    assert issues[0].cards == ()


@pytest.mark.parametrize("name", ["arena", "mtgo", "moxfield", "archidekt", "tcgplayer"])
def test_unknown_names_are_a_warning_naming_them(name: str) -> None:
    issues = _check("4 Lightning Bolt\n2 Notacard\nSB: 1 Bogus Thing\n", [BOLT], name)
    unknown = [i for i in issues if "may not recognise" in i.message]
    assert len(unknown) == 1
    assert unknown[0].level is WARNING
    assert unknown[0].cards == ("Notacard", "Bogus Thing")


@pytest.mark.parametrize("name", ["arena", "mtgo", "dek", "list", "mpc", "tcgplayer"])
def test_nothing_in_the_written_zones_is_an_error(name: str) -> None:
    issues = _check("MB: 4 Lightning Bolt\n", [BOLT], name)
    assert _levels(issues) == [ERROR]


@pytest.mark.parametrize("name", ["moxfield", "archidekt"])
def test_csv_destinations_write_the_maybeboard_so_it_is_not_empty(name: str) -> None:
    assert _check("MB: 4 Lightning Bolt\n", [BOLT], name) == ()


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: t.name)
def test_a_resolvable_deck_passes_every_generic_check(target: ExportTarget) -> None:
    text = "4 Lightning Bolt\nSB: 2 Lightning Bolt\nVS: Control\n    +2 Lightning Bolt\n"
    assert check_export(parse_deck_text(text), {"Lightning Bolt": BOLT}, target) == ()


def test_vimtg_checks_nothing() -> None:
    assert _check("", None, "vimtg") == ()


# ── mpc ────────────────────────────────────────────────────────────


def test_mpc_refuses_an_at_sign_in_a_card_name() -> None:
    issues = _check("4 Lightning Bolt\n1 Foo@Bar\n", [BOLT, _card("Foo@Bar")], "mpc")
    assert _levels(issues) == [ERROR]
    assert issues[0].cards == ("Foo@Bar",)


@pytest.mark.parametrize("name", ["list", "tcgplayer"])
def test_other_list_destinations_allow_an_at_sign(name: str) -> None:
    assert _check("1 Foo@Bar\n", [_card("Foo@Bar")], name) == ()


def test_mpc_counts_the_cards_it_writes() -> None:
    deck = parse_deck_text(
        "CMD: 1 Goblin Guide\n4 Lightning Bolt\nSB: 2 Lightning Bolt\nMB: 9 Opt\n"
    )
    assert exported_card_count(deck, _target("mpc")) == 7
    assert _target("mpc").counts_cards
    assert not _target("list").counts_cards


# ── arena ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["arena", "mtga"])
def test_arena_refuses_cards_not_on_arena(name: str) -> None:
    text = "4 Goblin Guide\n4 Lightning Bolt\n20 Mountain\n"
    issues = _check(text, [GUIDE, BOLT, MOUNTAIN], name)
    assert _levels(issues) == [ERROR]
    assert issues[0].cards == ("Goblin Guide",)
    assert "Arena" in issues[0].message


def test_arena_counts_banned_and_restricted_cards_as_on_arena() -> None:
    cards = [
        _card("Banned Thing", timeless="banned"),
        _card("Restricted Thing", timeless="restricted"),
    ]
    assert _check("1 Banned Thing\n1 Restricted Thing\n", cards, "arena") == ()


def test_arena_ignores_the_maybeboard() -> None:
    assert _check("4 Lightning Bolt\nMB: 4 Goblin Guide\n", [BOLT, GUIDE], "arena") == ()


def test_arena_without_timeless_data_warns_availability_is_unknown() -> None:
    old = [_card("Goblin Guide", timeless=None), _card("Lightning Bolt", timeless=None)]
    issues = _check("4 Goblin Guide\n4 Lightning Bolt\n", old, "arena")
    assert _levels(issues) == [WARNING]
    assert issues[0].message == "Arena availability unknown; run vimtg sync"


def test_only_arena_checks_arena_availability() -> None:
    assert _check("4 Goblin Guide\n", [GUIDE], "moxfield") == ()


def test_a_long_card_list_names_the_first_two_and_counts_the_rest() -> None:
    names = ["Alpha", "Beta", "Gamma", "Delta"]
    cards = [_card(n, timeless="not_legal") for n in names]
    issue = _check("".join(f"1 {n}\n" for n in names), cards, "arena")[0]
    assert issue.cards == tuple(names)
    assert issue.text().endswith(": Alpha, Beta and 2 more")


# ── mtgo ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["mtgo", "dek"])
def test_mtgo_warns_about_cards_with_no_tix_price(name: str) -> None:
    paper = _card("Paper Only", tix=None)
    text = "4 Lightning Bolt\n20 Mountain\nSB: 1 Paper Only\n"
    issues = _check(text, [BOLT, MOUNTAIN, paper], name)
    assert _levels(issues) == [WARNING]
    assert issues[0].cards == ("Paper Only",)
    assert "may not be on MTGO" in issues[0].message


def test_basic_lands_have_no_tix_price_and_are_fine_on_mtgo() -> None:
    snow = _card("Snow-Covered Mountain", tix=None, type_line="Basic Snow Land — Mountain")
    assert _check("20 Mountain\n4 Snow-Covered Mountain\n", [MOUNTAIN, snow], "mtgo") == ()


# ── guide ──────────────────────────────────────────────────────────


def test_guide_without_sideboard_plans_is_an_error() -> None:
    issues = _check("4 Lightning Bolt\nSB: 2 Lightning Bolt\n", [BOLT], "guide")
    assert _levels(issues) == [ERROR]
