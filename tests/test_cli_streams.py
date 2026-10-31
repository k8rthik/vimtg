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


def test_cli_output_is_plain_text_in_a_pipe_and_under_no_color(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI styles nothing, so a pipe or NO_COLOR=1 always gets plain
    text: no ANSI escape on stdout or stderr, even when click would
    allow colour (color=True stands in for a terminal)."""
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    bad = tmp_path / "bad.deck"
    bad.write_text("// Format: modern\n4 Lightning Bolt\nMountain\n", encoding="utf-8")
    good = tmp_path / "good.deck"
    good.write_text("// Format: modern\n4 Lightning Bolt\n56 Mountain\n", encoding="utf-8")
    commands = (
        ["validate", str(bad)],
        ["validate", "--json", str(bad)],
        ["info", str(good)],
        ["diff", str(good), str(bad)],
        ["hand", "--seed", "1", str(good)],
        ["guide", str(good)],
        ["convert", str(good), "--to", "arena"],
    )
    for color in (False, True):
        runner = CliRunner(env={"NO_COLOR": "1"} if color else {})
        for args in commands:
            result = runner.invoke(main, args, color=color)
            assert result.exception is None or isinstance(result.exception, SystemExit)
            assert "\x1b" not in result.stdout + result.stderr, args
