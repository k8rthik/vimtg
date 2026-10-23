"""ImportExportService.to_vimtg: the one import pipeline behind :import,
the editor's URL import, the greeter and `vimtg convert`."""

from __future__ import annotations

from vimtg.data.card_repository import CardRepository
from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection
from vimtg.services.deck_sources import RemoteDeck, SkippedLine
from vimtg.services.import_export_service import DeckFormat, ImportExportService

_MTGO = "4 lightning bolt\n2 Stomp\n20 Mountain\n4 Frobnicator\n\n2 fire/ice\n"

_REMOTE = RemoteDeck(
    name="Mono Red",
    deck=Deck(
        metadata=DeckMetadata(),
        entries=(
            DeckEntry(4, "lightning bolt", DeckSection.MAIN),
            DeckEntry(2, "Lightning Bolt", DeckSection.MAIN),
            DeckEntry(20, "Mountain", DeckSection.MAIN),
        ),
        comments=(),
    ),
    skipped=(SkippedLine(3, "???"),),
    format="modern",
)
_URL = "https://moxfield.com/decks/abc"


class TestTextImport:
    def test_names_are_canonical_and_grouped_by_type(
        self, real_shape_repo: CardRepository
    ) -> None:
        result = ImportExportService(card_repo=real_shape_repo).to_vimtg(_MTGO, name="burn")
        assert result.text.startswith("// Deck: burn\n// Format:\n")
        assert "    // Instants\n    4 Lightning Bolt\n" in result.text
        assert "    2 Bonecrusher Giant // Stomp\n" in result.text
        assert "SB:\n    2 Fire // Ice\n" in result.text
        assert result.resolution.unresolved == ("Frobnicator",)

    def test_without_card_data_names_stay_as_typed(self) -> None:
        result = ImportExportService().to_vimtg(_MTGO)
        assert "    4 lightning bolt\n" in result.text
        assert "// Instant" not in result.text

    def test_a_vimtg_deck_comes_in_verbatim(self, real_shape_repo: CardRepository) -> None:
        text = "// Deck: Burn\n\n// my notes\n4 lightning bolt\r\n"
        result = ImportExportService(card_repo=real_shape_repo).to_vimtg(text, name="other")
        assert result.text == "// Deck: Burn\n\n// my notes\n4 lightning bolt\n"

    def test_skipped_lines_are_reported(self) -> None:
        result = ImportExportService().to_vimtg(
            "Count,Name,Section\n4,Lightning Bolt,mainboard\n2,,sideboard\n",
            fmt=DeckFormat.MOXFIELD,
        )
        assert [s.line_number for s in result.skipped] == [3]


class TestRemoteImport:
    def test_remote_deck_is_stamped_resolved_and_merged(
        self, real_shape_repo: CardRepository
    ) -> None:
        result = ImportExportService(card_repo=real_shape_repo).to_vimtg(_REMOTE, url=_URL)
        assert result.text.startswith("// Deck: Mono Red\n// Format: modern\n")
        assert f"// Source: {_URL}\n" in result.text
        assert "    6 Lightning Bolt\n" in result.text
        assert "    // Lands\n    20 Mountain\n" in result.text
        assert result.skipped == _REMOTE.skipped

    def test_without_card_data_duplicates_still_merge(self) -> None:
        result = ImportExportService().to_vimtg(_REMOTE, url=_URL)
        assert "    6 lightning bolt\n" in result.text


class TestSummary:
    def test_summary_names_every_problem(self, real_shape_repo: CardRepository) -> None:
        result = ImportExportService(card_repo=real_shape_repo).to_vimtg(_MTGO + "??? what\n")
        assert result.summary("list.txt") == (
            "Imported 32 cards from list.txt"
            " | 1 line(s) skipped (line 7: ??? what)"
            " | W100: 1 cards not found in database"
            " | no format: fill in // Format: for legality checks"
        )

    def test_remote_summary_names_the_deck(self, real_shape_repo: CardRepository) -> None:
        result = ImportExportService(card_repo=real_shape_repo).to_vimtg(_REMOTE, url=_URL)
        assert result.summary("moxfield.com") == (
            "Imported 26 cards from moxfield.com — Mono Red | 1 line(s) skipped (line 3: ???)"
        )
