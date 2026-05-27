"""Route Rich console output through a plain text callback."""

from __future__ import annotations

from collections.abc import Callable

OutputFn = Callable[[str], None]


class ConsoleFile:
    """File-like object that forwards Rich output lines to ``output_fn``."""

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
