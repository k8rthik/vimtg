"""Import/export correctness: official card names on export, canonical
names on import, Commander lists in plain text, URL-import format and
signature spells, the structured import layout, and quantity-less or
tagged pasted lines. Card data comes from the real-shape Scryfall
fixtures (no network)."""

from __future__ import annotations

import csv
import io
from typing import Any

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.deck import DeckSection
from vimtg.services import deck_sources
from vimtg.services.deck_sources import (
    parse_archidekt,
    parse_decklist_text,
    parse_moxfield,
    stamped_deck,
)
from vimtg.services.import_export_service import (
    DeckFormat,
    ImportExportService,
    structured_deck_text,
)

# Typed spellings the clients reject or that name another face
_TYPED = (
    "// Deck: Names\n"
    "4 Stomp\n"
    "4 Fire/Ice\n"
    "4 delver of secrets\n"
    "4 lightning bolt\n"
)


def _resolved(repo: CardRepository, text: str) -> dict[str, Any]:
    deck = parse_deck_text(text)
    return dict(repo.get_by_names(sorted(deck.unique_card_names())))


# ── (b) exports write the card's real resolved name ────────────────


class TestExportOfficialNames:
    def test_arena_uses_official_front_face_and_split_names(
        self, real_shape_repo: CardRepository
    ) -> None:
        deck = parse_deck_text(_TYPED)
        out = ImportExportService().export_deck(
            deck, DeckFormat.ARENA, resolved=_resolved(real_shape_repo, _TYPED)
        )
        lines = out.splitlines()
        assert "4 Bonecrusher Giant" in lines  # adventure: front face
        assert "4 Fire // Ice" in lines  # split: both halves
        assert "4 Delver of Secrets" in lines  # DFC: front face, real case
        assert "4 Lightning Bolt" in lines
        assert "4 Stomp" not in lines and "4 Fire/Ice" not in lines

    def test_mtgo_text_and_dek_use_official_names(
        self, real_shape_repo: CardRepository
    ) -> None:
        deck = parse_deck_text(_TYPED)
        resolved = _resolved(real_shape_repo, _TYPED)
        service = ImportExportService()
        mtgo = service.export_deck(deck, DeckFormat.MTGO, resolved=resolved)
        assert "4 Bonecrusher Giant\n" in mtgo and "4 Fire // Ice\n" in mtgo
        dek = service.export_deck(deck, DeckFormat.MTGO_DEK, resolved=resolved)
        assert 'Name="Bonecrusher Giant"' in dek
        assert 'Name="Fire // Ice"' in dek
        assert 'Name="Delver of Secrets"' in dek

    def test_csv_exports_use_full_official_names(
        self, real_shape_repo: CardRepository
    ) -> None:
        deck = parse_deck_text(_TYPED)
        resolved = _resolved(real_shape_repo, _TYPED)
        service = ImportExportService()
        for fmt in (DeckFormat.MOXFIELD, DeckFormat.ARCHIDEKT):
            rows = list(csv.DictReader(io.StringIO(
                service.export_deck(deck, fmt, resolved=resolved)
            )))
            names = {row["Name"] for row in rows}
            assert names == {
                "Bonecrusher Giant // Stomp",
                "Fire // Ice",
                "Delver of Secrets // Insectile Aberration",
                "Lightning Bolt",
            }, fmt


# ── (d) imports normalise names; duplicates merge by card ──────────


class TestImportCanonicalNames:
    def test_spellings_of_one_card_merge_into_its_official_name(
        self, real_shape_repo: CardRepository
    ) -> None:
        service = ImportExportService(card_repo=real_shape_repo)
        deck = service.import_deck(
            "4 Fire // Ice\n4 Fire/Ice\n2 Delver of Secrets\n2 Insectile Aberration\n",
            DeckFormat.MTGO,
        )
        assert [(e.quantity, e.card_name) for e in deck.entries] == [
            (8, "Fire // Ice"),
            (4, "Delver of Secrets // Insectile Aberration"),
        ]

    def test_without_card_data_separator_spellings_still_merge(self) -> None:
        deck = ImportExportService().import_deck(
            "4 Fire // Ice\n4 Fire/Ice\n", DeckFormat.MTGO
        )
        assert [(e.quantity, e.card_name) for e in deck.entries] == [
            (8, "Fire // Ice")
        ]

    def test_unknown_names_stay_as_typed(
        self, real_shape_repo: CardRepository
    ) -> None:
        service = ImportExportService(card_repo=real_shape_repo)
        deck = service.import_deck("4 Not A Real Card\n", DeckFormat.MTGO)
        assert deck.entries[0].card_name == "Not A Real Card"


# ── (c) plain-text Commander lists ─────────────────────────────────

_NINETY_NINE = (
    "1 Sol Ring\n1 Rhystic Study\n1 Lightning Bolt\n1 Aether Vial\n"
    "1 Relentless Rats\n1 Lim-Dûl's Vault\n1 Fire // Ice\n"
    "46 Mountain\n46 Island\n"
)  # 99 cards
_KENRITH = "1 Kenrith, the Returned King\n"


class TestCommanderLists:
    def test_commander_first_moxfield_list(self) -> None:
        deck = ImportExportService().import_deck(_KENRITH + "\n" + _NINETY_NINE)
        assert [e.card_name for e in deck.commanders()] == [
            "Kenrith, the Returned King"
        ]
        assert sum(e.quantity for e in deck.mainboard()) == 99
        assert deck.sideboard() == ()

    def test_commander_last_list(self) -> None:
        deck = ImportExportService().import_deck(_NINETY_NINE + "\n" + _KENRITH)
        assert [e.card_name for e in deck.commanders()] == [
            "Kenrith, the Returned King"
        ]
        assert sum(e.quantity for e in deck.mainboard()) == 99
        assert deck.sideboard() == ()
        # The command zone reads first
        assert deck.entries[0].section == DeckSection.COMMANDER

    def test_partner_pair_is_the_command_zone(self) -> None:
        main_98 = _NINETY_NINE.replace("46 Island", "45 Island")
        deck = ImportExportService().import_deck(
            "1 Thrasios, Triton Hero\n1 Tymna the Weaver\n\n" + main_98
        )
        assert {e.card_name for e in deck.commanders()} == {
            "Thrasios, Triton Hero", "Tymna the Weaver",
        }
        assert deck.sideboard() == ()

    def test_sixty_card_deck_keeps_its_small_sideboard(self) -> None:
        deck = ImportExportService().import_deck(
            "4 Lightning Bolt\n56 Mountain\n\n1 Thrasios, Triton Hero\n"
        )
        assert deck.commanders() == ()
        assert [e.card_name for e in deck.sideboard()] == ["Thrasios, Triton Hero"]

    def test_sixty_card_list_led_by_eligible_card_with_card_data(
        self, real_shape_repo: CardRepository
    ) -> None:
        # Brawl: 59 + a legendary creature — the card database decides
        text = "1 Thrasios, Triton Hero\n\n4 Lightning Bolt\n55 Island\n"
        deck = ImportExportService(card_repo=real_shape_repo).import_deck(text)
        assert [e.card_name for e in deck.commanders()] == ["Thrasios, Triton Hero"]
        # ... but an ineligible single card stays a sideboard
        text = "4 Rhystic Study\n55 Island\n\n1 Lightning Bolt\n"
        deck = ImportExportService(card_repo=real_shape_repo).import_deck(text)
        assert deck.commanders() == ()
        assert [e.card_name for e in deck.sideboard()] == ["Lightning Bolt"]

    def test_mtgo_two_group_sideboard_split_unchanged(self) -> None:
        deck = ImportExportService().import_deck(
            "4 Lightning Bolt\n56 Mountain\n\n3 Smash to Smithereens\n"
        )
        assert [e.card_name for e in deck.sideboard()] == ["Smash to Smithereens"]


# ── (g) quantity-less lines and single-space tags ──────────────────


class TestPastedLineShapes:
    def test_line_without_quantity_is_one_copy(self) -> None:
        remote = parse_decklist_text(
            "4 Lightning Bolt\nSol Ring\nDelver of Secrets\n", name=""
        )
        assert [(e.quantity, e.card_name) for e in remote.deck.entries] == [
            (4, "Lightning Bolt"), (1, "Sol Ring"), (1, "Delver of Secrets"),
        ]
        assert remote.skipped == ()

    def test_main_deck_header_is_not_a_card(self) -> None:
        remote = parse_decklist_text("Main Deck\n4 Opt\nSideboard\n1 Duress\n", name="")
        assert [(e.card_name, e.section) for e in remote.deck.entries] == [
            ("Opt", DeckSection.MAIN), ("Duress", DeckSection.SIDEBOARD),
        ]

    def test_prose_and_group_labels_are_not_cards(self) -> None:
        remote = parse_decklist_text(
            "Creatures\n4 Goblin Guide\nnot a card line\nLands:\n", name=""
        )
        assert [e.card_name for e in remote.deck.entries] == ["Goblin Guide"]
        assert [s.text for s in remote.skipped] == [
            "Creatures", "not a card line", "Lands:",
        ]

    def test_lowercase_name_known_to_the_card_database(
        self, real_shape_repo: CardRepository
    ) -> None:
        remote = parse_decklist_text(
            "sol ring\n", name="", lookup=real_shape_repo.get_by_name
        )
        assert [(e.quantity, e.card_name) for e in remote.deck.entries] == [
            (1, "sol ring")
        ]

    def test_single_space_category_and_tags(self) -> None:
        remote = parse_decklist_text(
            "1 Sol Ring @ramp\n2 Rhystic Study @draw #core\nSol Talisman #fast\n",
            name="",
        )
        got = [(e.card_name, e.category, e.tags) for e in remote.deck.entries]
        assert got == [
            ("Sol Ring", "ramp", frozenset()),
            ("Rhystic Study", "draw", frozenset({"core"})),
            ("Sol Talisman", "", frozenset({"fast"})),
        ]

    def test_deckstats_comment_still_stripped(self) -> None:
        remote = parse_decklist_text(
            "1 Sol Ring # best card\n1 Kenrith #!Commander\n", name=""
        )
        assert [(e.card_name, e.section) for e in remote.deck.entries] == [
            ("Sol Ring", DeckSection.MAIN),
            ("Kenrith", DeckSection.COMMANDER),
        ]


# ── (e) URL imports ────────────────────────────────────────────────


def _moxfield(fmt: str, boards: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "Wrenn Oath",
        "format": fmt,
        "boards": {
            name: {"count": len(cards), "cards": cards}
            for name, cards in boards.items()
        },
    }


def _mox_card(qty: int, name: str) -> dict[str, Any]:
    return {"quantity": qty, "boardType": "x", "card": {"name": name}}


class TestUrlImports:
    def test_moxfield_format_and_signature_spell(self) -> None:
        data = _moxfield("oathbreaker", {
            "commanders": {"a": _mox_card(1, "Wrenn and Seven")},
            "signatureSpells": {"b": _mox_card(1, "Lightning Bolt")},
            "mainboard": {"c": _mox_card(58, "Forest")},
        })
        remote = parse_moxfield(data)
        assert remote.format == "oathbreaker"
        assert {e.card_name for e in remote.deck.commanders()} == {
            "Wrenn and Seven", "Lightning Bolt",
        }
        deck = stamped_deck(remote, "https://moxfield.com/decks/x")
        assert deck.metadata.format == "oathbreaker"
        assert "// Format: oathbreaker" in structured_deck_text(deck)

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("commander", "commander"), ("pauperEdh", "paupercommander"),
         ("Modern", "modern"), ("someNewFormat", "")],
    )
    def test_moxfield_format_names(self, raw: str, expected: str) -> None:
        assert parse_moxfield(_moxfield(raw, {})).format == expected

    def test_archidekt_numeric_format(self) -> None:
        data = {
            "name": "Kenrith",
            "deckFormat": 3,
            "categories": [],
            "cards": [{
                "quantity": 1,
                "categories": ["Commander"],
                "card": {"oracleCard": {"name": "Kenrith, the Returned King"}},
            }],
        }
        remote = parse_archidekt(data)
        assert remote.format == "commander"
        assert parse_archidekt({**data, "deckFormat": 7}).format == ""  # Custom

    def test_requests_send_versioned_user_agent_and_accept(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from vimtg import __version__

        seen: dict[str, Any] = {}

        class _Resp:
            status_code = 200
            text = "4 Lightning Bolt\n"

            def json(self) -> object:
                return _moxfield("modern", {})

        def fake_get(url: str, **kwargs: Any) -> _Resp:
            seen.update(kwargs["headers"])
            return _Resp()

        monkeypatch.setattr(deck_sources.httpx, "get", fake_get)
        deck_sources.fetch_deck("https://moxfield.com/decks/abc")
        assert seen["User-Agent"].startswith(f"vimtg/{__version__} ")
        assert seen["Accept"] == "application/json"
        deck_sources.fetch_deck("https://tappedout.net/mtg-decks/burn/")
        assert "text/plain" in seen["Accept"]


# ── (f) structured import layout ───────────────────────────────────


class TestStructuredLayout:
    def test_formatless_import_gets_metadata_and_blocks(self) -> None:
        deck = ImportExportService().import_deck(
            "4 Lightning Bolt\n20 Mountain\n\n2 Smash to Smithereens\n"
        )
        text = structured_deck_text(deck)
        assert text == (
            "// Deck:\n"
            "// Format:\n"
            "\n"
            "DCK:\n"
            "    4 Lightning Bolt\n"
            "    20 Mountain\n"
            "\n"
            "SB:\n"
            "    2 Smash to Smithereens\n"
        )
        assert "SB: " not in text

    def test_type_sections_with_card_data_and_lossless_reparse(
        self, real_shape_repo: CardRepository
    ) -> None:
        service = ImportExportService(card_repo=real_shape_repo)
        deck = service.import_deck(
            "Commander\n1 Thrasios, Triton Hero\nDeck\n"
            "1 Sol Ring @ramp\n1 Lightning Bolt\n30 Mountain\n1 Mystery Card\n"
        )
        resolved = service.resolve_cards(deck).resolved
        text = structured_deck_text(deck, resolved)
        lines = text.splitlines()
        assert lines[:5] == [
            "// Deck:", "// Format:", "", "CMD:", "    1 Thrasios, Triton Hero",
        ]
        dck = lines.index("DCK:")
        assert lines[dck + 1:] == [
            "    // Instants",
            "    1 Lightning Bolt",
            "",
            "    // Artifacts",
            "    1 Sol Ring  @ramp",
            "",
            "    // Lands",
            "    30 Mountain",
            "",
            "    // Other",
            "    1 Mystery Card",
        ]
        reparsed = parse_deck_text(text)
        assert sorted(
            (e.section.value, e.quantity, e.card_name, e.category)
            for e in reparsed.entries
        ) == sorted(
            (e.section.value, e.quantity, e.card_name, e.category)
            for e in deck.entries
        )

    def test_commander_format_scaffolds_empty_cmd_block(self) -> None:
        deck = parse_deck_text("// Format: commander\n1 Sol Ring\n")
        assert "CMD:\n\nDCK:" in structured_deck_text(deck)


class TestStructuredLayoutKeepsEverything:
    def test_metadata_comments_zones_and_plans_survive(self) -> None:
        deck = parse_deck_text(
            "// Deck: Burn\n// Format: modern\n// Author: me\n"
            "// Description: fast\n// Source: https://x\n// Tags: aggro, red\n"
            "// a note\n"
            "CMP: 1 Lurrus of the Dream-Den\n"
            "4 Lightning Bolt  #core  // best\n"
            "MB: 1 Opt\n"
            "SB: 2 Duress\n"
            "VS: Tron  // go fast\n"
            "    -2 Lightning Bolt\n"
            "    +2 Duress\n"
        )
        text = structured_deck_text(deck)
        for line in (
            "// Author: me", "// Description: fast", "// Source: https://x",
            "// Tags: aggro, red", "// a note",
            "CMP:\n    1 Lurrus of the Dream-Den",
            "DCK:\n    4 Lightning Bolt  #core  // best",
            "SB:\n    2 Duress",
            "MB:\n    1 Opt",
            "VS: Tron  // go fast\n    -2 Lightning Bolt\n    +2 Duress",
        ):
            assert line in text, line
        reparsed = parse_deck_text(text)
        assert reparsed.metadata == deck.metadata

        def plans(d: Any) -> list[Any]:
            return [
                (p.name, p.note, [(e.sign, e.quantity, e.card_name) for e in p.entries])
                for p in d.plans
            ]

        def entries(d: Any) -> list[Any]:
            return sorted(
                (e.section.value, e.quantity, e.card_name, e.tags, e.comment)
                for e in d.entries
            )

        assert plans(reparsed) == plans(deck)
        assert entries(reparsed) == entries(deck)


class _BrokenRepo:
    """A card repository whose database is damaged mid-session."""

    def get_by_name(self, name: str) -> None:
        import sqlite3

        raise sqlite3.DatabaseError("database disk image is malformed")

    def get_by_names(self, names: list[str]) -> None:
        import sqlite3

        raise sqlite3.DatabaseError("database disk image is malformed")


def test_damaged_card_database_degrades_to_typed_names() -> None:
    service = ImportExportService(card_repo=_BrokenRepo())  # type: ignore[arg-type]
    deck = service.import_deck("Sol Ring\n4 Fire/Ice\n", DeckFormat.MTGO)
    assert [(e.quantity, e.card_name) for e in deck.entries] == [
        (1, "Sol Ring"), (4, "Fire/Ice"),
    ]
