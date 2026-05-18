from pathlib import Path

import click

from whyline import __version__
from whyline.paths import DataPaths, resolve_data_paths

CONTEXT_KEY = "paths"


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.version_option(__version__, "-V", "--version", message="whyline %(version)s")
@click.option(
    "--data-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=None,
    help="Data directory (default: ~/.whyline). Overrides WHYLINE_DATA_DIR when set.",
)
@click.pass_context
def main(ctx: click.Context, data_dir: Path | None) -> None:
    """Capture engineering decisions and retrieve them later."""
    ctx.ensure_object(dict)
    ctx.obj[CONTEXT_KEY] = resolve_data_paths(data_dir)

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def get_data_paths(ctx: click.Context) -> DataPaths:
    """Resolved paths for the current CLI invocation."""
    return ctx.ensure_object(dict)[CONTEXT_KEY]


if __name__ == "__main__":
    main()
