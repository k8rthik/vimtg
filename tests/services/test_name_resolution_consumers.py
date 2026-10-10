"""Every consumer of resolved cards sees the same resolution.

A deck written the way MTGO / Arena / Moxfield write it (front-face
names, "Fire/Ice", lowercase) must lint clean, validate, produce stats,
export with set codes and render card details — not "Card not found"
or empty stats.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from vimtg import cli
from vimtg.cli import main
from vimtg.data.card_repository import CardRepository
from vimtg.data.deck_repository import DeckRepository, parse_deck_text
from vimtg.domain.analytics import compute_stats
from vimtg.domain.card import Color
from vimtg.domain.validation import validate_deck
from vimtg.editor.buffer import Buffer
from vimtg.editor.lint import lint_buffer
from vimtg.editor.session import resolve_cards
from vimtg.services.deck_service import DeckService
from vimtg.services.import_export_service import DeckFormat, ImportExportService
from vimtg.tui.deck_renderer import render_line

DECK = """\
// Format: modern
4 Fable of the Mirror-Breaker
4 Bonecrusher Giant
2 Fire/Ice
3 Valakut Awakening
4 lightning bolt
4 Delver of Secrets
"""


@pytest.fixture
def deck_service(real_shape_repo: CardRepository) -> DeckService:
    return DeckService(deck_repo=DeckRepository(), card_repo=real_shape_repo)


def test_every_name_resolves(deck_service: DeckService) -> None:
    resolved, unresolved = deck_service.resolve_cards(parse_deck_text(DECK))
    assert unresolved == []
    assert len({c.scryfall_id for c in resolved.values()}) == 6


def test_validate_reports_no_unknown_cards(deck_service: DeckService) -> None:
    deck = parse_deck_text(DECK)
    resolved, _ = deck_service.resolve_cards(deck)
    errors = validate_deck(deck, resolved, "modern")
    assert not [e for e in errors if "Card not found" in e.message]


def test_lint_has_no_card_not_found(real_shape_repo: CardRepository) -> None:
    buf = Buffer.from_text(DECK)
    result = lint_buffer(buf, resolve_cards(buf, real_shape_repo))
    messages = [e.message for e in result.line_errors.values()]
    assert not [m for m in messages if "Card not found" in m]


def test_stats_count_lowercase_and_face_names(deck_service: DeckService) -> None:
    deck = parse_deck_text(DECK)
    resolved, _ = deck_service.resolve_cards(deck)
    stats = compute_stats(deck, resolved)
    # All 21 mainboard cards resolved (each is counted land or nonland)
    assert stats.land_count + stats.nonland_count == 21
    assert stats.average_cmc > 0
    # Bolt (lowercase), Fable (front face, colours on its faces),
    # Bonecrusher and Fire/Ice all count as red
    assert stats.color_distribution.cards[Color.RED] >= 4 + 4 + 4 + 2


def test_export_moxfield_includes_editions(deck_service: DeckService) -> None:
    deck = parse_deck_text(DECK)
    resolved, _ = deck_service.resolve_cards(deck)
    out = ImportExportService().export_deck(deck, DeckFormat.MOXFIELD, resolved=resolved)
    assert "4,lightning bolt,CLU," in out
    assert "4,Fable of the Mirror-Breaker,NEO," in out
    assert "2,Fire/Ice,MH2," in out


def test_import_resolution_uses_face_names(real_shape_repo: CardRepository) -> None:
    service = ImportExportService(card_repo=real_shape_repo)
    deck = service.import_deck("4 Fable of the Mirror-Breaker\n2 Fire/Ice\n", DeckFormat.MTGO)
    resolution = service.resolve_cards(deck)
    assert resolution.unresolved == ()
    assert set(resolution.resolved) == {"Fable of the Mirror-Breaker", "Fire/Ice"}


def test_render_shows_details_for_lowercase_face_name(
    real_shape_repo: CardRepository,
) -> None:
    buf = Buffer.from_text("4 valakut awakening\n")
    lines = render_line(0, buf, cursor_row=0, resolved=resolve_cards(buf, real_shape_repo))
    assert len(lines) >= 2
    assert "Instant" in lines[1].plain


class TestCli:
    def test_search_color_finds_dfcs(
        self, real_shape_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli, "_make_card_repo", lambda: real_shape_repo)
        result = CliRunner().invoke(main, ["search", "c:r", "-n", "50"])
        assert result.exit_code == 0
        assert "Fable of the Mirror-Breaker" in result.output
        assert "Valakut Awakening" in result.output

    def test_validate_resolves_face_names(
        self,
        real_shape_repo: CardRepository,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(cli, "_try_card_repo", lambda: real_shape_repo)
        path = tmp_path / "deck.deck"
        path.write_text(DECK, encoding="utf-8")
        result = CliRunner().invoke(main, ["validate", str(path)])
        assert "Card not found" not in result.output
