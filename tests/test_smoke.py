import tomllib
from pathlib import Path

from click.testing import CliRunner

from vimtg import __version__
from vimtg.cli import main


def test_version():
    assert __version__ == "0.8.0"


def test_package_version_matches_pyproject():
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text())["project"]["version"]
    assert declared == __version__


def test_user_agents_carry_the_version():
    from vimtg.data.scryfall_sync import USER_AGENT as SCRYFALL_UA
    from vimtg.services.edhrec import USER_AGENT as EDHREC_UA

    assert SCRYFALL_UA == EDHREC_UA == f"vimtg/{__version__}"


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.8.0" in result.output


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "vimtg" in result.output
