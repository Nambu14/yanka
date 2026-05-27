from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from yanka.config import EmbeddingConfig
from yanka.embeddings import EMBEDDING_DIM, register_embedding_backend
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.records.io import read_record
from yanka.records.models import RecordStatus
from yanka.vectors.filters import VectorSearchFilters, build_where_clause
from yanka.vectors.indexing import index_claims, index_record
from yanka.vectors.search import search_claims, search_records
from yanka.vectors.store import clear_vector_db_cache

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
        else:
            vectors.append([0.0] * EMBEDDING_DIM)
    return vectors


@pytest.fixture(autouse=True)
def _setup_embed_backend() -> None:
    clear_vector_db_cache()
    register_embedding_backend("test", _search_embed)
    yield
    clear_vector_db_cache()


def _index_fixture(paths, tmp_name: str = "2026-05-14-redis-session.md") -> None:
    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / tmp_name
    config = EmbeddingConfig(provider="test", model="fake")
    index_record(record, paths, config=config)
    index_claims(record, paths, config=config)


def test_build_where_clause_includes_date_bounds() -> None:
    clause = build_where_clause(
        VectorSearchFilters(
            status="active",
            date_after=date(2026, 4, 1),
            date_before=date(2026, 5, 1),
        )
    )
    assert clause is not None
    assert "date >= DATE '2026-04-01'" in clause
    assert "date <= DATE '2026-05-01'" in clause


def test_build_where_clause_combines_filters() -> None:
    clause = build_where_clause(
        VectorSearchFilters(
            status="active",
            project="main-platform",
            context_path_prefix="main-platform/auth",
        )
    )
    assert clause is not None
    assert "status = 'active'" in clause
    assert "project = 'main-platform'" in clause
    assert "context_path LIKE 'main-platform/auth%'" in clause


def test_search_records_filters_by_project_and_status(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _index_fixture(paths)
    config = EmbeddingConfig(provider="test", model="fake")

    hits = search_records(
        "session storage",
        paths,
        filters=VectorSearchFilters(status="active", project="main-platform"),
        limit=5,
        config=config,
    )

    assert len(hits) == 1
    assert hits[0]["file_reference"].endswith("redis-session.md")
    assert hits[0]["status"] == "active"


def test_search_records_context_path_prefix(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _index_fixture(paths)
    config = EmbeddingConfig(provider="test", model="fake")

    hits = search_records(
        [1.0] + [0.0] * (EMBEDDING_DIM - 1),
        paths,
        filters=VectorSearchFilters(context_path_prefix="main-platform/auth"),
        limit=5,
        config=config,
    )

    assert len(hits) == 1
    assert hits[0]["context_path"].startswith("main-platform/auth")


def test_search_records_excludes_wrong_status(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / "archived.md"
    record.status = RecordStatus.SUPERSEDED
    config = EmbeddingConfig(provider="test", model="fake")
    index_record(record, paths, config=config)

    hits = search_records(
        "session storage",
        paths,
        filters=VectorSearchFilters(status="active"),
        config=config,
    )

    assert hits == []


def test_search_claims_filters_by_status(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _index_fixture(paths)
    config = EmbeddingConfig(provider="test", model="fake")

    hits = search_claims(
        "PostgreSQL",
        paths,
        filters=VectorSearchFilters(status="active"),
        limit=5,
        config=config,
    )

    assert len(hits) == 1
    assert hits[0]["claim_id"].endswith(":c1")
    assert hits[0]["status"] == "active"


def test_search_claims_status_filter_excludes_other_statuses(
    tmp_path: Path,
) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _index_fixture(paths)
    config = EmbeddingConfig(provider="test", model="fake")

    active_hits = search_claims(
        "Redis is not used for sessions",
        paths,
        filters=VectorSearchFilters(status="active"),
        config=config,
    )
    assert not any(hit["claim_id"].endswith(":c2") for hit in active_hits)

    tentative_hits = search_claims(
        "Redis is not used for sessions",
        paths,
        filters=VectorSearchFilters(status="tentative"),
        limit=5,
        config=config,
    )
    assert len(tentative_hits) == 1
    assert tentative_hits[0]["claim_id"].endswith(":c2")
