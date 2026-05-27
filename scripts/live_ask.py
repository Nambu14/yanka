#!/usr/bin/env python3
"""One-shot live retrieval — spec §8 steps 1–5. See docs/live-retrieval-checklist.md."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from yanka.config import load_config
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.retrieval import run_retrieval_pipeline
from yanka.ui import render_retrieval_answer


def _read_question(argument: str | None) -> str:
    if argument is not None and argument.strip():
        return argument.strip()
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            return text
    raise click.UsageError("Provide a question as an argument or pipe text on stdin.")


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("question", required=False, default=None)
@click.option(
    "--data-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=None,
    help="Data directory (default: ~/.yanka).",
)
def main(question: str | None, data_dir: Path | None) -> None:
    """Run one retrieval query with real LLM calls."""
    user_question = _read_question(question)
    paths = ensure_data_layout(resolve_data_paths(data_dir))
    config = load_config(paths) if paths.config_path.is_file() else None
    llm_config = config.llm if config is not None else None
    embedding_config = config.embedding if config is not None else None

    click.echo("Running retrieval pipeline (live LLM)...")
    result = run_retrieval_pipeline(
        user_question,
        paths,
        llm_config=llm_config,
        embedding_config=embedding_config,
    )

    Console().print(render_retrieval_answer(result.answer_view))
    click.echo()
    click.echo(f"Graph hits: {len(result.graph_hits)}")
    click.echo(f"Vector hits: {len(result.vector_hits)}")
    click.echo(f"Merged hits: {len(result.merged_hits)}")


if __name__ == "__main__":
    main()
