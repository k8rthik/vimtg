"""`vimtg info`: every zone, the effective format, and the stats line."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from vimtg import cli
from vimtg.cli import main
from vimtg.data.card_repository import CardRepository

_DECK = (
    "// Deck: Lurrus Burn\n"
    "CMP: 1 Lurrus of the Dream-Den\n"
    "4 Lightning Bolt\n"
    "52 Mountain\n"
    "SB: 2 Fire/Ice\n"
    "MB: 1 Sol Ring\n"
)


@pytest.fixture
def deck_file(tmp_path: Path) -> Path:
    path = tmp_path / "lurrus.deck"
    path.write_text(_DECK, encoding="utf-8")
    return path


def _no_card_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)


def test_info_lists_every_zone(deck_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_card_db(monkeypatch)
    result = CliRunner().invoke(main, ["info", str(deck_file)])
    assert result.exit_code == 0, result.output
    assert result.output == (
        "Deck:       Lurrus Burn\n"
        "Format:     (none)\n"
        "Companion:  1 card (1 unique)\n"
        "Mainboard:  56 cards (2 unique)\n"
        "Sideboard:  2 cards (1 unique)\n"
        "Maybeboard: 1 card (1 unique)\n"
    )


def test_info_names_the_default_format(
    deck_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vimtg.config.paths import config_dir

    _no_card_db(monkeypatch)
    config_dir().mkdir(parents=True, exist_ok=True)
    (config_dir() / "config.toml").write_text(
        '[editor]\ndefault_format = "modern"\n', encoding="utf-8"
    )
    result = CliRunner().invoke(main, ["info", str(deck_file)])
    assert "Format:     modern (default_format)\n" in result.output


def _stats_row(output: str) -> str:
    rows = [line for line in output.splitlines() if line.startswith("Stats:")]
    assert len(rows) == 1, output
    return rows[0]


def test_info_prints_the_stats_line(
    deck_file: Path, monkeypatch: pytest.MonkeyPatch, real_shape_repo: CardRepository
) -> None:
    """Card count, average CMC, cards per type and the price with its source."""
    monkeypatch.setattr(cli, "_try_card_repo", lambda: real_shape_repo)
    result = CliRunner().invoke(main, ["info", str(deck_file)])
    assert result.exit_code == 0, result.output
    row = _stats_row(result.output)
    assert row.startswith("Stats:      ")
    assert "Avg CMC" in row
    assert "(usd)" in row


def test_info_stats_follow_the_price_source_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_shape_repo: CardRepository
) -> None:
    from vimtg.config.paths import config_dir

    monkeypatch.setattr(cli, "_try_card_repo", lambda: real_shape_repo)
    config_dir().mkdir(parents=True, exist_ok=True)
    (config_dir() / "config.toml").write_text(
        '[editor]\nprice_source = "eur"\n', encoding="utf-8"
    )
    deck = tmp_path / "fable.deck"
    deck.write_text("// Deck: Fable\n2 Fable of the Mirror-Breaker\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["info", str(deck)])
    assert result.exit_code == 0, result.output
    assert _stats_row(result.output).endswith("€30.00 (eur)")


def test_info_warns_about_cards_without_a_quantity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_shape_repo: CardRepository
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: real_shape_repo)
    deck = tmp_path / "burn.deck"
    deck.write_text("// Deck: Burn\nLightning Bolt\n4x Shock\n56 Mountain\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["info", str(deck)])
    assert result.exit_code == 0, result.output
    assert result.stderr == (
        "burn.deck:2: warning: not a card line: add a quantity (1 Lightning Bolt)\n"
        "burn.deck:3: warning: not a card line: drop the x (4 Shock)\n"
    )
    assert "Mainboard:  56 cards (1 unique)\n" in result.stdout


def test_validate_warns_about_cards_without_a_quantity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_shape_repo: CardRepository
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: real_shape_repo)
    deck = tmp_path / "burn.deck"
    deck.write_text(
        "// Deck: Burn\n// Format: modern\nLightning Bolt\n60 Mountain\n", encoding="utf-8"
    )
    result = CliRunner().invoke(main, ["validate", str(deck)])
    assert result.exit_code == 0, result.output
    assert (
        "burn.deck:3: warning: not a card line: add a quantity (1 Lightning Bolt)"
        in result.output
    )
    strict = CliRunner().invoke(main, ["validate", "--strict", str(deck)])
    assert strict.exit_code == 1
