from pathlib import Path

import click
from click.testing import CliRunner

from whyline.cli import CONTEXT_KEY, get_data_paths, main
from whyline.paths import resolve_data_paths


def test_version() -> None:
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_help() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Capture engineering decisions" in result.output
    assert "--data-dir" in result.output


def test_data_dir_option_with_version(tmp_path: Path) -> None:
    result = CliRunner().invoke(main, ["--data-dir", str(tmp_path), "--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_get_data_paths_from_context(tmp_path: Path) -> None:
    ctx = click.Context(main)
    ctx.ensure_object(dict)
    ctx.obj[CONTEXT_KEY] = resolve_data_paths(tmp_path)
    assert get_data_paths(ctx).data_dir == tmp_path.resolve()
