"""Tests for CLI commands: new, validate, info."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from vimtg.cli import main

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# --- new command ---


def test_new_creates_file(runner: CliRunner, tmp_path: Path) -> None:
    output_path = tmp_path / "dragons.deck"
    result = runner.invoke(main, ["new", "Dragons", "-o", str(output_path)])
    assert result.exit_code == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "// Deck: Dragons" in content


def test_new_with_format(runner: CliRunner, tmp_path: Path) -> None:
    output_path = tmp_path / "elves.deck"
    result = runner.invoke(main, ["new", "Elves", "-f", "standard", "-o", str(output_path)])
    assert result.exit_code == 0
    content = output_path.read_text(encoding="utf-8")
    assert "// Format: standard" in content


def test_new_default_path(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(main, ["new", "Burn"])
    assert result.exit_code == 0
    default_path = tmp_path / "Burn.deck"
    assert default_path.exists()


# --- validate command ---


def test_validate_valid(runner: CliRunner) -> None:
    deck_path = FIXTURES_DIR / "sample_burn.deck"
    result = runner.invoke(main, ["validate", str(deck_path)])
    assert result.exit_code == 0


def test_validate_shows_warnings(runner: CliRunner, tmp_path: Path) -> None:
    deck_file = tmp_path / "small.deck"
    deck_file.write_text("// Deck: Small\n4 Lightning Bolt\n", encoding="utf-8")
    result = runner.invoke(main, ["validate", str(deck_file)])
    # Should warn about small mainboard
    assert "warning" in result.output.lower()


# --- info command ---


def test_info_output(runner: CliRunner) -> None:
    deck_path = FIXTURES_DIR / "sample_burn.deck"
    result = runner.invoke(main, ["info", str(deck_path)])
    assert result.exit_code == 0
    assert "Burn" in result.output
    assert "60" in result.output
    assert "15" in result.output
