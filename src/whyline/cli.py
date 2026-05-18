import click

from whyline import __version__


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.version_option(__version__, "-V", "--version", message="whyline %(version)s")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Capture engineering decisions and retrieve them later."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


if __name__ == "__main__":
    main()
