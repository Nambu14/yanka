from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from whyline.config import EmbeddingConfig
from whyline.embeddings import EMBEDDING_DIM, register_embedding_backend
from whyline.paths import ensure_data_layout, resolve_data_paths
from whyline.records.io import read_record
from whyline.records.models import RecordStatus
from whyline.retrieval.query_analysis import QueryAnalysis, QueryFilters, TimeRange
from whyline.retrieval.vector_retrieve import VectorRetrievalHit, retrieve_from_vector
from whyline.retrieval_enums import QueryType, StatusFilter
from whyline.vectors.indexing import index_record
from whyline.vectors.store import clear_vector_db_cache

pytest.importorskip("lancedb")

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "with-claims.md"


def _search_embed(
    texts: list[str],
    _config: EmbeddingConfig,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        lower = text.lower()
        if "postgresql" in lower or "session storage" in lower:
            vectors.append([1.0] + [0.0] * (EMBEDDING_DIM - 1))
        elif "redis" in lower:
            vectors.append([0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2))
        elif "kubernetes" in lower or "migration" in lower:
            vectors.append([0.0, 0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 3))
        else:
            vectors.append([0.0] * EMBEDDING_DIM)
    return vectors


@pytest.fixture(autouse=True)
def _setup_embed_backend() -> None:
    clear_vector_db_cache()
    register_embedding_backend("test", _search_embed)
    yield
    clear_vector_db_cache()


def _index_record(paths, filename: str, *, status: RecordStatus = RecordStatus.ACTIVE) -> None:
    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / filename
    record.status = status
    config = EmbeddingConfig(provider="test", model="fake")
    index_record(record, paths, config=config)


def _seed_vectors(paths) -> None:
    _index_record(paths, "active-session.md", status=RecordStatus.ACTIVE)
    _index_record(paths, "old-session.md", status=RecordStatus.SUPERSEDED)


def _analysis(
    query_type: QueryType,
    *,
    project: str | None = "main-platform",
    context_keywords: list[str] | None = None,
    people: list[str] | None = None,
    status_filter: StatusFilter | None = None,
    semantic_query: str | None = None,
    time_range: TimeRange | None = None,
) -> QueryAnalysis:
    return QueryAnalysis(
        query_type=query_type,
        filters=QueryFilters(
            project=project,
            context_keywords=["auth"] if context_keywords is None else context_keywords,
            people=people or [],
            status_filter=status_filter,
            time_range=time_range,
        ),
        semantic_query=semantic_query,
        graph_hint="test",
    )


def test_current_state_returns_active_only(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_vectors(paths)
    config = EmbeddingConfig(provider="test", model="fake")

    hits = retrieve_from_vector(
        _analysis(QueryType.CURRENT_STATE, semantic_query="session storage"),
        paths,
        config=config,
        limit=10,
    )

    assert len(hits) == 1
    assert hits[0].file_reference.endswith("active-session.md")
    assert hits[0].status == "active"
    assert hits[0].source == "vector"
    assert isinstance(hits[0], VectorRetrievalHit)


def test_historical_includes_superseded(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_vectors(paths)
    config = EmbeddingConfig(provider="test", model="fake")

    hits = retrieve_from_vector(
        _analysis(
            QueryType.HISTORICAL,
            semantic_query="session storage",
            status_filter=StatusFilter.ALL,
        ),
        paths,
        config=config,
        limit=10,
    )

    refs = {hit.file_reference for hit in hits}
    assert any(ref.endswith("active-session.md") for ref in refs)
    assert any(ref.endswith("old-session.md") for ref in refs)


def test_specific_decision_semantic_match(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _index_record(paths, "redis-topic.md")
    config = EmbeddingConfig(provider="test", model="fake")

    hits = retrieve_from_vector(
        _analysis(
            QueryType.SPECIFIC_DECISION,
            context_keywords=[],
            semantic_query="redis",
        ),
        paths,
        config=config,
        limit=5,
    )

    assert len(hits) == 1
    assert hits[0].file_reference.endswith("redis-topic.md")


def test_exploratory_without_status_filter(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_vectors(paths)
    config = EmbeddingConfig(provider="test", model="fake")

    hits = retrieve_from_vector(
        _analysis(
            QueryType.EXPLORATORY,
            semantic_query="session storage",
            status_filter=None,
        ),
        paths,
        config=config,
        limit=10,
    )

    assert len(hits) >= 1


def test_relationship_uses_semantic_query(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / "k8s.md"
    record.context_path = ["main-platform", "infra"]
    record.decision = "Kubernetes migration completed"
    config = EmbeddingConfig(provider="test", model="fake")
    index_record(record, paths, config=config)

    hits = retrieve_from_vector(
        _analysis(
            QueryType.RELATIONSHIP,
            context_keywords=["infra"],
            semantic_query="kubernetes migration",
        ),
        paths,
        config=config,
        limit=5,
    )

    assert any(hit.file_reference.endswith("k8s.md") for hit in hits)


def test_person_without_semantic_query_returns_empty(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_vectors(paths)

    hits = retrieve_from_vector(
        _analysis(
            QueryType.PERSON,
            context_keywords=[],
            people=["Carlos"],
            semantic_query=None,
        ),
        paths,
    )

    assert hits == []


def test_person_with_semantic_query_supplements(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_vectors(paths)
    config = EmbeddingConfig(provider="test", model="fake")

    hits = retrieve_from_vector(
        _analysis(
            QueryType.PERSON,
            people=["Carlos"],
            semantic_query="session storage",
        ),
        paths,
        config=config,
        limit=5,
    )

    assert len(hits) >= 1


def test_time_range_filter_excludes_old_records(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / "recent.md"
    record.date = date(2026, 5, 14)
    config = EmbeddingConfig(provider="test", model="fake")
    index_record(record, paths, config=config)

    record_old = read_record(FIXTURE).record
    record_old.source_path = paths.records_dir / "ancient.md"
    record_old.date = date(2020, 1, 1)
    index_record(record_old, paths, config=config)

    hits = retrieve_from_vector(
        _analysis(
            QueryType.CURRENT_STATE,
            semantic_query="session storage",
            time_range=TimeRange(after=date(2026, 1, 1)),
        ),
        paths,
        config=config,
        limit=10,
    )

    refs = {hit.file_reference for hit in hits}
    assert any(ref.endswith("recent.md") for ref in refs)
    assert not any(ref.endswith("ancient.md") for ref in refs)
