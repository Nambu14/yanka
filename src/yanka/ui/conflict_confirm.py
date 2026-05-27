"""Conflict confirmation UI — spec §11 conflict detection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from yanka.ingest.conflict_confirmation import ConflictPromptView


def default_conflict_prompt(
    view: ConflictPromptView,
    *,
    console: Console | None = None,
) -> bool:
    """Render an amber conflict panel and ask yes/no via click."""
    target = console if console is not None else Console()
    target.print(render_conflict_prompt(view))
    return click.confirm("  Supersede the previous claim?", default=False)


def render_conflict_prompt(view: ConflictPromptView) -> Panel:
    """Build the amber-bordered conflict comparison panel."""
    return Panel(
        _panel_body(view),
        title=_panel_title(),
        border_style="yellow",
        padding=(1, 2),
    )


def _panel_title() -> Text:
    title = Text()
    title.append("yanka", style="bold purple")
    title.append("  ")
    title.append("Possible conflict", style="bold yellow")
    return title


def _panel_body(view: ConflictPromptView) -> RenderableType:
    lines: list[RenderableType] = []
    lines.append(_labeled_line("Previous", view.old_content, style="strike red"))
    lines.append(_labeled_line("New", view.new_content, style="bold green"))
    lines.append(Text(""))
    reason = Text()
    reason.append("Why: ", style="dim")
    reason.append(view.detected.reason)
    lines.append(reason)
    return Text("\n").join(lines)


def _labeled_line(label: str, value: str, *, style: str = "") -> Text:
    line = Text()
    line.append(f"{label}: ", style="bold purple")
    line.append(value, style=style or None)
    return line
