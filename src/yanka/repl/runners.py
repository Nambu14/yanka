"""Default live ingest and retrieval runners for the REPL."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from yanka.ingest.pipeline_stages import PipelineStage
from yanka.paths import DataPaths
from yanka.records.models import Record
from yanka.repl.errors import repl_conflict_prompt
from yanka.repl.prompts import ask_log_user, prompt_log_user
from yanka.repl.types import OutputFn, PromptFn
from yanka.ui.pipeline_activity import IngestOnStage, RetrievalOnStage


def run_live_ingest(
    raw_dump: str,
    paths: DataPaths,
    *,
    input_fn: PromptFn,
    output_fn: OutputFn,
    messages: list[dict[str, str]] | None = None,
    stage: PipelineStage | None = None,
    record: Record | None = None,
    on_stage: IngestOnStage | None = None,
    before_blocking_prompt: Callable[[], None] | None = None,
    before_confirmation: Callable[[], None] | None = None,
) -> Any:
    from yanka.config import load_config
    from yanka.ingest import run_ingest_pipeline
    from yanka.ingest.entity_resolution import make_fetch_resolution

    config = load_config(paths) if paths.config_path.is_file() else None
    llm_config = config.llm if config is not None else None
    embedding_config = config.embedding if config is not None else None

    def _before_prompt() -> None:
        if before_blocking_prompt is not None:
            before_blocking_prompt()

    return run_ingest_pipeline(
        raw_dump,
        paths,
        prompt_user=lambda assistant_message: prompt_log_user(
            assistant_message,
            input_fn=input_fn,
            output_fn=output_fn,
            before_prompt=_before_prompt,
        ),
        fetch_resolution=make_fetch_resolution(paths=paths, llm_config=llm_config),
        ask_user=lambda question: ask_log_user(
            question,
            input_fn=input_fn,
            output_fn=output_fn,
            before_prompt=_before_prompt,
        ),
        prompt_confirm=repl_conflict_prompt,
        show_confirmation=True,
        llm_config=llm_config,
        embedding_config=embedding_config,
        resume_messages=messages if record is None else None,
        resume_stage=stage,
        resume_record=record,
        on_stage=on_stage,
        before_confirmation=before_confirmation,
        confirmation_output=output_fn,
    )


def run_live_ask(
    question: str,
    paths: DataPaths,
    *,
    on_stage: RetrievalOnStage | None = None,
) -> Any:
    from yanka.config import load_config
    from yanka.retrieval import run_retrieval_pipeline

    config = load_config(paths) if paths.config_path.is_file() else None
    llm_config = config.llm if config is not None else None
    embedding_config = config.embedding if config is not None else None

    return run_retrieval_pipeline(
        question,
        paths,
        llm_config=llm_config,
        embedding_config=embedding_config,
        on_stage=on_stage,
    )


def display_retrieval_answer(result: Any, output_fn: OutputFn) -> None:
    from rich.console import Console

    from yanka.ui import render_retrieval_answer
    from yanka.ui.console_file import ConsoleFile

    view = getattr(result, "answer_view", None)
    if view is None:
        answer = getattr(result, "answer", None)
        if answer:
            output_fn(str(answer))
        return

    console = Console(file=ConsoleFile(output_fn), force_terminal=True, width=120)
    console.print(render_retrieval_answer(view))
