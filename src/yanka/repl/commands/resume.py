"""`/resume` command."""

from __future__ import annotations

from typing import Any

from yanka.app_logging import get_logger, log_exception
from yanka.ingest.extraction import RecordExtractionError
from yanka.ingest.pipeline import IngestAbortError
from yanka.ingest.pipeline_stages import PipelineStage
from yanka.ingest.resume_state import (
    clear_pending_log_session,
    has_pending_log_session,
    load_pending_log_session,
    save_pending_log_session,
)
from yanka.llm.client import LlmError
from yanka.paths import DataPaths
from yanka.repl.errors import emit_user_error
from yanka.repl.prompts import format_last_model_reply
from yanka.repl.runners import run_live_ingest
from yanka.repl.types import LogRunner, OutputFn, PromptFn

_LOGGER = get_logger(__name__)


def run_resume_command(
    paths: DataPaths,
    *,
    input_fn: PromptFn | None = None,
    output_fn: OutputFn | None = None,
    ingest_runner: LogRunner | None = None,
) -> Any | None:
    """Resume interrupted /log work from saved state."""
    prompt = input_fn if input_fn is not None else input
    output = output_fn if output_fn is not None else print

    if not has_pending_log_session(paths):
        output("Nothing to resume.")
        return None
    try:
        pending = load_pending_log_session(paths)
    except ValueError as exc:
        log_exception(_LOGGER, "invalid resume state", exc, command="resume")
        output(f"Pending resume state is invalid: {exc}")
        clear_pending_log_session(paths)
        return None

    output(
        f"Resuming interrupted /log ({pending.stage.value}) "
        f"from {pending.created_at}..."
    )
    runner = ingest_runner if ingest_runner is not None else _default_resume_runner
    try:
        result = runner(
            pending.raw_dump,
            paths,
            messages=pending.messages,
            stage=pending.stage,
            record=pending.record,
            input_fn=prompt,
            output_fn=output,
        )
    except RecordExtractionError as exc:
        log_exception(_LOGGER, "resume extraction incomplete", exc, command="resume")
        save_pending_log_session(
            paths,
            raw_dump=pending.raw_dump,
            messages=exc.messages,
            stage=PipelineStage.EXTRACTION,
        )
        output("Resume did not complete yet. Progress kept; run /resume again.")
        if exc.last_assistant_response.strip():
            output("Last model reply:")
            output(format_last_model_reply(exc.last_assistant_response))
        return None
    except IngestAbortError as exc:
        log_exception(_LOGGER, "resume ingest aborted", exc, command="resume")
        save_pending_log_session(
            paths,
            raw_dump=pending.raw_dump,
            messages=exc.messages,
            stage=exc.stage,
            record=exc.record,
        )
        output("Resume stopped before the record could be saved.")
        emit_user_error(output, exc, command="resume")
        output("Progress is still saved. Run /resume again.")
        return None
    except LlmError as exc:
        log_exception(_LOGGER, "resume command failed", exc, command="resume")
        save_pending_log_session(
            paths,
            raw_dump=pending.raw_dump,
            messages=pending.messages,
            stage=pending.stage,
            record=pending.record,
        )
        output("Resume failed.")
        emit_user_error(output, exc, command="resume")
        output("Progress is still saved. Run /resume again.")
        return None

    clear_pending_log_session(paths)
    write_result = getattr(result, "write_result", None)
    path = getattr(write_result, "path", None)
    if path is not None:
        output(f"Saved: {path}")
    return result


def _default_resume_runner(
    raw_dump: str,
    paths: DataPaths,
    *,
    messages: list[dict[str, str]],
    stage: PipelineStage | None = None,
    record: Any | None = None,
    input_fn: PromptFn,
    output_fn: OutputFn,
    **kwargs: Any,
) -> Any:
    return run_live_ingest(
        raw_dump,
        paths,
        input_fn=input_fn,
        output_fn=output_fn,
        messages=messages,
        stage=stage,
        record=record,
    )
