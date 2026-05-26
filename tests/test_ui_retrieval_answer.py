from __future__ import annotations

from datetime import date
from io import StringIO

from rich.console import Console

from whyline.records.models import RecordStatus
from whyline.retrieval import format_retrieval_answer
from whyline.retrieval.merge import MergedRetrievalHit, RetrievalConfidence
from whyline.retrieval_enums import RetrievalSource
from whyline.ui import render_retrieval_answer


def _capture(view) -> str:
    buffer = StringIO()
    console = Console(file=buffer, width=120, force_terminal=True, legacy_windows=False)
    console.print(render_retrieval_answer(view))
    return buffer.getvalue()


def _hit(
    file_reference: str,
    *,
    status: str = RecordStatus.ACTIVE.value,
    record_date: date = date(2026, 5, 14),
) -> MergedRetrievalHit:
    return MergedRetrievalHit(
        file_reference=file_reference,
        date=record_date,
        status=status,
        summary="Use PostgreSQL for sessions",
        context="main-platform/auth-service",
        sources=frozenset({RetrievalSource.GRAPH, RetrievalSource.VECTOR}),
        vector_score=0.03,
        confidence=RetrievalConfidence.HIGH,
    )


def test_render_retrieval_answer_shows_answer_citations_and_sources() -> None:
    view = format_retrieval_answer(
        "Sessions use PostgreSQL (source: current.md).",
        [_hit("records/current.md")],
        today=date(2026, 5, 26),
    )

    output = _capture(view)

    assert "Answer" in output
    assert "Sessions use PostgreSQL" in output
    assert "Citations" in output
    assert "current.md" in output
    assert "Use PostgreSQL for sessions" in output
    assert "source=graph+vector" in output
    assert "confidence=high" in output


def test_render_retrieval_answer_shows_stale_and_superseded_source() -> None:
    view = format_retrieval_answer(
        "Redis was used historically (source: old.md).",
        [
            _hit(
                "records/old.md",
                status=RecordStatus.SUPERSEDED.value,
                record_date=date(2026, 1, 1),
            )
        ],
        today=date(2026, 5, 26),
    )

    output = _capture(view)

    assert "Staleness" in output
    assert "records/old.md" in output
    assert "superseded" in output
    assert "stale" in output


def test_render_retrieval_answer_handles_empty_source_list() -> None:
    view = format_retrieval_answer("No relevant records found.", [], today=date(2026, 5, 26))

    output = _capture(view)

    assert "No relevant records found." in output
    assert "Sources" in output
    assert "(none)" in output
