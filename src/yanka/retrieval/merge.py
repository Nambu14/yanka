"""Graph-anchored merge for retrieval hits — spec §8 step 3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from yanka.records.models import RecordStatus
from yanka.retrieval.graph_retrieve import GraphRetrievalHit
from yanka.retrieval.query_analysis import QueryAnalysis
from yanka.retrieval.vector_retrieve import VectorRetrievalHit
from yanka.retrieval_enums import QueryType, RetrievalSource


class RetrievalConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class MergedRetrievalHit:
    """A retrieval hit after graph/vector dedupe and source merging."""

    file_reference: str
    date: date
    status: str
    summary: str
    context: str
    sources: frozenset[RetrievalSource]
    vector_score: float | None
    confidence: RetrievalConfidence


def merge_retrieval_hits(
    analysis: QueryAnalysis,
    graph_hits: list[GraphRetrievalHit],
    vector_hits: list[VectorRetrievalHit],
    *,
    limit: int | None = None,
) -> list[MergedRetrievalHit]:
    """Merge graph and vector hits with graph order as the retrieval skeleton."""
    if limit is not None and limit < 1:
        msg = "limit must be at least 1"
        raise ValueError(msg)

    vector_by_ref = _first_vector_by_ref(vector_hits)
    merged: list[MergedRetrievalHit] = []
    seen: set[str] = set()

    for graph_hit in graph_hits:
        vector_hit = vector_by_ref.get(graph_hit.file_reference)
        merged.append(_merged_from_graph_hit(graph_hit, vector_hit))
        seen.add(graph_hit.file_reference)

    for vector_hit in vector_hits:
        if vector_hit.file_reference in seen:
            continue
        if not _allow_vector_only_hit(analysis, vector_hit):
            continue
        merged.append(_merged_from_vector_hit(vector_hit))
        seen.add(vector_hit.file_reference)

    if limit is None:
        return merged
    return merged[:limit]


def _first_vector_by_ref(
    vector_hits: list[VectorRetrievalHit],
) -> dict[str, VectorRetrievalHit]:
    by_ref: dict[str, VectorRetrievalHit] = {}
    for hit in vector_hits:
        by_ref.setdefault(hit.file_reference, hit)
    return by_ref


def _merged_from_graph_hit(
    graph_hit: GraphRetrievalHit,
    vector_hit: VectorRetrievalHit | None,
) -> MergedRetrievalHit:
    if vector_hit is None:
        return MergedRetrievalHit(
            file_reference=graph_hit.file_reference,
            date=graph_hit.date,
            status=graph_hit.status,
            summary=graph_hit.summary,
            context=graph_hit.context_canonical,
            sources=frozenset({RetrievalSource.GRAPH}),
            vector_score=None,
            confidence=RetrievalConfidence.MEDIUM,
        )

    return MergedRetrievalHit(
        file_reference=graph_hit.file_reference,
        date=graph_hit.date,
        status=graph_hit.status,
        summary=graph_hit.summary,
        context=graph_hit.context_canonical,
        sources=frozenset({RetrievalSource.GRAPH, RetrievalSource.VECTOR}),
        vector_score=vector_hit.score,
        confidence=RetrievalConfidence.HIGH,
    )


def _merged_from_vector_hit(vector_hit: VectorRetrievalHit) -> MergedRetrievalHit:
    return MergedRetrievalHit(
        file_reference=vector_hit.file_reference,
        date=vector_hit.date,
        status=vector_hit.status,
        summary=vector_hit.summary,
        context=vector_hit.context_path,
        sources=frozenset({RetrievalSource.VECTOR}),
        vector_score=vector_hit.score,
        confidence=RetrievalConfidence.LOW,
    )


def _allow_vector_only_hit(
    analysis: QueryAnalysis,
    vector_hit: VectorRetrievalHit,
) -> bool:
    if analysis.query_type is not QueryType.CURRENT_STATE:
        return True
    return vector_hit.status == RecordStatus.ACTIVE.value
