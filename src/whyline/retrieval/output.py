"""Structured retrieval answer output — spec §8 step 5."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from whyline.records.models import RecordStatus
from whyline.retrieval.merge import MergedRetrievalHit, RetrievalConfidence
from whyline.retrieval_enums import RetrievalSource

_CITATION_PATTERN = re.compile(r"\(source:\s*([^)]+?)\)", re.IGNORECASE)
_STALE_AFTER_DAYS = 90


@dataclass(frozen=True)
class RetrievalSourceView:
    """Source metadata shown with a retrieval answer."""

    file_reference: str
    filename: str
    status: str
    summary: str
    context: str
    date: date
    sources: frozenset[RetrievalSource]
    confidence: RetrievalConfidence
    vector_score: float | None
    is_stale: bool
    is_superseded: bool


@dataclass(frozen=True)
class RetrievalAnswerView:
    """Display-ready retrieval answer with citations and source metadata."""

    answer: str
    sources: list[RetrievalSourceView]
    citations: list[str]
    stale_sources: list[str]
    has_staleness_warning: bool


def format_retrieval_answer(
    answer: str,
    merged_hits: list[MergedRetrievalHit],
    *,
    today: date | None = None,
) -> RetrievalAnswerView:
    """Build a display-ready retrieval answer view."""
    reference_date = today if today is not None else date.today()
    sources = [_source_view(hit, reference_date) for hit in merged_hits]
    stale_sources = [source.file_reference for source in sources if source.is_stale]
    return RetrievalAnswerView(
        answer=answer,
        sources=sources,
        citations=extract_citations(answer),
        stale_sources=stale_sources,
        has_staleness_warning=bool(stale_sources),
    )


def extract_citations(answer: str) -> list[str]:
    """Extract ``(source: filename.md)`` citations from synthesized text."""
    citations: list[str] = []
    seen: set[str] = set()
    for match in _CITATION_PATTERN.finditer(answer):
        for citation in _split_citation_group(match.group(1)):
            if citation in seen:
                continue
            seen.add(citation)
            citations.append(citation)
    return citations


def _source_view(hit: MergedRetrievalHit, today: date) -> RetrievalSourceView:
    return RetrievalSourceView(
        file_reference=hit.file_reference,
        filename=_filename(hit.file_reference),
        status=hit.status,
        summary=hit.summary,
        context=hit.context,
        date=hit.date,
        sources=hit.sources,
        confidence=hit.confidence,
        vector_score=hit.vector_score,
        is_stale=_is_stale(hit.date, today),
        is_superseded=hit.status == RecordStatus.SUPERSEDED.value,
    )


def _split_citation_group(value: str) -> list[str]:
    parts = re.split(r"\s*,\s*|\s+and\s+", value.strip())
    return [part.strip() for part in parts if part.strip()]


def _filename(file_reference: str) -> str:
    return file_reference.rsplit("/", maxsplit=1)[-1]


def _is_stale(record_date: date, today: date) -> bool:
    return (today - record_date).days >= _STALE_AFTER_DAYS
