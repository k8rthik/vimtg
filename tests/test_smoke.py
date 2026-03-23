from click.testing import CliRunner

from vimtg import __version__
from vimtg.cli import main


def test_version():
    assert __version__ == "0.1.0"


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "vimtg" in result.output
