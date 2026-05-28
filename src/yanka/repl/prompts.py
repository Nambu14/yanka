"""REPL input adapters and /log conversation helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from yanka.paths import DataPaths
from yanka.repl.types import NoteReader, OutputFn, PromptFn
from yanka.ui import print_clarifying_panel

SLASH_COMMANDS = (
    "/log",
    "/ask",
    "/status",
    "/history",
    "/last",
    "/people",
    "/projects",
    "/config",
    "/rebuild",
    "/resume",
    "/help",
    "/exit",
    "/?",
    "/h",
    "/q",
)


@dataclass(frozen=True)
class PromptAdapters:
    prompt: PromptFn
    read_note: NoteReader


def build_prompt_adapters(paths: DataPaths) -> PromptAdapters | None:
    """Return prompt_toolkit session adapters, or None if not installed."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory
    except ImportError:
        return None

    history_path = repl_history_path(paths)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    session = PromptSession(history=FileHistory(str(history_path)))
    completer = WordCompleter(SLASH_COMMANDS, ignore_case=True, sentence=True)

    def prompt_fn(prompt_text: str) -> str:
        return session.prompt(prompt_text, completer=completer)

    def read_note() -> str:
        return read_note_multiline(prompt_fn)

    return PromptAdapters(prompt=prompt_fn, read_note=read_note)


def repl_history_path(paths: DataPaths) -> Path:
    return paths.data_dir / "repl_history.txt"


def read_note_multiline(prompt: PromptFn) -> str:
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


def prompt_log_user(
    assistant_message: str,
    *,
    input_fn: PromptFn,
    output_fn: OutputFn,
    before_prompt: Callable[[], None] | None = None,
) -> str:
    if before_prompt is not None:
        before_prompt()
    if looks_like_json_payload(assistant_message):
        output_fn("Model returned structured JSON early; finalizing record...")
        return "CONVERSATION ENDED. Output ONLY the final record now — no questions."

    output_fn("")
    print_clarifying_panel(output_fn, assistant_message)
    output_fn("")
    reply = input_fn("  Your reply: ")
    if not reply.strip():
        return "CONVERSATION ENDED. Output ONLY the final record now — no questions."
    return reply


def ask_log_user(
    question: str,
    *,
    input_fn: PromptFn,
    output_fn: OutputFn,
    before_prompt: Callable[[], None] | None = None,
) -> str:
    if before_prompt is not None:
        before_prompt()
    output_fn("")
    output_fn(question)
    return input_fn("  Your answer: ")


def format_last_model_reply(reply: str, *, max_chars: int = 500) -> str:
    """Keep failed extraction diagnostics readable in the REPL."""
    stripped = reply.strip()
    if len(stripped) <= max_chars:
        return stripped
    return f"{stripped[:max_chars].rstrip()}..."


def looks_like_json_payload(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") and stripped.endswith("}")
