"""Shared REPL callback types."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from yanka.ui.console_file import OutputFn

PromptFn = Callable[[str], str]
NoteReader = Callable[[], str]
LogRunner = Callable[..., Any]
AskRunner = Callable[..., Any]
AnswerDisplayFn = Callable[[Any, OutputFn], None]

__all__ = [
    "AnswerDisplayFn",
    "AskRunner",
    "LogRunner",
    "NoteReader",
    "OutputFn",
    "PromptFn",
]
