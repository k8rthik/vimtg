"""Tests for CLI commands: new, validate, info, convert."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from vimtg import cli
from vimtg.cli import main
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def loaded_repo(db_factory: Callable[..., Database]) -> CardRepository:
    repo = CardRepository(db_factory())
    with open(FIXTURES_DIR / "scryfall_sample.json") as f:
        repo.bulk_insert([Card.from_scryfall(d) for d in json.load(f)])
    return repo


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


# --- convert command ---


def test_convert_to_mtgo(runner: CliRunner) -> None:
    deck_path = FIXTURES_DIR / "sample_burn.deck"
    result = runner.invoke(main, ["convert", str(deck_path), "--to", "mtgo"])
    assert result.exit_code == 0
    assert "4 Lightning Bolt" in result.output
    assert "Sideboard" in result.output


def test_convert_to_file(runner: CliRunner, tmp_path: Path) -> None:
    deck_path = FIXTURES_DIR / "sample_burn.deck"
    out = tmp_path / "burn.txt"
    result = runner.invoke(main, ["convert", str(deck_path), "--to", "mtgo", "-o", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Lightning Bolt" in content


def test_convert_roundtrip_vimtg(runner: CliRunner, tmp_path: Path) -> None:
    """Convert vimtg -> mtgo -> vimtg preserves card names."""
    deck_path = FIXTURES_DIR / "sample_burn.deck"
    mtgo_out = tmp_path / "burn.mtgo"
    runner.invoke(main, ["convert", str(deck_path), "--to", "mtgo", "-o", str(mtgo_out)])

    result = runner.invoke(main, ["convert", str(mtgo_out), "--from", "mtgo", "--to", "vimtg"])
    assert result.exit_code == 0
    assert "Lightning Bolt" in result.output


# --- version / entry point ---


def test_version_flag(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "vimtg, version 0.1.0" in result.output


def test_help_lists_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for sub in ("sync", "edit", "search", "new", "validate", "convert", "guide"):
        assert sub in result.output


def test_make_card_repo_initializes_db() -> None:
    # XDG dirs are isolated per-test, so this builds a fresh throwaway db.
    repo = cli._make_card_repo()
    try:
        assert repo.count() == 0
    finally:
        repo._db.close()


# --- validate error exit path ---


def test_validate_with_error_exits_nonzero(
    runner: CliRunner, tmp_path: Path
) -> None:
    deck_file = tmp_path / "bad.deck"
    deck_file.write_text("// Deck: Bad\n\n0 Lightning Bolt\n", encoding="utf-8")
    result = runner.invoke(main, ["validate", str(deck_file)])
    assert result.exit_code == 1
    assert "error:" in result.output


# --- search command ---


def test_search_outputs_results(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["search", "bolt"])
    assert result.exit_code == 0
    assert "Lightning Bolt" in result.output


def test_search_no_results(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["search", "zzzznotacard"])
    assert result.exit_code == 0
    assert "No cards found." in result.output


# --- sync command ---


def test_sync_command_reports_count(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)

    fake_sync = MagicMock(return_value=42)
    monkeypatch.setattr(cli.ScryfallSync, "sync", fake_sync)
    result = runner.invoke(main, ["sync"])
    assert result.exit_code == 0
    assert "Synced 42 cards" in result.output


def test_sync_progress_output(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)

    def fake_sync(self, force=False, progress=None):  # type: ignore[no-untyped-def]
        if progress:
            progress("download", 50, 100)
            progress("parse", 5, 10)
        return 7

    monkeypatch.setattr(cli.ScryfallSync, "sync", fake_sync)
    result = runner.invoke(main, ["sync", "--force"])
    assert result.exit_code == 0
    assert "Downloading... 50%" in result.output
    assert "Parsing... 5/10" in result.output


# --- editor launch paths (app is mocked to avoid a real TUI) ---


def test_edit_launches_app(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_app = MagicMock()
    fake_app_cls = MagicMock(return_value=fake_app)
    import vimtg.tui.app as app_mod

    monkeypatch.setattr(app_mod, "VimTGApp", fake_app_cls)
    result = runner.invoke(main, ["edit", "deck.deck"])
    assert result.exit_code == 0
    fake_app.run.assert_called_once()


def test_no_subcommand_launches_app(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_app = MagicMock()
    fake_app_cls = MagicMock(return_value=fake_app)
    import vimtg.tui.app as app_mod

    monkeypatch.setattr(app_mod, "VimTGApp", fake_app_cls)
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    fake_app.run.assert_called_once()


# --- format-aware validate ---


def test_validate_format_rules_without_db(
    runner: CliRunner, tmp_path: Path
) -> None:
    deck_file = tmp_path / "cmd.deck"
    deck_file.write_text(
        "// Format: commander\nCMD: 1 Atraxa\n2 Sol Ring\n96 Island\n",
        encoding="utf-8",
    )
    result = runner.invoke(main, ["validate", str(deck_file)])
    assert result.exit_code == 1
    assert "Sol Ring" in result.output
    assert "exactly 100" in result.output


def test_validate_notes_missing_db_when_format_set(
    runner: CliRunner, tmp_path: Path
) -> None:
    deck_file = tmp_path / "m.deck"
    deck_file.write_text(
        "// Format: modern\n" + "".join(f"1 Card{i}\n" for i in range(60)),
        encoding="utf-8",
    )
    result = runner.invoke(main, ["validate", str(deck_file)])
    assert "no card database" in result.output
    assert result.exit_code == 0


def test_validate_line_numbers_in_output(
    runner: CliRunner, tmp_path: Path
) -> None:
    deck_file = tmp_path / "q.deck"
    deck_file.write_text("// Deck: X\n0 Bolt\n", encoding="utf-8")
    result = runner.invoke(main, ["validate", str(deck_file)])
    assert "q.deck:2:" in result.output


class TestDeckFileFallback:
    """`vimtg burn.deck` opens the editor, vim-style."""

    def test_existing_deck_file_routes_to_edit(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        deck = tmp_path / "burn.deck"
        deck.write_text("4 Lightning Bolt\n")
        launched = MagicMock()
        monkeypatch.setattr(cli, "_launch_editor", launched)
        result = runner.invoke(main, [str(deck)])
        assert result.exit_code == 0
        launched.assert_called_once_with(str(deck))

    def test_new_deck_path_routes_to_edit(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        launched = MagicMock()
        monkeypatch.setattr(cli, "_launch_editor", launched)
        result = runner.invoke(main, [str(tmp_path / "brand-new.deck")])
        assert result.exit_code == 0
        launched.assert_called_once()

    def test_unknown_command_still_errors(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["snc"])
        assert result.exit_code != 0
        assert "No such command" in result.output

    def test_real_subcommands_unaffected(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        deck = tmp_path / "x.deck"
        deck.write_text("// Deck: X\n4 Bolt\n56 Mountain\n")
        result = runner.invoke(main, ["info", str(deck)])
        assert result.exit_code == 0
        assert "Mainboard" in result.output


_PLAN_DECK = (
    "// Deck: Burn\n// Format: modern\n\n4 Lightning Bolt\nSB: 3 Alpine Moon\n\n"
    "VS: Tron\n    -4 Lightning Bolt\n    +3 Alpine Moon\n\n"
    "VS: Burn\n    -2 Lightning Bolt\n"
)


def test_guide_lists_plans(runner: CliRunner, tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text(_PLAN_DECK, encoding="utf-8")
    result = runner.invoke(main, ["guide", str(deck)])
    assert result.exit_code == 0
    assert "vs Tron  -4 +3 !" in result.output
    assert "  -4 Lightning Bolt" in result.output
    assert "  +3 Alpine Moon" in result.output
    assert "vs Burn  -2 +0 !" in result.output


def test_guide_markdown(runner: CliRunner, tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text(_PLAN_DECK, encoding="utf-8")
    result = runner.invoke(main, ["guide", str(deck), "--markdown"])
    assert result.exit_code == 0
    assert result.output.startswith("# Burn — sideboard guide")


def test_guide_without_plans(runner: CliRunner, tmp_path: Path) -> None:
    deck = tmp_path / "plain.deck"
    deck.write_text("4 Lightning Bolt\n", encoding="utf-8")
    result = runner.invoke(main, ["guide", str(deck)])
    assert result.exit_code == 0
    assert "No sideboard plans" in result.output


def test_validate_reports_plan_issues(runner: CliRunner, tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text("4 Lightning Bolt\n\nVS: Tron\n    +1 Lightning Bolt\n", encoding="utf-8")
    result = runner.invoke(main, ["validate", str(deck)])
    assert result.exit_code == 1
    assert "burn.deck:4: error: Lightning Bolt is not in the sideboard" in result.output
