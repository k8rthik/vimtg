"""CLI notes and errors go to stderr; the command's own output to stdout."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from vimtg import cli
from vimtg.cli import main


@pytest.fixture
def deck_file(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text("// Format: modern\n4 Lightning Bolt\n56 Mountain\n", encoding="utf-8")
    return path


def test_validate_notes_go_to_stderr(deck_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    result = CliRunner().invoke(main, ["validate", str(deck_file)])
    assert result.exit_code == 0, result.output
    assert result.stdout == "burn.deck: ok (modern)\n"
    assert result.stderr == (
        "(no card database — legality checks skipped; run 'vimtg sync')\n"
    )


def test_validate_strict_error_goes_to_stderr(
    deck_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    result = CliRunner().invoke(main, ["validate", "--strict", str(deck_file)])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "--strict needs a card database" in result.stderr
