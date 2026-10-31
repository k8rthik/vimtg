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
    with open(FIXTURES_DIR / "scryfall_sample.json", encoding="utf-8") as f:
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
    assert "vimtg, version 1.0.0rc1" in result.output


def test_help_lists_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for sub in ("sync", "search", "new", "validate", "convert", "guide", "tutor", "info"):
        assert sub in result.output
    assert "  edit" not in result.output


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


def test_search_applies_filters(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["search", "c:w"])
    assert result.exit_code == 0
    assert "Rest in Peace" in result.output
    assert "Lightning Bolt" not in result.output


def test_search_shows_full_split_cost(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["search", "fire"])
    assert result.exit_code == 0
    assert "{1}{R} // {1}{U}" in result.output


def test_search_without_card_data_says_to_sync(
    runner: CliRunner, db_factory: Callable[..., Database], monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = CardRepository(db_factory())
    monkeypatch.setattr(cli, "_make_card_repo", lambda: empty)
    result = runner.invoke(main, ["search", "bolt"])
    assert result.exit_code == 1
    assert "no card database (run 'vimtg sync' first)" in result.output


def _write_config(text: str) -> None:
    from vimtg.config.paths import config_dir

    config_dir().mkdir(parents=True, exist_ok=True)
    (config_dir() / "config.toml").write_text(text, encoding="utf-8")


def test_search_prices_follow_price_source(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config('[editor]\nprice_source = "eur"\n')
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["search", "!\"Lightning Bolt\""])
    assert result.exit_code == 0, result.output
    assert result.output.rstrip().endswith("\u20ac1.20")
    assert "$" not in result.output


def test_search_hides_prices_when_show_prices_is_off(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config("[editor]\nshow_prices = false\n")
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["search", "!\"Lightning Bolt\""])
    assert result.exit_code == 0, result.output
    assert "1.50" not in result.output
    assert result.output.rstrip().endswith("STA")


def test_search_no_results(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["search", "zzzznotacard"])
    assert result.exit_code == 0
    assert "No cards found." in result.output


@pytest.mark.parametrize("query", [["mv>"], ["t:creature", "mv>"], ["-t:"], ["(c:)"]])
def test_search_incomplete_term_is_an_error(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch,
    query: list[str],
) -> None:
    """`vimtg search "mv>"` used to print "No cards found."."""
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["search", "--", *query])
    assert result.exit_code == 1
    assert "needs a value" in result.output
    assert "No cards found." not in result.output


@pytest.mark.parametrize("query", ['o:"deals 3: damage"', "o:/x: y/", "Fire // Ice"])
def test_search_colon_inside_a_value_is_not_an_empty_term(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["search", query])
    assert result.exit_code == 0, result.output


def test_top_level_help_shows_whole_search_summary(runner: CliRunner) -> None:
    """Click cut the summary at "e.g." ("...syntax, e.g.")."""
    result = runner.invoke(main, ["--help"])
    assert "Search for cards with Scryfall-style syntax." in result.output
    assert "e.g." not in result.output


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


def test_deck_path_launches_app(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_app = MagicMock()
    fake_app_cls = MagicMock(return_value=fake_app)
    import vimtg.tui.app as app_mod

    monkeypatch.setattr(app_mod, "VimTGApp", fake_app_cls)
    result = runner.invoke(main, ["deck.deck"])
    assert result.exit_code == 0, result.output
    fake_app.run.assert_called_once()
    assert fake_app_cls.call_args.kwargs["deck_path"] == Path("deck.deck")


def test_edit_is_not_a_subcommand(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`vimtg edit deck.deck` was the same as `vimtg deck.deck`."""
    fake_app_cls = MagicMock()
    import vimtg.tui.app as app_mod

    monkeypatch.setattr(app_mod, "VimTGApp", fake_app_cls)
    result = runner.invoke(main, ["edit", "deck.deck"])
    assert result.exit_code == 2
    assert "No such command 'edit'" in result.output
    fake_app_cls.assert_not_called()


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


def test_validate_names_the_editor_line_when_it_differs(
    runner: CliRunner, tmp_path: Path
) -> None:
    """The editor scaffolds '// Format:' / '// Tags:' and a blank line on
    open, so the file's line 2 is the editor's line 5: validate keeps the
    file line (what other tools jump to) and names the editor's."""
    deck_file = tmp_path / "q.deck"
    deck_file.write_text("// Deck: X\n0 Bolt\n", encoding="utf-8")
    result = runner.invoke(main, ["validate", str(deck_file)])
    assert "q.deck:2: error: Invalid quantity 0 for Bolt (line 5 in the vimtg editor)" in (
        result.output
    )


def test_validate_adds_no_note_when_editor_and_file_agree(
    runner: CliRunner, tmp_path: Path
) -> None:
    deck_file = tmp_path / "q.deck"
    deck_file.write_text(
        "// Deck: X\n// Format:\n// Tags:\n\n0 Bolt\n", encoding="utf-8",
    )
    result = runner.invoke(main, ["validate", str(deck_file)])
    assert "q.deck:5:" in result.output
    assert "vimtg editor" not in result.output


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


# --- validate --strict ---


def _burn_with_typo(tmp_path: Path) -> Path:
    deck_file = tmp_path / "typo.deck"
    deck_file.write_text(
        "// Format: modern\n4 Lightning Bolt\n4 Lightnig Bolt\n52 Mountain\n",
        encoding="utf-8",
    )
    return deck_file


def test_validate_reports_unknown_card_but_passes_without_strict(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    loaded_repo: CardRepository,
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["validate", str(_burn_with_typo(tmp_path))])
    assert "warning: Card not found: Lightnig Bolt" in result.output
    assert result.exit_code == 0


def test_validate_strict_fails_on_unknown_card(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    loaded_repo: CardRepository,
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: loaded_repo)
    result = runner.invoke(
        main, ["validate", "--strict", str(_burn_with_typo(tmp_path))]
    )
    assert "Card not found: Lightnig Bolt" in result.output
    assert result.exit_code == 1


def test_validate_strict_passes_clean_deck(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    loaded_repo: CardRepository,
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: loaded_repo)
    deck_file = tmp_path / "ok.deck"
    deck_file.write_text(
        "// Format: modern\n4 Lightning Bolt\n56 Mountain\n", encoding="utf-8"
    )
    result = runner.invoke(main, ["validate", "--strict", str(deck_file)])
    assert result.exit_code == 0, result.output


def test_validate_reports_unknown_when_no_card_resolves(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    loaded_repo: CardRepository,
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: loaded_repo)
    deck_file = tmp_path / "junk.deck"
    deck_file.write_text("60 Not A Card\n", encoding="utf-8")
    result = runner.invoke(main, ["validate", "--strict", str(deck_file)])
    assert "Card not found: Not A Card" in result.output
    assert result.exit_code == 1


def test_validate_strict_without_db_fails(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    deck_file = tmp_path / "m.deck"
    deck_file.write_text("60 Mountain\n", encoding="utf-8")
    result = runner.invoke(main, ["validate", "--strict", str(deck_file)])
    assert "--strict needs a card database" in result.output
    assert result.exit_code == 1


# --- file safety: `new` ---


def test_new_refuses_to_overwrite(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    deck = tmp_path / "Burn.deck"
    deck.write_text("4 Lightning Bolt\n", encoding="utf-8")
    result = runner.invoke(main, ["new", "Burn"])
    assert result.exit_code != 0
    assert "already exists" in result.output
    assert "--force" in result.output
    assert deck.read_text(encoding="utf-8") == "4 Lightning Bolt\n"


def test_new_refuses_to_overwrite_output(runner: CliRunner, tmp_path: Path) -> None:
    deck = tmp_path / "x.deck"
    deck.write_text("keep\n", encoding="utf-8")
    result = runner.invoke(main, ["new", "X", "-o", str(deck)])
    assert result.exit_code != 0
    assert deck.read_text(encoding="utf-8") == "keep\n"


def test_new_force_overwrites(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    deck = tmp_path / "Burn.deck"
    deck.write_text("old\n", encoding="utf-8")
    result = runner.invoke(main, ["new", "Burn", "--force"])
    assert result.exit_code == 0
    assert "// Deck: Burn" in deck.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["", "   ", "a/b", "a\\b", ".hidden", ".deck"])
def test_new_rejects_bad_names(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(main, ["new", name])
    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output
    assert list(tmp_path.iterdir()) == []


def test_new_does_not_double_deck_suffix(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(main, ["new", "t.deck"])
    assert result.exit_code == 0
    assert [p.name for p in tmp_path.iterdir()] == ["t.deck"]
    assert "// Deck: t\n" in (tmp_path / "t.deck").read_text(encoding="utf-8")


def test_new_slash_in_name_allowed_with_output(runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "rg.deck"
    result = runner.invoke(main, ["new", "R/G Aggro", "-o", str(out)])
    assert result.exit_code == 0
    assert "// Deck: R/G Aggro" in out.read_text(encoding="utf-8")


# --- friendly errors instead of tracebacks ---


def _assert_clean_error(result, *needles: str) -> None:  # type: ignore[no-untyped-def]
    assert result.exit_code == 1, result.output
    assert not isinstance(result.exception, OSError | UnicodeDecodeError)
    assert "Traceback" not in result.output
    assert "Error:" in result.output
    for needle in needles:
        assert needle in result.output


def test_info_non_utf8_file(runner: CliRunner, tmp_path: Path) -> None:
    deck = tmp_path / "latin1.deck"
    deck.write_bytes("4 Lim-Dûl's Vault\n".encode("latin-1"))
    result = runner.invoke(main, ["info", str(deck)])
    _assert_clean_error(result, "UTF-8", "Hint:")


def test_info_directory(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(main, ["info", str(tmp_path)])
    _assert_clean_error(result, "directory")


def test_convert_output_into_missing_directory(runner: CliRunner, tmp_path: Path) -> None:
    src = tmp_path / "in.txt"
    src.write_text("4 Lightning Bolt\n", encoding="utf-8")
    out = tmp_path / "nonexistent" / "x.txt"
    result = runner.invoke(main, ["convert", str(src), "--to", "mtgo", "-o", str(out)])
    _assert_clean_error(result, "No such file or directory", "Hint:")


def test_corrupt_database(runner: CliRunner) -> None:
    from vimtg.config.paths import db_path

    db_path().write_bytes(b"this is not a sqlite database" * 100)
    result = runner.invoke(main, ["search", "bolt"])
    assert result.exit_code == 1, result.output
    assert "card database" in result.output
    assert "vimtg sync" in result.output


def test_sync_failure_is_friendly(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    def boom(self, force=False, progress=None):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError("dns failure")

    monkeypatch.setattr(cli.ScryfallSync, "sync", boom)
    result = runner.invoke(main, ["sync"])
    assert result.exit_code == 1
    assert "run `vimtg sync` to retry" in result.output


def test_search_full_syntax_and_unquoted_terms(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI shares the overlay's parser; separate shell words are
    one query."""
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["search", "--", "-t:creature", "(c:w", "or", "c:u)"])
    assert result.exit_code == 0, result.output
    assert "Rest in Peace" in result.output
    assert "Fire // Ice" in result.output
    assert "Delver" not in result.output
    assert "Lightning Bolt" not in result.output


def test_search_unknown_key_is_an_error(
    runner: CliRunner, loaded_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_make_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["search", "foo:bar"])
    assert result.exit_code == 1
    assert "Unknown search key 'foo'" in result.output


def test_output_error_names_the_output_not_a_temp_file(
    runner: CliRunner, tmp_path: Path
) -> None:
    out = tmp_path / "nodir" / "x.deck"
    result = runner.invoke(main, ["new", "X", "-o", str(out)])
    _assert_clean_error(result, f"{out}: No such file or directory")
    assert ".tmp" not in result.output


@pytest.mark.parametrize("force", [[], ["--force"]])
def test_new_output_directory_is_refused(
    runner: CliRunner, tmp_path: Path, force: list[str]
) -> None:
    # Was "already exists (use --force…)", then a temp-file error with --force
    result = runner.invoke(main, ["new", "X", "-o", str(tmp_path), *force])
    assert result.exit_code == 1, result.output
    assert "is a directory (give a file path to -o)" in result.output
    assert "--force" not in result.output


def test_convert_output_directory_is_refused(runner: CliRunner, tmp_path: Path) -> None:
    src = tmp_path / "in.deck"
    src.write_text("4 Lightning Bolt\n", encoding="utf-8")
    out = tmp_path / "outdir"
    out.mkdir()
    result = runner.invoke(main, ["convert", str(src), "--to", "mtgo", "-o", str(out)])
    assert result.exit_code == 1, result.output
    assert "is a directory" in result.output


@pytest.mark.parametrize("limit", ["0", "-5"])
def test_search_limit_must_be_positive(runner: CliRunner, limit: str) -> None:
    # 0 printed "No cards found." and -5 meant "unlimited" (SQL LIMIT -5)
    result = runner.invoke(main, ["search", "-n", limit, "bolt"])
    assert result.exit_code == 2, result.output
    assert "--limit" in result.output


def test_validate_reports_unreadable_database_as_such(
    runner: CliRunner, tmp_path: Path
) -> None:
    from vimtg.config.paths import db_path

    db_path().write_bytes(b"this is not a sqlite database" * 100)
    deck = tmp_path / "d.deck"
    deck.write_text("// Format: modern\n4 Lightning Bolt\n", encoding="utf-8")
    result = runner.invoke(main, ["validate", str(deck)])
    assert "card database unreadable" in result.output
    assert "no card database" not in result.output


def test_validate_without_database_says_so(runner: CliRunner, tmp_path: Path) -> None:
    deck = tmp_path / "d.deck"
    deck.write_text("// Format: modern\n4 Lightning Bolt\n", encoding="utf-8")
    result = runner.invoke(main, ["validate", str(deck)])
    assert "(no card database — legality checks skipped" in result.output


def test_validate_works_when_data_dir_cannot_be_created(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The card database is optional for validate/convert: an unusable
    # data directory must not turn into "Error: …: Permission denied"
    def denied() -> Path:
        raise PermissionError(13, "Permission denied", str(tmp_path / "data"))

    monkeypatch.setattr(cli, "db_path", denied)
    deck = tmp_path / "d.deck"
    deck.write_text("4 Lightning Bolt\n", encoding="utf-8")
    result = runner.invoke(main, ["validate", str(deck)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(main, ["convert", str(deck), "--to", "mtgo"])
    assert result.exit_code == 0, result.output
    assert "4 Lightning Bolt" in result.output


def test_sync_unopenable_database_omits_tui_fallback_text(
    runner: CliRunner,
) -> None:
    from vimtg.config.paths import db_path

    db_path().mkdir()  # cannot be opened as a database file
    result = runner.invoke(main, ["sync"])
    assert result.exit_code == 1, result.output
    assert "Cannot open the card database" in result.output
    assert "Running without card data" not in result.output
