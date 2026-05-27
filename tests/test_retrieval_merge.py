from __future__ import annotations

from datetime import date

import pytest

from yanka.records.models import RecordStatus
from yanka.retrieval.graph_retrieve import GraphRetrievalHit
from yanka.retrieval.merge import (
    MergedRetrievalHit,
    RetrievalConfidence,
    merge_retrieval_hits,
)
from yanka.retrieval.query_analysis import QueryAnalysis, QueryFilters
from yanka.retrieval.vector_retrieve import VectorRetrievalHit
from yanka.retrieval_enums import QueryType, RetrievalSource


def _analysis(query_type: QueryType = QueryType.CURRENT_STATE) -> QueryAnalysis:
    return QueryAnalysis(
        query_type=query_type,
        filters=QueryFilters(),
        semantic_query="session storage",
        graph_hint="test",
    )


def _graph_hit(
    file_reference: str,
    *,
    status: str = RecordStatus.ACTIVE.value,
    summary: str | None = None,
) -> GraphRetrievalHit:
    return GraphRetrievalHit(
        file_reference=file_reference,
        date=date(2026, 5, 14),
        status=status,
        summary=summary or f"Graph {file_reference}",
        context_canonical="main-platform/auth-service",
    )


def _vector_hit(
    file_reference: str,
    *,
    status: str = RecordStatus.ACTIVE.value,
    score: float | None = 0.12,
    summary: str | None = None,
) -> VectorRetrievalHit:
    return VectorRetrievalHit(
        file_reference=file_reference,
        date=date(2026, 5, 14),
        status=status,
        summary=summary or f"Vector {file_reference}",
        context_path="main-platform/auth-service",
        score=score,
    )


def test_graph_only_hits_are_preserved_in_graph_order() -> None:
    graph_hits = [
        _graph_hit("records/a.md"),
        _graph_hit("records/b.md"),
    ]

    merged = merge_retrieval_hits(_analysis(), graph_hits, [])

    assert [hit.file_reference for hit in merged] == ["records/a.md", "records/b.md"]
    assert all(hit.sources == frozenset({RetrievalSource.GRAPH}) for hit in merged)
    assert all(hit.confidence is RetrievalConfidence.MEDIUM for hit in merged)


def test_graph_vector_duplicate_merges_sources_and_keeps_graph_metadata() -> None:
    graph_hit = _graph_hit("records/a.md", summary="Graph summary")
    vector_hit = _vector_hit("records/a.md", score=0.03, summary="Vector summary")

    merged = merge_retrieval_hits(_analysis(), [graph_hit], [vector_hit])

    assert merged == [
        MergedRetrievalHit(
            file_reference="records/a.md",
            date=date(2026, 5, 14),
            status=RecordStatus.ACTIVE.value,
            summary="Graph summary",
            context="main-platform/auth-service",
            sources=frozenset({RetrievalSource.GRAPH, RetrievalSource.VECTOR}),
            vector_score=0.03,
            confidence=RetrievalConfidence.HIGH,
        )
    ]


def test_vector_only_active_hits_are_appended_as_discovery() -> None:
    graph_hits = [_graph_hit("records/a.md")]
    vector_hits = [_vector_hit("records/b.md", score=0.2)]

    merged = merge_retrieval_hits(_analysis(), graph_hits, vector_hits)

    assert [hit.file_reference for hit in merged] == ["records/a.md", "records/b.md"]
    assert merged[1].sources == frozenset({RetrievalSource.VECTOR})
    assert merged[1].confidence is RetrievalConfidence.LOW
    assert merged[1].vector_score == 0.2


@pytest.mark.parametrize(
    "status",
    [
        RecordStatus.SUPERSEDED.value,
        RecordStatus.TENTATIVE.value,
        "archived",
    ],
)
def test_current_state_drops_vector_only_inactive_hits(status: str) -> None:
    vector_hits = [_vector_hit("records/old.md", status=status)]

    merged = merge_retrieval_hits(_analysis(QueryType.CURRENT_STATE), [], vector_hits)

    assert merged == []


def test_historical_keeps_vector_only_superseded_hits() -> None:
    vector_hits = [_vector_hit("records/old.md", status=RecordStatus.SUPERSEDED.value)]

    merged = merge_retrieval_hits(_analysis(QueryType.HISTORICAL), [], vector_hits)

    assert [hit.file_reference for hit in merged] == ["records/old.md"]
    assert merged[0].status == RecordStatus.SUPERSEDED.value


def test_limit_applies_after_merge_and_dedupe() -> None:
    graph_hits = [_graph_hit("records/a.md"), _graph_hit("records/b.md")]
    vector_hits = [
        _vector_hit("records/a.md", score=0.01),
        _vector_hit("records/c.md", score=0.02),
    ]

    merged = merge_retrieval_hits(_analysis(), graph_hits, vector_hits, limit=2)

    assert [hit.file_reference for hit in merged] == ["records/a.md", "records/b.md"]
    assert merged[0].sources == frozenset({RetrievalSource.GRAPH, RetrievalSource.VECTOR})


def test_invalid_limit_raises() -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        merge_retrieval_hits(_analysis(), [], [], limit=0)
