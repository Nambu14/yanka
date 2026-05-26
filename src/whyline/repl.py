"""Interactive slash-command loop — spec §11."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from whyline.paths import DataPaths
from whyline.rebuild import rebuild_indexes
from whyline.records.io import iter_records

PromptFn = Callable[[str], str]
OutputFn = Callable[[str], None]
LogRunner = Callable[..., Any]

PROMPT = "❯ "

HELP_TEXT = """\
/log      Record a decision
/ask      Query existing knowledge
/status   Show local KB status
/history  Show recent records
/rebuild  Rebuild graph and vector indexes
/resume   Resume interrupted work
/help     Show this command reference
/exit     Quit"""


def run_repl(
    paths: DataPaths,
    *,
    input_fn: PromptFn | None = None,
    output_fn: OutputFn | None = None,
    log_runner: LogRunner | None = None,
) -> None:
    """Run the interactive Whyline loop.

    Commands are implemented incrementally through Phase 8.
    """
    prompt = input_fn if input_fn is not None else input
    output = output_fn if output_fn is not None else print

    output("Welcome to Whyline.")
    output(f"Data dir: {paths.data_dir}")
    output("Type /help for commands.")
    output("")

    while True:
        try:
            raw = prompt(PROMPT)
        except (EOFError, KeyboardInterrupt):
            output("")
            return

        command = raw.strip()
        if not command:
            continue
        if command in {"/exit", "/quit"}:
            return
        if command == "/help":
            output(HELP_TEXT)
            continue
        if command == "/status":
            output(format_status(paths))
            continue
        if command == "/history":
            output(format_history(paths))
            continue
        if command == "/rebuild":
            output(run_repl_rebuild(paths))
            continue
        if command == "/log":
            run_log_command(
                paths,
                input_fn=prompt,
                output_fn=output,
                ingest_runner=log_runner,
            )
            continue
        if command.startswith("/"):
            output(f"Unknown command: {command}. Type /help for commands.")
            continue
        output("Commands start with /. Type /help for commands.")


def format_status(paths: DataPaths) -> str:
    """Return a concise local knowledge-base status summary."""
    records = list(iter_records(paths))
    lines = [
        f"Data dir: {paths.data_dir}",
        f"Records: {len(records)}",
    ]
    if not records:
        return "\n".join(lines)

    projects = sorted(
        {
            record_file.record.context_path[0]
            for record_file in records
            if record_file.record.context_path
        }
    )
    if projects:
        lines.append(f"Projects: {', '.join(projects)}")
    latest = max(record_file.record.date for record_file in records)
    lines.append(f"Latest record: {latest.isoformat()}")
    return "\n".join(lines)


def format_history(paths: DataPaths, *, limit: int = 5) -> str:
    """Return recent records with date, status, filename, and summary."""
    records = sorted(
        iter_records(paths),
        key=lambda record_file: (record_file.record.date, record_file.path.name),
        reverse=True,
    )
    if not records:
        return "No records yet."

    lines: list[str] = []
    for record_file in records[:limit]:
        record = record_file.record
        lines.append(
            f"{record.date.isoformat()}  {record.status.value}  "
            f"{record_file.path.name}  {record.decision}"
        )
    return "\n".join(lines)


def run_repl_rebuild(paths: DataPaths) -> str:
    """Rebuild indexes from the REPL and return the user-facing summary."""
    count = rebuild_indexes(paths)
    return f"Rebuilt indexes from {count} record(s)."


def run_log_command(
    paths: DataPaths,
    *,
    input_fn: PromptFn | None = None,
    output_fn: OutputFn | None = None,
    ingest_runner: LogRunner | None = None,
) -> Any | None:
    """Prompt for a brain dump and run the ingest pipeline."""
    prompt = input_fn if input_fn is not None else input
    output = output_fn if output_fn is not None else print

    output("Paste your decision note:")
    raw_dump = prompt("> ").strip()
    if not raw_dump:
        output("Nothing to log.")
        return None

    from whyline.ingest.extraction import RecordExtractionError

    output("Running ingest pipeline...")
    runner = ingest_runner if ingest_runner is not None else _run_live_log
    try:
        result = runner(
            raw_dump,
            paths,
            input_fn=prompt,
            output_fn=output,
        )
    except RecordExtractionError as exc:
        output("Could not turn this session into a complete record.")
        output(
            "Nothing was saved. Try /log again with a shorter summary "
            "or more context."
        )
        if exc.last_assistant_response.strip():
            output("Last model reply:")
            output(_format_last_model_reply(exc.last_assistant_response))
        return None
    write_result = getattr(result, "write_result", None)
    path = getattr(write_result, "path", None)
    if path is not None:
        output(f"Saved: {path}")
    return result


def _run_live_log(
    raw_dump: str,
    paths: DataPaths,
    *,
    input_fn: PromptFn,
    output_fn: OutputFn,
):
    from whyline.config import load_config
    from whyline.ingest import run_ingest_pipeline
    from whyline.ingest.entity_resolution import make_fetch_resolution
    from whyline.ui.conflict_confirm import default_conflict_prompt

    config = load_config(paths) if paths.config_path.is_file() else None
    llm_config = config.llm if config is not None else None
    embedding_config = config.embedding if config is not None else None

    return run_ingest_pipeline(
        raw_dump,
        paths,
        prompt_user=lambda assistant_message: _prompt_log_user(
            assistant_message,
            input_fn=input_fn,
            output_fn=output_fn,
        ),
        fetch_resolution=make_fetch_resolution(paths=paths, llm_config=llm_config),
        ask_user=lambda question: _ask_log_user(
            question,
            input_fn=input_fn,
            output_fn=output_fn,
        ),
        prompt_confirm=default_conflict_prompt,
        show_confirmation=True,
        llm_config=llm_config,
        embedding_config=embedding_config,
    )


def _prompt_log_user(
    assistant_message: str,
    *,
    input_fn: PromptFn,
    output_fn: OutputFn,
) -> str:
    output_fn("")
    output_fn(assistant_message)
    output_fn("")
    reply = input_fn("  Your reply: ")
    if not reply.strip():
        return "CONVERSATION ENDED. Output ONLY the final record now — no questions."
    return reply


def _ask_log_user(
    question: str,
    *,
    input_fn: PromptFn,
    output_fn: OutputFn,
) -> str:
    output_fn("")
    output_fn(question)
    return input_fn("  Your answer: ")


def _format_last_model_reply(reply: str, *, max_chars: int = 500) -> str:
    """Keep failed extraction diagnostics readable in the REPL."""
    stripped = reply.strip()
    if len(stripped) <= max_chars:
        return stripped
    return f"{stripped[:max_chars].rstrip()}..."
