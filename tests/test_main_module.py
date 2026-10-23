"""``python -m vimtg`` entry point and an end-to-end CLI smoke path."""

from __future__ import annotations

import importlib
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from vimtg import __version__
from vimtg.cli import main


def test_importing_main_module_does_not_launch_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    # Guarded by ``if __name__ == "__main__"``: a plain import (tooling,
    # coverage, docs builds) must not parse sys.argv or start the TUI.
    monkeypatch.setattr(sys, "argv", ["vimtg", "--definitely-not-an-option"])
    sys.modules.pop("vimtg.__main__", None)
    module = importlib.import_module("vimtg.__main__")
    assert module.main is main


def test_run_as_main_invokes_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["vimtg", "--version"])
    sys.modules.pop("vimtg.__main__", None)
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("vimtg", run_name="__main__")
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_python_dash_m_vimtg_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "vimtg", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert __version__ in result.stdout


def test_cli_smoke_new_info_validate(tmp_path: Path) -> None:
    runner = CliRunner()
    deck = tmp_path / "smoke.deck"

    created = runner.invoke(main, ["new", "Smoke", "-f", "modern", "-o", str(deck)])
    assert created.exit_code == 0, created.output
    assert deck.exists()

    # An empty scaffold is a valid file but not a legal deck.
    empty = runner.invoke(main, ["validate", str(deck)])
    assert empty.exit_code == 1
    assert "No mainboard cards" in empty.output

    with deck.open("a", encoding="utf-8") as f:
        f.write("    4 Lightning Bolt\n    20 Mountain\n")

    info = runner.invoke(main, ["info", str(deck)])
    assert info.exit_code == 0, info.output
    assert "Smoke" in info.output
    assert "modern" in info.output
    assert "Mainboard:  24 cards (2 unique)" in info.output

    # Without a card database legality is skipped; size warnings remain and
    # warnings alone do not fail validation.
    validated = runner.invoke(main, ["validate", str(deck)])
    assert validated.exit_code == 0, validated.output
    assert "minimum 60" in validated.output
