"""Export destinations: one table says how each writes card names and
what it checks before a write."""

from __future__ import annotations

from typing import Any

import pytest

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.services.export_targets import (
    TARGETS,
    DeckFormat,
    Naming,
    target_named,
)
from vimtg.services.import_export_service import (
    FORMAT_NAMES,
    IMPORT_FORMAT_NAMES,
    ImportExportService,
)


def _card(name: str, layout: str = "normal", **extra: Any) -> Card:
    return Card.from_scryfall({"id": name, "name": name, "layout": layout, **extra})


_RESOLVED = {
    "Stomp": _card("Bonecrusher Giant // Stomp", "adventure"),
    "fire/ice": _card("Fire // Ice", "split"),
    "Insectile Aberration": _card("Delver of Secrets // Insectile Aberration", "transform"),
}
_TYPED = ("Stomp", "fire/ice", "Insectile Aberration")
_WRITTEN = {
    Naming.TYPED: _TYPED,
    Naming.OFFICIAL: (
        "Bonecrusher Giant // Stomp",
        "Fire // Ice",
        "Delver of Secrets // Insectile Aberration",
    ),
    Naming.CLIENT: ("Bonecrusher Giant", "Fire // Ice", "Delver of Secrets"),
    Naming.FRONT_FACE: ("Bonecrusher Giant", "Fire", "Delver of Secrets"),
}
_NAMING = {
    "arena": Naming.CLIENT,
    "mtgo": Naming.CLIENT,
    "dek": Naming.CLIENT,
    "moxfield": Naming.OFFICIAL,
    "archidekt": Naming.OFFICIAL,
    "list": Naming.FRONT_FACE,
    "mpc": Naming.FRONT_FACE,
    "tcgplayer": Naming.FRONT_FACE,
    "vimtg": Naming.TYPED,
    "guide": Naming.TYPED,
}


@pytest.mark.parametrize("naming", list(Naming))
def test_each_naming_writes_the_documented_name(naming: Naming) -> None:
    assert tuple(naming.write(n, _RESOLVED) for n in _TYPED) == _WRITTEN[naming]


def test_without_card_data_a_name_falls_back_to_its_typed_spelling() -> None:
    typed = "Brazen Borrower // Petty Theft"
    assert Naming.OFFICIAL.write(typed, {}) == typed
    assert Naming.CLIENT.write(typed, {}) == "Brazen Borrower"
    assert Naming.FRONT_FACE.write(typed, {}) == "Brazen Borrower"


def test_every_destination_states_its_naming() -> None:
    assert {t.name: t.naming for t in TARGETS} == _NAMING


def test_every_format_name_is_one_destination() -> None:
    names = [n for t in TARGETS for n in (t.name, *t.aliases)]
    assert len(names) == len(set(names))
    assert list(FORMAT_NAMES) == names
    assert target_named("mtga") is target_named("arena")
    assert target_named("MPC") is target_named("mpc")
    assert target_named("nope") is None
    assert "mpc" not in IMPORT_FORMAT_NAMES


def test_mpc_and_tcgplayer_are_destinations_of_the_plain_list() -> None:
    for name in ("list", "mpc", "tcgplayer"):
        target = target_named(name)
        assert target is not None and target.name == name
        assert target.fmt is DeckFormat.LIST


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: t.name)
def test_a_destination_writes_its_serializer_output(target: Any) -> None:
    deck = parse_deck_text("4 Stomp\n1 fire/ice\nSB: 2 Insectile Aberration\n")
    svc = ImportExportService()
    assert svc.export(deck, target, _RESOLVED) == svc.export_deck(deck, target.fmt, _RESOLVED)
