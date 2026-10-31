import tomllib
from pathlib import Path

from click.testing import CliRunner

from vimtg import __version__
from vimtg.cli import main


def test_version():
    assert __version__ == "1.0.0rc1"


def test_package_version_is_single_sourced():
    # pyproject must not carry its own literal version: hatch reads it from
    # vimtg.__version__, so the two can never drift apart.
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    assert "version" not in pyproject["project"]
    assert "version" in pyproject["project"]["dynamic"]
    assert pyproject["tool"]["hatch"]["version"]["path"] == "src/vimtg/__init__.py"


def test_installed_metadata_matches_package_version():
    from importlib.metadata import version

    assert version("vimtg") == __version__


def test_user_agents_carry_the_version():
    from vimtg.data.scryfall_sync import USER_AGENT as SCRYFALL_UA
    from vimtg.services.edhrec import USER_AGENT as EDHREC_UA

    assert SCRYFALL_UA == EDHREC_UA == f"vimtg/{__version__}"


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "1.0.0rc1" in result.output


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "vimtg" in result.output


def test_license_file_ships_in_both_dists():
    # PEP 639: license-files puts LICENSE in the wheel's .dist-info; the sdist
    # uses an explicit only-include list, so LICENSE must be listed there too.
    root = Path(__file__).parent.parent
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["license"] == "MIT"
    assert pyproject["project"]["license-files"] == ["LICENSE"]
    assert "LICENSE" in pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]
    text = (root / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "Copyright (c) 2026 Keerthik Muruganandam" in text


def test_release_metadata_matches_version():
    # A release must have its own dated CHANGELOG section (under an empty
    # Unreleased heading) and a classifier that matches a 1.x stable series.
    root = Path(__file__).parent.parent
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert "Development Status :: 5 - Production/Stable" in pyproject["project"]["classifiers"]
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"\n## [{__version__}] - " in changelog
    assert changelog.index("## [Unreleased]") < changelog.index(f"## [{__version__}]")
