"""Shared system-facing Rich rendering helpers for REPL UX."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

OutputFn = Callable[[str], None]


def yanka_badge() -> Text:
    badge = Text()
    badge.append("yanka", style="bold purple")
    return badge


def print_system(output_fn: OutputFn, message: str) -> None:
    line = Text()
    line.append_text(yanka_badge())
    line.append("  ")
    line.append(message)
    _render_text(output_fn, line)


def print_hint(output_fn: OutputFn, message: str) -> None:
    _render_text(output_fn, Text(f"· {message}", style="italic dim"))


def print_statusline(output_fn: OutputFn, message: str) -> None:
    _render_text(output_fn, Text(message, style="dim"))


def print_clarifying_panel(output_fn: OutputFn, content: str) -> None:
    panel = Panel(
        Text(content.strip()),
        title=_panel_title("Clarifying"),
        border_style="purple",
        padding=(0, 1),
    )
    _render_panel(output_fn, panel)


def print_status_panel(output_fn: OutputFn, content: str) -> None:
    panel = Panel(
        Text(content),
        title=_panel_title("Status"),
        border_style="purple",
        padding=(0, 1),
    )
    _render_panel(output_fn, panel)


def _panel_title(label: str) -> Text:
    title = Text()
    title.append_text(yanka_badge())
    title.append("  ")
    title.append(label, style="bold purple")
    return title


def _render_panel(output_fn: OutputFn, panel: Panel) -> None:
    _console(output_fn).print(panel)


def _render_text(output_fn: OutputFn, line: Text) -> None:
    _console(output_fn).print(line)


def _console(output_fn: OutputFn) -> Console:
    return Console(file=_ConsoleFile(output_fn), force_terminal=False, width=120)


class Activity(Protocol):
    def update(self, message: str) -> None: ...
    def stop(self) -> None: ...


def start_activity(output_fn: OutputFn, message: str) -> Activity:
    if _use_rich_status(output_fn):
        status = Console().status(message, spinner="dots")
        status.start()
        return _RichActivity(status=status)
    print_hint(output_fn, message)
    return _FallbackActivity(output_fn=output_fn)


def _use_rich_status(output_fn: OutputFn) -> bool:
    return output_fn is print and sys.stdout.isatty()


@dataclass
class _RichActivity:
    status: Any

    def update(self, message: str) -> None:
        self.status.update(message)

    def stop(self) -> None:
        self.status.stop()


@dataclass
class _FallbackActivity:
    output_fn: OutputFn

    def update(self, message: str) -> None:
        print_hint(self.output_fn, message)

    def stop(self) -> None:
        return None


class _ConsoleFile:
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
