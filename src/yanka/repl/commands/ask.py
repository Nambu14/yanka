"""`/ask` command."""

from __future__ import annotations

from typing import Any

from yanka.app_logging import get_logger, log_exception
from yanka.llm.client import LlmError
from yanka.paths import DataPaths
from yanka.records.io import iter_records
from yanka.repl.errors import emit_user_error
from yanka.repl.runners import display_retrieval_answer, run_live_ask
from yanka.repl.types import AnswerDisplayFn, AskRunner, OutputFn, PromptFn
from yanka.ui import RetrievalActivityStage, retrieval_stage_label, start_activity

_LOGGER = get_logger(__name__)


def run_ask_command(
    paths: DataPaths,
    *,
    question: str = "",
    input_fn: PromptFn | None = None,
    output_fn: OutputFn | None = None,
    ask_runner: AskRunner | None = None,
    display_answer: AnswerDisplayFn | None = None,
) -> Any | None:
    """Run a knowledge-base query and show the synthesized answer."""
    prompt = input_fn if input_fn is not None else input
    output = output_fn if output_fn is not None else print

    user_question = question.strip()
    if not user_question:
        user_question = prompt("Question: ").strip()
    if not user_question:
        output("Nothing to ask.")
        return None

    if not list(iter_records(paths)):
        output("No records yet. Use /log first, then /rebuild if indexes are stale.")
        return None

    output("Searching knowledge base...")
    activity = start_activity(output, retrieval_stage_label(RetrievalActivityStage.ANALYZING))

    def on_stage(stage: RetrievalActivityStage) -> None:
        activity.update(retrieval_stage_label(stage))

    runner = ask_runner if ask_runner is not None else run_live_ask
    show_answer = display_answer if display_answer is not None else display_retrieval_answer
    try:
        result = runner(user_question, paths, on_stage=on_stage)
    except LlmError as exc:
        activity.stop()
        log_exception(_LOGGER, "ask command failed", exc, command="ask")
        output("Could not answer this question.")
        emit_user_error(output, exc, command="ask")
        return None

    activity.stop()
    show_answer(result, output)
    for warning in getattr(result, "warnings", ()):
        output(f"Warning: {warning}")
    output("[/log to update]  [/ask <follow-up>]")
    return result
