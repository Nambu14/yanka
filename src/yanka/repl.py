"""Interactive slash-command loop — spec §11."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yanka.ingest.resume_state import (
    clear_pending_log_session,
    has_pending_log_session,
    load_pending_log_session,
    save_pending_log_session,
)
from yanka.paths import DataPaths
from yanka.rebuild import rebuild_indexes
from yanka.records.io import iter_records
from yanka.ui import (
    print_clarifying_panel,
    print_status_panel,
    print_statusline,
    print_system,
    start_activity,
)

PromptFn = Callable[[str], str]
NoteReader = Callable[[], str]
OutputFn = Callable[[str], None]
LogRunner = Callable[..., Any]
AskRunner = Callable[..., Any]
AnswerDisplayFn = Callable[[Any, OutputFn], None]

PROMPT = "❯ "

HELP_TEXT = """\
/log [text]     Record a decision (inline or prompted)
/ask [question] Query existing knowledge
/status         Show local KB status
/history        Show recent records
/last           Show most recent record
/rebuild        Rebuild graph and vector indexes
/resume         Resume interrupted work
/help           Show this command reference
/exit           Quit

Aliases: /? -> /help, /h -> /history, /q -> /exit"""


def run_repl(
    paths: DataPaths,
    *,
    input_fn: PromptFn | None = None,
    output_fn: OutputFn | None = None,
    log_runner: LogRunner | None = None,
    ask_runner: AskRunner | None = None,
    display_answer: AnswerDisplayFn | None = None,
) -> None:
    """Run the interactive Yanka loop.

    Commands are implemented incrementally through Phase 8.
    """
    prompt = input_fn if input_fn is not None else input
    note_reader: NoteReader | None = None
    output = output_fn if output_fn is not None else print
    if input_fn is None:
        adapters = _build_prompt_adapters(paths)
        if adapters is not None:
            prompt = adapters.prompt
            note_reader = adapters.read_note

    print_system(output, "Welcome to yanka.")
    output(f"Data dir: {paths.data_dir}")
    output("Type /help for commands.")
    output("")

    while True:
        print_statusline(output, format_statusline(paths))
        try:
            raw = prompt(PROMPT)
        except (EOFError, KeyboardInterrupt):
            output("")
            return

        command = raw.strip()
        if not command:
            continue
        if command in {"/exit", "/quit", "/q"}:
            return
        if command in {"/help", "/?"}:
            output(HELP_TEXT)
            continue
        if command == "/status":
            print_status_panel(output, format_status(paths))
            continue
        if command in {"/history", "/h"}:
            output(format_history(paths))
            continue
        if command == "/last":
            output(format_last(paths))
            continue
        if command == "/rebuild":
            output(run_repl_rebuild(paths))
            continue
        if command == "/resume":
            run_resume_command(
                paths,
                input_fn=prompt,
                output_fn=output,
                ingest_runner=log_runner,
            )
            continue
        if command == "/log" or command.startswith("/log "):
            statement = command[4:].strip() if command.startswith("/log ") else ""
            if has_pending_log_session(paths):
                output(
                    "You have interrupted /log work pending. "
                    "Run /resume to continue it."
                )
                choice = prompt("Start a new /log and discard pending work? [y/N]: ")
                if choice.strip().lower() not in {"y", "yes"}:
                    output("Cancelled. Pending work kept.")
                    continue
                clear_pending_log_session(paths)
            run_log_command(
                paths,
                statement=statement,
                input_fn=prompt,
                note_reader=note_reader,
                output_fn=output,
                ingest_runner=log_runner,
            )
            continue
        if command == "/ask" or command.startswith("/ask "):
            question = command[4:].strip() if command.startswith("/ask ") else ""
            run_ask_command(
                paths,
                question=question,
                input_fn=prompt,
                output_fn=output,
                ask_runner=ask_runner,
                display_answer=display_answer,
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


def format_last(paths: DataPaths) -> str:
    """Return the most recent record summary with file path."""
    records = sorted(
        iter_records(paths),
        key=lambda record_file: (record_file.record.date, record_file.path.name),
        reverse=True,
    )
    if not records:
        return "No records yet."
    latest = records[0]
    record = latest.record
    return (
        f"{record.date.isoformat()}  {record.status.value}  {latest.path.name}  "
        f"{record.decision}\nPath: {latest.path}"
    )


def format_statusline(paths: DataPaths) -> str:
    """One-line prompt context summary."""
    records = list(iter_records(paths))
    llm_label = "llm: default"
    if paths.config_path.is_file():
        from yanka.config import load_config

        config = load_config(paths)
        llm_label = f"llm: {config.llm.provider}/{config.llm.model}"
    return (
        f"dir: {paths.data_dir.name} | records: {len(records)} | {llm_label}"
    )


def run_repl_rebuild(paths: DataPaths) -> str:
    """Rebuild indexes from the REPL and return the user-facing summary."""
    count = rebuild_indexes(paths)
    return f"Rebuilt indexes from {count} record(s)."


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

    from yanka.ingest.extraction import RecordExtractionError
    from yanka.llm.client import LlmError

    output("Running ingest pipeline...")
    activity = start_activity(output, "searching related records...")
    activity.update("extracting claims...")
    activity.update("checking for conflicts...")
    runner = ingest_runner if ingest_runner is not None else _run_live_log
    try:
        result = runner(
            raw_dump,
            paths,
            input_fn=prompt,
            output_fn=output,
        )
    except RecordExtractionError as exc:
        save_pending_log_session(paths, raw_dump=raw_dump, messages=exc.messages)
        activity.stop()
        output("Could not turn this session into a complete record.")
        output(
            "Nothing was saved. Try /log again with a shorter summary "
            "or more context."
        )
        if exc.last_assistant_response.strip():
            output("Last model reply:")
            output(_format_last_model_reply(exc.last_assistant_response))
        output("Your progress is saved — run /resume to continue.")
        return None
    except LlmError as exc:
        save_pending_log_session(paths, raw_dump=raw_dump, messages=[])
        activity.stop()
        output("Ingest failed before a record could be saved.")
        output(str(exc))
        output("Your progress is saved — run /resume to continue.")
        return None
    activity.stop()
    write_result = getattr(result, "write_result", None)
    path = getattr(write_result, "path", None)
    if path is not None:
        clear_pending_log_session(paths)
        output(f"Saved: {path}")
        output("[a] /ask about this   [o] open file   [n] /log")
    return result


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

    from yanka.llm.client import LlmError

    output("Searching knowledge base...")
    activity = start_activity(output, "analyzing query...")
    activity.update("retrieving from graph...")
    activity.update("retrieving from vectors...")
    activity.update("synthesizing answer...")
    runner = ask_runner if ask_runner is not None else _run_live_ask
    show_answer = (
        display_answer if display_answer is not None else _display_retrieval_answer
    )
    try:
        result = runner(user_question, paths)
    except LlmError as exc:
        activity.stop()
        output("Could not answer this question.")
        output(str(exc))
        return None

    activity.stop()
    show_answer(result, output)
    output("[/log to update]  [/ask <follow-up>]")
    return result


def _run_live_ask(question: str, paths: DataPaths):
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
    )


def _display_retrieval_answer(result: Any, output_fn: OutputFn) -> None:
    from rich.console import Console

    view = getattr(result, "answer_view", None)
    if view is None:
        answer = getattr(result, "answer", None)
        if answer:
            output_fn(str(answer))
        return

    from yanka.ui import render_retrieval_answer

    console = Console(file=_ConsoleFile(output_fn), force_terminal=True, width=120)
    console.print(render_retrieval_answer(view))


class _ConsoleFile:
    """Route Rich console output through a plain output callback."""

    def __init__(self, output_fn: OutputFn) -> None:
        self._output_fn = output_fn

    def write(self, text: str) -> int:
        if text:
            for line in text.splitlines():
                stripped = line.rstrip()
                if stripped:
                    self._output_fn(stripped)
        return len(text)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False


def _run_live_log(
    raw_dump: str,
    paths: DataPaths,
    *,
    input_fn: PromptFn,
    output_fn: OutputFn,
):
    from yanka.config import load_config
    from yanka.ingest import run_ingest_pipeline
    from yanka.ingest.entity_resolution import make_fetch_resolution
    from yanka.ui.conflict_confirm import default_conflict_prompt

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


def run_resume_command(
    paths: DataPaths,
    *,
    input_fn: PromptFn | None = None,
    output_fn: OutputFn | None = None,
    ingest_runner: LogRunner | None = None,
) -> Any | None:
    """Resume interrupted /log extraction work from saved state."""
    prompt = input_fn if input_fn is not None else input
    output = output_fn if output_fn is not None else print
    from yanka.ingest.extraction import RecordExtractionError
    from yanka.llm.client import LlmError
    if not has_pending_log_session(paths):
        output("Nothing to resume.")
        return None
    try:
        pending = load_pending_log_session(paths)
    except ValueError as exc:
        output(f"Pending resume state is invalid: {exc}")
        clear_pending_log_session(paths)
        return None

    output(f"Resuming interrupted /log from {pending.created_at}...")
    runner = ingest_runner if ingest_runner is not None else _run_live_resume
    try:
        result = runner(
            pending.raw_dump,
            paths,
            messages=pending.messages,
            input_fn=prompt,
            output_fn=output,
        )
    except RecordExtractionError as exc:
        save_pending_log_session(
            paths,
            raw_dump=pending.raw_dump,
            messages=exc.messages,
        )
        output("Resume did not complete yet. Progress kept; run /resume again.")
        if exc.last_assistant_response.strip():
            output("Last model reply:")
            output(_format_last_model_reply(exc.last_assistant_response))
        return None
    except LlmError as exc:
        output(f"Resume failed: {exc}")
        output("Progress is still saved. Run /resume again.")
        return None

    clear_pending_log_session(paths)
    write_result = getattr(result, "write_result", None)
    path = getattr(write_result, "path", None)
    if path is not None:
        output(f"Saved: {path}")
    return result


def _run_live_resume(
    raw_dump: str,
    paths: DataPaths,
    *,
    messages: list[dict[str, str]],
    input_fn: PromptFn,
    output_fn: OutputFn,
):
    from yanka.config import load_config
    from yanka.ingest import run_ingest_pipeline
    from yanka.ingest.entity_resolution import make_fetch_resolution
    from yanka.ui.conflict_confirm import default_conflict_prompt

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
        resume_messages=messages,
    )


def _prompt_log_user(
    assistant_message: str,
    *,
    input_fn: PromptFn,
    output_fn: OutputFn,
) -> str:
    if _looks_like_json_payload(assistant_message):
        output_fn("Model returned structured JSON early; finalizing record...")
        return "CONVERSATION ENDED. Output ONLY the final record now — no questions."

    output_fn("")
    print_clarifying_panel(output_fn, assistant_message)
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


def _looks_like_json_payload(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") and stripped.endswith("}")


def _read_note_multiline(prompt: PromptFn) -> str:
    first = prompt("> ").strip()
    if not first:
        return ""
    lines = [first]
    while True:
        line = prompt("… ").rstrip()
        if not line:
            break
        lines.append(line)
    return "\n".join(lines)


@dataclass(frozen=True)
class _PromptAdapters:
    prompt: PromptFn
    read_note: NoteReader


def _build_prompt_adapters(paths: DataPaths) -> _PromptAdapters | None:
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory
    except ImportError:
        return None

    history_path = _repl_history_path(paths)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    session = PromptSession(history=FileHistory(str(history_path)))
    completer = WordCompleter(_slash_commands(), ignore_case=True, sentence=True)

    def prompt_fn(prompt_text: str) -> str:
        return session.prompt(prompt_text, completer=completer)

    def read_note() -> str:
        return _read_note_multiline(prompt_fn)

    return _PromptAdapters(prompt=prompt_fn, read_note=read_note)


def _slash_commands() -> tuple[str, ...]:
    return (
        "/log",
        "/ask",
        "/status",
        "/history",
        "/last",
        "/rebuild",
        "/resume",
        "/help",
        "/exit",
        "/?",
        "/h",
        "/q",
    )


def _repl_history_path(paths: DataPaths) -> Path:
    return paths.data_dir / "repl_history.txt"
