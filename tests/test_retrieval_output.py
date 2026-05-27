from __future__ import annotations

from datetime import date

from yanka.records.models import RecordStatus
from yanka.retrieval import extract_citations, format_retrieval_answer
from yanka.retrieval.merge import MergedRetrievalHit, RetrievalConfidence
from yanka.retrieval_enums import RetrievalSource


def _hit(
    file_reference: str = "records/current.md",
    *,
    status: str = RecordStatus.ACTIVE.value,
    record_date: date = date(2026, 5, 14),
    sources: frozenset[RetrievalSource] = frozenset(
        {RetrievalSource.GRAPH, RetrievalSource.VECTOR}
    ),
) -> MergedRetrievalHit:
    return MergedRetrievalHit(
        file_reference=file_reference,
        date=record_date,
        status=status,
        summary="Use PostgreSQL for sessions",
        context="main-platform/auth-service",
        sources=sources,
        vector_score=0.03,
        confidence=RetrievalConfidence.HIGH,
    )


def test_extract_citations_from_source_parentheses() -> None:
    answer = (
        "Sessions use PostgreSQL (source: current.md). "
        "Redis is historical (source: old.md, current.md)."
    )

    assert extract_citations(answer) == ["current.md", "old.md"]


def test_format_retrieval_answer_preserves_source_metadata() -> None:
    view = format_retrieval_answer(
        "Sessions use PostgreSQL (source: current.md).",
        [_hit()],
        today=date(2026, 5, 26),
    )

    assert view.answer.startswith("Sessions use PostgreSQL")
    assert view.citations == ["current.md"]
    assert view.has_staleness_warning is False
    assert len(view.sources) == 1
    source = view.sources[0]
    assert source.file_reference == "records/current.md"
    assert source.filename == "current.md"
    assert source.status == RecordStatus.ACTIVE.value
    assert source.summary == "Use PostgreSQL for sessions"
    assert source.context == "main-platform/auth-service"
    assert source.sources == frozenset({RetrievalSource.GRAPH, RetrievalSource.VECTOR})
    assert source.confidence is RetrievalConfidence.HIGH
    assert source.vector_score == 0.03


def test_format_retrieval_answer_flags_stale_sources() -> None:
    stale_hit = _hit(
        "records/old.md",
        record_date=date(2026, 1, 1),
        sources=frozenset({RetrievalSource.VECTOR}),
    )

    view = format_retrieval_answer(
        "Old answer (source: old.md).",
        [stale_hit],
        today=date(2026, 5, 1),
    )

    assert view.has_staleness_warning is True
    assert view.stale_sources == ["records/old.md"]
    assert view.sources[0].is_stale is True


def test_format_retrieval_answer_marks_superseded_sources() -> None:
    view = format_retrieval_answer(
        "History includes Redis (source: old.md).",
        [_hit("records/old.md", status=RecordStatus.SUPERSEDED.value)],
        today=date(2026, 5, 26),
    )

    assert view.sources[0].is_superseded is True
    assert view.sources[0].status == RecordStatus.SUPERSEDED.value


def test_format_retrieval_answer_allows_no_sources() -> None:
    view = format_retrieval_answer("No relevant records found.", [], today=date(2026, 5, 26))

    assert view.sources == []
    assert view.citations == []
    assert view.has_staleness_warning is False
