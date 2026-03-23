import click

from vimtg import __version__


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="vimtg")
@click.pass_context
def main(ctx: click.Context) -> None:
    """vimtg — Vim-powered MTG deck builder."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
