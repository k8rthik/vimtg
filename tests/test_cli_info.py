"""`vimtg info`: every zone, the effective format, and the :stats line."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from vimtg import cli
from vimtg.cli import main
from vimtg.data.card_repository import CardRepository
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.deck_cmds import cmd_stats
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor
from vimtg.editor.session import resolve_cards

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


def test_info_prints_the_stats_line(
    deck_file: Path, monkeypatch: pytest.MonkeyPatch, real_shape_repo: CardRepository
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: real_shape_repo)
    buffer = Buffer.from_text(_DECK)
    ctx = EditorContext(resolved_cards=resolve_cards(buffer, real_shape_repo))
    cmd_stats(buffer, Cursor(row=0), ParsedCommand(name="stats"), ctx)

    result = CliRunner().invoke(main, ["info", str(deck_file)])
    assert result.exit_code == 0, result.output
    assert f"Stats:      {ctx.message}\n" in result.output
