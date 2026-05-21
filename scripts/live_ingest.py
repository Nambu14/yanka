#!/usr/bin/env python3
"""One-shot live ingest — spec §7 steps 1–10. See docs/live-ingest-checklist.md."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from whyline.config import load_config
from whyline.ingest import run_ingest_pipeline
from whyline.ingest.entity_resolution import make_fetch_resolution
from whyline.ingest.extraction import RecordExtractionError
from whyline.paths import ensure_data_layout, resolve_data_paths
from whyline.ui.conflict_confirm import default_conflict_prompt


def _read_dump(argument: str | None) -> str:
    if argument is not None and argument.strip():
        return argument.strip()
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            return text
    raise click.UsageError(
        "Provide a brain dump as an argument or pipe text on stdin."
    )


_WRAP_UP_NUDGE = (
    "CONVERSATION ENDED. Output ONLY the final record now — no questions."
)


def _prompt_user(assistant_message: str) -> str:
    click.echo()
    click.echo(assistant_message)
    click.echo()
    reply = click.prompt("  Your reply", default="", show_default=False)
    if not reply.strip():
        return _WRAP_UP_NUDGE
    return reply


def _ask_user(question: str) -> str:
    click.echo()
    click.echo(question)
    return click.prompt("  Your answer", default="", show_default=False)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("dump", required=False, default=None)
@click.option(
    "--data-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=None,
    help="Data directory (default: ~/.whyline).",
)
def main(dump: str | None, data_dir: Path | None) -> None:
    """Run a full ingest session with real LLM calls."""
    raw_dump = _read_dump(dump)
    paths = ensure_data_layout(resolve_data_paths(data_dir))
    config = load_config(paths) if paths.config_path.is_file() else None
    llm_config = config.llm if config is not None else None
    embedding_config = config.embedding if config is not None else None

    click.echo("Running ingest pipeline (live LLM)...")
    try:
        result = _run_pipeline(
            raw_dump,
            paths,
            llm_config=llm_config,
            embedding_config=embedding_config,
        )
    except RecordExtractionError as exc:
        click.echo()
        click.echo("Extraction failed: no valid record after wrap-up.", err=True)
        if exc.last_assistant_response.strip():
            click.echo()
            click.echo("Last model reply:")
            click.echo(exc.last_assistant_response[:4000])
        raise SystemExit(1) from exc

    _report_result(result)


def _run_pipeline(
    raw_dump: str,
    paths,
    *,
    llm_config,
    embedding_config,
):
    return run_ingest_pipeline(
        raw_dump,
        paths,
        prompt_user=_prompt_user,
        fetch_resolution=make_fetch_resolution(paths=paths, llm_config=llm_config),
        ask_user=_ask_user,
        prompt_confirm=default_conflict_prompt,
        show_confirmation=True,
        llm_config=llm_config,
        embedding_config=embedding_config,
    )


def _report_result(result) -> None:
    if result.warnings:
        click.echo()
        for warning in result.warnings:
            click.echo(f"Warning: {warning}")

    click.echo()
    click.echo(f"Saved: {result.write_result.path}")
    if result.confirmed_conflicts:
        click.echo(
            f"Confirmed {len(result.confirmed_conflicts)} supersession(s)."
        )


if __name__ == "__main__":
    main()
