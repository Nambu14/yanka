"""Map exceptions to user-facing REPL messages — spec §12."""

from __future__ import annotations

from collections.abc import Callable

import click

from yanka.ingest.pipeline import IngestAbortError
from yanka.llm.client import (
    LlmAuthError,
    LlmError,
    LlmRateLimitError,
    LlmTimeoutError,
    LlmTransportError,
)

_RESUME_HINT = "Your progress is saved — run /resume to continue."


def format_user_error(exc: BaseException, *, command: str) -> list[str]:
    """Return user-facing lines for an error (no raw provider tracebacks)."""
    if isinstance(exc, IngestAbortError):
        lines = ["The record could not be written to disk."]
        if command == "log":
            lines.append(_RESUME_HINT)
        return lines

    if isinstance(exc, LlmTransportError):
        return _with_resume_hint(
            ["Could not reach the LLM provider. Check your network and try again."],
            command=command,
        )
    if isinstance(exc, LlmAuthError):
        return _with_resume_hint(
            [
                "The API key was rejected.",
                "Check keyring or environment variables for your provider.",
            ],
            command=command,
        )
    if isinstance(exc, LlmRateLimitError):
        return _with_resume_hint(
            ["The provider rate limit was hit. Wait a moment and try again."],
            command=command,
        )
    if isinstance(exc, LlmTimeoutError):
        return _with_resume_hint(
            ["The provider did not respond in time (45s). Try again."],
            command=command,
        )
    if isinstance(exc, LlmError):
        return _with_resume_hint(
            ["The request to the LLM provider failed. Try again."],
            command=command,
        )

    return ["Something went wrong. Try again."]


def emit_user_error(
    output_fn: Callable[[str], None],
    exc: BaseException,
    *,
    command: str,
) -> None:
    for line in format_user_error(exc, command=command):
        output_fn(line)


def repl_conflict_prompt(view, *, console=None) -> bool:
    """Conflict yes/no; Ctrl+C counts as No without Click's Aborted! banner."""
    from yanka.ui.conflict_confirm import default_conflict_prompt

    try:
        return default_conflict_prompt(view, console=console)
    except click.Abort:
        return False


def _with_resume_hint(lines: list[str], *, command: str) -> list[str]:
    if command == "log":
        return [*lines, _RESUME_HINT]
    return lines
