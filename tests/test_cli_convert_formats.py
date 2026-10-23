"""`vimtg convert` speaks every :export format and reads deck URLs."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from vimtg.cli import main
from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection
from vimtg.services.deck_sources import RemoteDeck
from vimtg.services.import_export_service import FORMAT_NAMES

_DECK = "// Deck: Burn\n\n4 Lightning Bolt\n\nSB: 2 Smash to Smithereens\n"
_URL = "https://moxfield.com/decks/abc123"


@pytest.fixture
def deck_file(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(_DECK, encoding="utf-8")
    return path


def test_convert_writes_mtgo_dek(deck_file: Path) -> None:
    result = CliRunner().invoke(main, ["convert", str(deck_file), "--to", "dek"])
    assert result.exit_code == 0, result.output
    assert '<Cards Quantity="4" Sideboard="false" Name="Lightning Bolt" />' in result.output
    assert '<Cards Quantity="2" Sideboard="true" Name="Smash to Smithereens" />' in result.output


def test_convert_mtga_is_arena(deck_file: Path) -> None:
    runner = CliRunner()
    mtga = runner.invoke(main, ["convert", str(deck_file), "--to", "mtga"])
    arena = runner.invoke(main, ["convert", str(deck_file), "--to", "arena"])
    assert mtga.exit_code == 0, mtga.output
    assert mtga.output == arena.output


def test_convert_reads_a_dek_file(tmp_path: Path) -> None:
    dek = tmp_path / "burn.dek"
    dek.write_text(
        '<?xml version="1.0"?><Deck>'
        '<Cards Quantity="4" Sideboard="false" Name="Lightning Bolt" /></Deck>',
        encoding="utf-8",
    )
    result = CliRunner().invoke(main, ["convert", str(dek), "--from", "dek", "--to", "mtgo"])
    assert result.exit_code == 0, result.output
    assert result.output == "4 Lightning Bolt\n\n"


def test_every_export_format_is_a_convert_target() -> None:
    result = CliRunner().invoke(main, ["convert", "--help"])
    for name in FORMAT_NAMES:
        assert name in result.output


def test_convert_reads_a_deck_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import vimtg.services.deck_sources as ds

    remote = RemoteDeck(
        name="Mono Red",
        deck=Deck(
            metadata=DeckMetadata(),
            entries=(DeckEntry(4, "Lightning Bolt", DeckSection.MAIN),),
            comments=(),
        ),
    )
    monkeypatch.setattr(ds, "fetch_deck", lambda url: remote)
    result = CliRunner().invoke(main, ["convert", _URL, "--to", "vimtg"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("// Deck: Mono Red\n")
    assert f"// Source: {_URL}\n" in result.output


def test_convert_url_offline_is_a_friendly_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import vimtg.services.deck_sources as ds

    def offline(*args: object, **kwargs: object) -> object:
        raise httpx.ConnectError("[Errno 8] nodename nor servname provided")

    monkeypatch.setattr(ds.httpx, "get", offline)
    result = CliRunner().invoke(main, ["convert", _URL, "--to", "arena"])
    assert result.exit_code == 1
    assert "Error: Could not reach api2.moxfield.com — you seem to be offline" in result.output
    assert "Traceback" not in result.output


def test_convert_missing_file_is_an_error(tmp_path: Path) -> None:
    result = CliRunner().invoke(main, ["convert", str(tmp_path / "nope.deck"), "--to", "arena"])
    assert result.exit_code != 0
    assert "nope.deck" in result.output
    assert "does not exist" in result.output
