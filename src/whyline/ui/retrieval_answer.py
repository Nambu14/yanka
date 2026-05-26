"""Retrieval answer Rich rendering — spec §11."""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from whyline.records.models import RecordStatus
from whyline.retrieval.output import RetrievalAnswerView, RetrievalSourceView
from whyline.retrieval_enums import RetrievalSource


def render_retrieval_answer(view: RetrievalAnswerView) -> Panel:
    """Build a subtle retrieval answer panel with source metadata."""
    return Panel(
        _panel_body(view),
        title=_panel_title(),
        border_style="blue",
        padding=(1, 2),
    )


def _panel_title() -> Text:
    title = Text()
    title.append("whyline", style="bold purple")
    title.append("  ")
    title.append("Answer", style="bold blue")
    return title


def _panel_body(view: RetrievalAnswerView) -> Group:
    parts: list[Text] = [Text(view.answer)]
    if view.citations:
        parts.append(_labeled_line("Citations", ", ".join(view.citations), style="blue"))
    if view.has_staleness_warning:
        parts.append(
            _labeled_line(
                "Staleness",
                f"Some sources are 90+ days old: {', '.join(view.stale_sources)}",
                style="yellow",
            )
        )
    parts.append(Text(""))
    parts.append(Text("Sources:", style="bold purple"))
    if not view.sources:
        parts.append(Text("  (none)", style="dim"))
    else:
        for source in view.sources:
            parts.append(_source_line(source))
    return Group(*parts)


def _labeled_line(label: str, value: str, *, style: str = "") -> Text:
    line = Text()
    line.append(f"{label}: ", style="bold purple")
    line.append(value, style=style or None)
    return line


def _source_line(source: RetrievalSourceView) -> Text:
    line = Text("  • ")
    line.append(source.filename, style=_status_style(source.status))
    line.append(f" [{source.status}]", style=_status_style(source.status))
    line.append(f" {source.date.isoformat()}", style="dim")
    line.append(f" — {source.summary}")
    line.append(f" ({source.context})", style="dim")
    line.append(f" source={_format_sources(source)}", style="dim")
    line.append(f" confidence={source.confidence.value}", style="dim")
    if source.is_stale:
        line.append(" stale", style="yellow")
    return line


def _status_style(status: str) -> str:
    if status == RecordStatus.ACTIVE.value:
        return "green"
    if status == RecordStatus.SUPERSEDED.value:
        return "red"
    if status == RecordStatus.TENTATIVE.value:
        return "yellow"
    return "dim"


def _format_sources(source: RetrievalSourceView) -> str:
    order = (RetrievalSource.GRAPH, RetrievalSource.VECTOR)
    return "+".join(item.value for item in order if item in source.sources)
