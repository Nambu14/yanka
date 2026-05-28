from pathlib import Path

import click
from click.testing import CliRunner

from yanka.cli import CONTEXT_KEY, get_data_paths, main
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.records.io import read_record, write_record


def test_version() -> None:
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_help() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Capture engineering decisions" in result.output
    assert "--data-dir" in result.output
    assert "rebuild" in result.output


def test_data_dir_option_with_version(tmp_path: Path) -> None:
    result = CliRunner().invoke(main, ["--data-dir", str(tmp_path), "--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_rebuild_command(tmp_path: Path) -> None:
    from yanka.config import EmbeddingConfig, default_config, save_config
    from yanka.embeddings import EMBEDDING_DIM, register_embedding_backend

    def fake_embed(texts: list[str], _config: EmbeddingConfig) -> list[list[float]]:
        return [[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts]

    register_embedding_backend("test", fake_embed)
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    config = default_config(paths.data_dir)
    config.embedding = EmbeddingConfig(provider="test", model="fake")
    save_config(paths, config)
    record = read_record(Path(__file__).parent / "fixtures" / "records" / "with-claims.md").record
    write_record(paths, record, filename="with-claims.md")

    result = CliRunner().invoke(main, ["--data-dir", str(tmp_path), "rebuild"])

    assert result.exit_code == 0
    assert "Rebuilt indexes from 1 record(s)." in result.output


def test_no_subcommand_enters_repl(tmp_path: Path, monkeypatch) -> None:
    from yanka.config import default_config, save_config

    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    save_config(paths, default_config(paths.data_dir))
    called = []

    def fake_repl(repl_paths):
        called.append(repl_paths)

    monkeypatch.setattr("yanka.cli.run_repl", fake_repl)

    result = CliRunner().invoke(main, ["--data-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert called == [paths]


def test_get_data_paths_from_context(tmp_path: Path) -> None:
    ctx = click.Context(main)
    ctx.ensure_object(dict)
    ctx.obj[CONTEXT_KEY] = resolve_data_paths(tmp_path)
    assert get_data_paths(ctx).data_dir == tmp_path.resolve()
