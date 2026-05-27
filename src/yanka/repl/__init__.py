"""Interactive slash-command REPL — spec §11."""

from yanka.repl.commands.ask import run_ask_command
from yanka.repl.commands.log import run_log_command
from yanka.repl.commands.rebuild import run_repl_rebuild
from yanka.repl.commands.resume import run_resume_command
from yanka.repl.constants import HELP_TEXT, PROMPT
from yanka.repl.errors import emit_user_error, format_user_error, repl_conflict_prompt
from yanka.repl.format import (
    format_history,
    format_last,
    format_status,
    format_statusline,
)
from yanka.repl.loop import run_repl
from yanka.repl.prompts import (
    SLASH_COMMANDS,
    build_prompt_adapters,
    format_last_model_reply,
    prompt_log_user,
    read_note_multiline,
    repl_history_path,
)
from yanka.repl.types import (
    AnswerDisplayFn,
    AskRunner,
    LogRunner,
    NoteReader,
    OutputFn,
    PromptFn,
)

_build_prompt_adapters = build_prompt_adapters
_format_last_model_reply = format_last_model_reply
_prompt_log_user = prompt_log_user
_read_note_multiline = read_note_multiline
_repl_history_path = repl_history_path


def _slash_commands() -> tuple[str, ...]:
    return SLASH_COMMANDS


__all__ = [
    "HELP_TEXT",
    "PROMPT",
    "AnswerDisplayFn",
    "AskRunner",
    "LogRunner",
    "NoteReader",
    "OutputFn",
    "PromptFn",
    "emit_user_error",
    "format_history",
    "format_user_error",
    "format_last",
    "format_status",
    "format_statusline",
    "run_ask_command",
    "run_log_command",
    "run_repl",
    "run_repl_rebuild",
    "run_resume_command",
    "repl_conflict_prompt",
]
