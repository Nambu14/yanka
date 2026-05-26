"""Post-write confirmation panel — spec §7 step 10, §11 record confirmation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.text import Text

from whyline.records.models import Claim, ClaimStatus, Record

if TYPE_CHECKING:
    from whyline.ingest.write import WriteResult

_REBUILD_HINT = "Indexing incomplete — run `whyline rebuild` to fix."


@dataclass
class IngestConfirmationView:
    """Fields shown in the record-saved confirmation panel."""

    filename: str
    context_path: list[str]
    decision: str
    claims: list[Claim] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    superseded_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def confirmation_view_from_record(
    record: Record,
    *,
    path: Path | None = None,
    write_result: WriteResult | None = None,
    extra_warnings: list[str] | None = None,
) -> IngestConfirmationView:
    """Build a confirmation view from a written record and optional write outcome."""
    filename = path.name if path is not None else _filename_from_record(record)
    warnings = list(extra_warnings or [])
    warnings.extend(_warnings_from_write_result(write_result))
    return IngestConfirmationView(
        filename=filename,
        context_path=list(record.context_path),
        decision=record.decision,
        claims=list(record.claims),
        tags=list(record.tags),
        superseded_files=_superseded_files(record),
        warnings=warnings,
    )


def render_ingest_confirmation(
    view: IngestConfirmationView,
    *,
    console: Console | None = None,
) -> None:
    """Print the green-bordered record confirmation panel."""
    target = console if console is not None else Console()
    target.print(_build_panel(view))


def _build_panel(view: IngestConfirmationView) -> Panel:
    return Panel(
        _panel_body(view),
        title=_panel_title(),
        border_style="green",
        padding=(1, 2),
    )


def _panel_title() -> Text:
    title = Text()
    title.append("whyline", style="bold purple")
    title.append("  ")
    title.append("Record saved", style="bold green")
    return title


def _panel_body(view: IngestConfirmationView) -> RenderableType:
    lines: list[RenderableType] = []
    lines.append(_labeled_line("Context", _format_context_path(view.context_path)))
    lines.append(_labeled_line("Decision", view.decision))
    lines.extend(_claims_section(view.claims))
    if view.superseded_files:
        lines.append(_labeled_line("Supersedes", ", ".join(view.superseded_files)))
    if view.tags:
        lines.append(_labeled_line("Tags", ", ".join(view.tags)))
    lines.append(_labeled_line("File", view.filename, style="dim"))
    lines.extend(_warnings_section(view.warnings))
    return Text("\n").join(lines)


def _labeled_line(label: str, value: str, *, style: str = "") -> Text:
    line = Text()
    line.append(f"{label}: ", style="bold purple")
    line.append(value, style=style or None)
    return line


def _claims_section(claims: list[Claim]) -> list[RenderableType]:
    if not claims:
        return [_labeled_line("Claims", "(none)", style="dim")]

    header = Text()
    header.append("Claims:", style="bold purple")
    rows: list[RenderableType] = [header]
    for claim in claims:
        rows.append(_claim_line(claim))
    return rows


def _claim_line(claim: Claim) -> Text:
    line = Text("  • ", style="green")
    line.append(f"{claim.id} — {claim.content}")
    if claim.status == ClaimStatus.TENTATIVE:
        line.append(" (tentative)", style="bold yellow")
    return line


def _warnings_section(warnings: list[str]) -> list[RenderableType]:
    if not warnings:
        return []
    rows: list[RenderableType] = [Text("")]
    for warning in warnings:
        row = Text("⚠ ", style="bold yellow")
        row.append(warning, style="yellow")
        rows.append(row)
    return rows


def _format_context_path(context_path: list[str]) -> str:
    if not context_path:
        return "(none)"
    return " / ".join(context_path)


def _superseded_files(record: Record) -> list[str]:
    files: list[str] = []
    if record.supersedes:
        files.append(record.supersedes)
    for claim in record.claims:
        if claim.supersedes is not None:
            files.append(claim.supersedes.file)
    seen: set[str] = set()
    unique: list[str] = []
    for name in files:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def _filename_from_record(record: Record) -> str:
    if record.source_path is not None:
        return record.source_path.name
    return "(unsaved)"


def _warnings_from_write_result(result: WriteResult | None) -> list[str]:
    if result is None:
        return []
    if result.graph_ok and result.vectors_ok:
        return []
    warnings = [_REBUILD_HINT]
    warnings.extend(result.index_errors)
    return warnings
