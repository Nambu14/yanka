"""Main REPL read-eval loop."""

from __future__ import annotations

from yanka.ingest.resume_state import (
    clear_pending_log_session,
    has_pending_log_session,
)
from yanka.paths import DataPaths
from yanka.repl.commands.ask import run_ask_command
from yanka.repl.commands.inspect import (
    run_config_command,
    run_people_command,
    run_projects_command,
)
from yanka.repl.commands.log import run_log_command
from yanka.repl.commands.rebuild import run_repl_rebuild
from yanka.repl.commands.resume import run_resume_command
from yanka.repl.constants import HELP_TEXT, PROMPT
from yanka.repl.format import (
    format_history,
    format_last,
    format_status,
    format_statusline,
)
from yanka.repl.help_topics import format_help_topic, list_help_topics
from yanka.repl.prompts import build_prompt_adapters
from yanka.repl.statusline_cache import StatuslineCache
from yanka.repl.types import (
    AnswerDisplayFn,
    AskRunner,
    LogRunner,
    NoteReader,
    OutputFn,
    PromptFn,
)
from yanka.ui import print_status_panel, print_statusline, print_welcome_panel


def run_repl(
    paths: DataPaths,
    *,
    input_fn: PromptFn | None = None,
    output_fn: OutputFn | None = None,
    log_runner: LogRunner | None = None,
    ask_runner: AskRunner | None = None,
    display_answer: AnswerDisplayFn | None = None,
) -> None:
    """Run the interactive Yanka loop."""
    prompt = input_fn if input_fn is not None else input
    note_reader: NoteReader | None = None
    output = output_fn if output_fn is not None else print
    if input_fn is None:
        adapters = build_prompt_adapters(paths)
        if adapters is not None:
            prompt = adapters.prompt
            note_reader = adapters.read_note

    print_welcome_panel(output, paths)
    output("")
    statusline_cache = StatuslineCache(paths)

    while True:
        print_statusline(output, format_statusline(paths, cache=statusline_cache))
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
        if command.startswith("/help ") or command.startswith("/? "):
            topic = command.split(maxsplit=1)[1] if " " in command else ""
            topic_help = format_help_topic(topic)
            if topic_help is not None:
                output(topic_help)
            else:
                output(f"Unknown help topic: {topic.strip() or '(empty)'}")
                output("Topics: " + ", ".join(list_help_topics()))
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
        if command == "/people":
            run_people_command(paths, output_fn=output)
            continue
        if command == "/projects":
            run_projects_command(paths, output_fn=output)
            continue
        if command == "/config":
            run_config_command(paths, output_fn=output)
            continue
        if command == "/rebuild":
            output(run_repl_rebuild(paths))
            statusline_cache.invalidate()
            continue
        if command == "/resume":
            resume_result = run_resume_command(
                paths,
                input_fn=prompt,
                output_fn=output,
                ingest_runner=log_runner,
            )
            if _saved_record(resume_result):
                statusline_cache.invalidate()
            continue
        if command == "/log" or command.startswith("/log "):
            statement = command[4:].strip() if command.startswith("/log ") else ""
            if has_pending_log_session(paths):
                output("You have interrupted /log work pending. Run /resume to continue it.")
                choice = prompt("Start a new /log and discard pending work? [y/N]: ")
                if choice.strip().lower() not in {"y", "yes"}:
                    output("Cancelled. Pending work kept.")
                    continue
                clear_pending_log_session(paths)
            log_result = run_log_command(
                paths,
                statement=statement,
                input_fn=prompt,
                note_reader=note_reader,
                output_fn=output,
                ingest_runner=log_runner,
            )
            if _saved_record(log_result):
                statusline_cache.invalidate()
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


def _saved_record(result: object | None) -> bool:
    write_result = getattr(result, "write_result", None)
    return getattr(write_result, "path", None) is not None
