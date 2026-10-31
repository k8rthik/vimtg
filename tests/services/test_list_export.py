"""The plain list export: one 'N Name' line per card for tools that read
a bare decklist (MPC Autofill, store mass-entry boxes), so no headers,
no blank lines, front-face names, and a card in two zones listed once."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from vimtg.cli import main
from vimtg.data.card_repository import CardRepository
from vimtg.data.deck_repository import parse_deck_text
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.export_cmds import cmd_clipboard, cmd_export
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor
from vimtg.services.import_export_service import (
    FORMAT_NAMES,
    IMPORT_FORMAT_NAMES,
    DeckFormat,
    ImportExportService,
)

_DECK = (
    "// Deck: Proxies\n"
    "// Format: commander\n"
    "\n"
    "CMD: 1 Thrasios, Triton Hero\n"
    "CMP: 1 Lurrus of the Dream-Den\n"
    "\n"
    "// Spells\n"
    "4 Lightning Bolt  @removal  #burn\n"
    "1 Insectile Aberration\n"
    "1 Stomp  #value\n"
    "1 Fire/Ice  @removal\n"
    "\n"
    "SB: 2 lightning bolt\n"
    "SB: 1 Sol Ring  #ramp  // fast mana\n"
    "MB: 1 Rhystic Study\n"
)

_EXPECTED = (
    "1 Thrasios, Triton Hero\n"
    "1 Lurrus of the Dream-Den\n"
    "6 Lightning Bolt\n"
    "1 Delver of Secrets\n"
    "1 Bonecrusher Giant\n"
    "1 Fire\n"
    "1 Sol Ring\n"
)


def _resolved(repo: CardRepository, text: str) -> dict[str, Any]:
    deck = parse_deck_text(text)
    return dict(repo.get_by_names(sorted(deck.unique_card_names())))


def test_list_writes_one_front_face_line_per_card(
    real_shape_repo: CardRepository,
) -> None:
    out = ImportExportService().export_deck(
        parse_deck_text(_DECK), DeckFormat.LIST, resolved=_resolved(real_shape_repo, _DECK)
    )
    assert out == _EXPECTED


def test_list_without_card_data_splits_the_typed_name() -> None:
    text = (
        "CMD: 1 Esika, God of the Tree // The Prismatic Bridge\n"
        "2 Brazen Borrower // Petty Theft\n"
        "SB: 1 Brazen Borrower // Petty Theft\n"
        "MB: 1 Opt\n"
    )
    out = ImportExportService().export_deck(parse_deck_text(text), DeckFormat.LIST)
    assert out == "1 Esika, God of the Tree\n3 Brazen Borrower\n"


def test_list_names_and_aliases_are_export_only() -> None:
    assert FORMAT_NAMES["list"] is DeckFormat.LIST
    assert FORMAT_NAMES["mpc"] is DeckFormat.LIST
    assert FORMAT_NAMES["tcgplayer"] is DeckFormat.LIST
    assert not {"list", "mpc", "tcgplayer"} & set(IMPORT_FORMAT_NAMES)
    with pytest.raises(ValueError):
        ImportExportService().import_deck("4 Lightning Bolt\n", DeckFormat.LIST)


@pytest.mark.parametrize("name", ["list", "mpc", "tcgplayer"])
def test_convert_to_list(tmp_path: Path, name: str) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text(
        "// Deck: Burn\n\n4 Lightning Bolt\n\nSB: 2 Smash to Smithereens\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(main, ["convert", str(deck), "--to", name])
    assert result.exit_code == 0, result.output
    assert result.output == "4 Lightning Bolt\n2 Smash to Smithereens\n\n"


def test_convert_from_does_not_offer_the_list_format(tmp_path: Path) -> None:
    deck = tmp_path / "burn.txt"
    deck.write_text("4 Lightning Bolt\n", encoding="utf-8")
    result = CliRunner().invoke(
        main, ["convert", str(deck), "--from", "list", "--to", "arena"]
    )
    assert result.exit_code == 2


def test_export_list_writes_the_file(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    ctx = EditorContext()
    cmd = ParsedCommand(name="export", args=f"list {target}")
    cmd_export(Buffer.from_text(_DECK), Cursor(row=0), cmd, ctx)
    assert not ctx.error, ctx.message
    text = target.read_text(encoding="utf-8")
    assert "Sideboard" not in text
    assert text.endswith("1 Sol Ring\n")
    assert "Rhystic Study" not in text


def test_clipboard_list_copies_the_list(
    real_shape_repo: CardRepository,
) -> None:
    ctx = EditorContext(resolved_cards=_resolved(real_shape_repo, _DECK))
    cmd = ParsedCommand(name="clipboard", args="list")
    cmd_clipboard(Buffer.from_text(_DECK), Cursor(row=0), cmd, ctx)
    assert ctx.clipboard_text == _EXPECTED
    assert ctx.clipboard_label == "list (7 lines)"
