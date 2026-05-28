"""`/log` command."""

from __future__ import annotations

from typing import Any

from yanka.app_logging import get_logger, log_exception
from yanka.ingest.extraction import RecordExtractionError
from yanka.ingest.pipeline import IngestAbortError, IngestDuplicateRecordError
from yanka.ingest.pipeline_stages import PipelineStage
from yanka.ingest.resume_state import (
    clear_pending_log_session,
    save_pending_log_session,
)
from yanka.llm.client import LlmError
from yanka.paths import DataPaths
from yanka.repl.errors import emit_user_error
from yanka.repl.prompts import format_last_model_reply
from yanka.repl.runners import run_live_ingest
from yanka.repl.types import LogRunner, NoteReader, OutputFn, PromptFn
from yanka.ui import IngestActivityStage, ingest_stage_label, start_activity

_LOGGER = get_logger(__name__)


def run_log_command(
    paths: DataPaths,
    *,
    statement: str = "",
    input_fn: PromptFn | None = None,
    note_reader: NoteReader | None = None,
    output_fn: OutputFn | None = None,
    ingest_runner: LogRunner | None = None,
) -> Any | None:
    """Prompt for a brain dump and run the ingest pipeline."""
    prompt = input_fn if input_fn is not None else input
    output = output_fn if output_fn is not None else print

    raw_dump = statement.strip()
    if not raw_dump:
        output("Paste your decision note:")
        if note_reader is not None:
            raw_dump = note_reader().strip()
        else:
            raw_dump = prompt("> ").strip()
    if not raw_dump:
        output("Nothing to log.")
        return None

    output("Running ingest pipeline...")
    activity = start_activity(output, ingest_stage_label(IngestActivityStage.SEARCHING))

    def on_stage(stage: IngestActivityStage) -> None:
        activity.update(ingest_stage_label(stage))

    def pause_activity_for_panel() -> None:
        activity.stop()
        output("")

    runner = ingest_runner if ingest_runner is not None else _default_log_runner
    try:
        result = runner(
            raw_dump,
            paths,
            input_fn=prompt,
            output_fn=output,
            on_stage=on_stage,
            before_blocking_prompt=pause_activity_for_panel,
            before_confirmation=pause_activity_for_panel,
        )
    except RecordExtractionError as exc:
        log_exception(_LOGGER, "log extraction incomplete", exc, command="log")
        save_pending_log_session(
            paths,
            raw_dump=raw_dump,
            messages=exc.messages,
            stage=PipelineStage.EXTRACTION,
        )
        activity.stop()
        output("Could not turn this session into a complete record.")
        output("Nothing was saved. Try /log again with a shorter summary or more context.")
        if exc.last_assistant_response.strip():
            output("Last model reply:")
            output(format_last_model_reply(exc.last_assistant_response))
        output("Your progress is saved — run /resume to continue.")
        return None
    except IngestDuplicateRecordError as exc:
        log_exception(_LOGGER, "log ingest skipped duplicates", exc, command="log")
        clear_pending_log_session(paths)
        activity.stop()
        emit_user_error(output, exc, command="log")
        return None
    except IngestAbortError as exc:
        log_exception(_LOGGER, "log ingest aborted", exc, command="log")
        save_pending_log_session(
            paths,
            raw_dump=raw_dump,
            messages=exc.messages,
            stage=exc.stage,
            record=exc.record,
        )
        activity.stop()
        output("Ingest stopped before the record could be saved.")
        emit_user_error(output, exc, command="log")
        return None
    except LlmError as exc:
        log_exception(_LOGGER, "log command failed", exc, command="log")
        save_pending_log_session(
            paths,
            raw_dump=raw_dump,
            messages=[],
            stage=PipelineStage.EXTRACTION,
        )
        activity.stop()
        output("Ingest failed before a record could be saved.")
        emit_user_error(output, exc, command="log")
        return None
    activity.stop()
    write_result = getattr(result, "write_result", None)
    path = getattr(write_result, "path", None)
    if path is not None:
        clear_pending_log_session(paths)
        output(f"Saved: {path}")
        for warning in getattr(result, "warnings", ()):
            output(f"Warning: {warning}")
    return result


def _default_log_runner(
    raw_dump: str,
    paths: DataPaths,
    *,
    input_fn: PromptFn,
    output_fn: OutputFn,
    **kwargs: Any,
) -> Any:
    on_stage = kwargs.get("on_stage")
    return run_live_ingest(
        raw_dump,
        paths,
        input_fn=input_fn,
        output_fn=output_fn,
        on_stage=on_stage,
        before_blocking_prompt=kwargs.get("before_blocking_prompt"),
        before_confirmation=kwargs.get("before_confirmation"),
    )
