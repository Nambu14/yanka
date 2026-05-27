from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from yanka.config import EmbeddingConfig
from yanka.embeddings import EMBEDDING_DIM, register_embedding_backend
from yanka.ingest.context_search import (
    format_related_records_for_prompt,
    search_related_records,
)
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.records.io import read_record, write_record
from yanka.records.models import Record, RecordBody, RecordStatus, RecordType
from yanka.vectors.indexing import index_record
from yanka.vectors.store import clear_vector_db_cache

pytest.importorskip("lancedb")

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "with-claims.md"


def _context_embed(
    texts: list[str],
    _config: EmbeddingConfig,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        lower = text.lower()
        if "redis" in lower or "session storage" in lower:
            vectors.append([1.0] + [0.0] * (EMBEDDING_DIM - 1))
        elif "kubernetes" in lower:
            vectors.append([0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2))
        else:
            vectors.append([0.0] * EMBEDDING_DIM)
    return vectors


@pytest.fixture(autouse=True)
def _embed_backend() -> None:
    clear_vector_db_cache()
    register_embedding_backend("test", _context_embed)
    yield
    clear_vector_db_cache()


def _unrelated_record() -> Record:
    return Record(
        date=date(2026, 4, 1),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=["main-platform", "infra"],
        decision="Migrate workloads to Kubernetes",
        body=RecordBody(rationale="Cluster capacity."),
        record_complete=True,
    )


def _seed_records(paths) -> None:
    config = EmbeddingConfig(provider="test", model="fake")
    redis_record = read_record(FIXTURE).record
    write_record(paths, redis_record, filename="2026-05-14-redis-sessions.md")
    redis_record.source_path = paths.records_dir / "2026-05-14-redis-sessions.md"
    index_record(redis_record, paths, config=config)

    k8s_record = _unrelated_record()
    write_record(paths, k8s_record, filename="2026-04-01-k8s-migration.md")
    k8s_record.source_path = paths.records_dir / "2026-04-01-k8s-migration.md"
    index_record(k8s_record, paths, config=config)


def test_search_related_records_returns_matching_record(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_records(paths)
    config = EmbeddingConfig(provider="test", model="fake")

    related = search_related_records(
        "We are dropping Redis for session storage",
        paths,
        limit=3,
        config=config,
    )

    assert len(related) >= 1
    assert related[0].path.name == "2026-05-14-redis-sessions.md"
    assert "Drop Redis for session storage" in related[0].record.decision


def test_format_related_records_for_prompt_includes_decision(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_records(paths)
    config = EmbeddingConfig(provider="test", model="fake")

    related = search_related_records(
        "session storage redis",
        paths,
        limit=1,
        config=config,
    )
    text = format_related_records_for_prompt(related)

    assert len(related) == 1
    assert "--- related record: 2026-05-14-redis-sessions.md ---" in text
    assert "Drop Redis for session storage" in text


def test_search_related_records_empty_when_no_index(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    config = EmbeddingConfig(provider="test", model="fake")

    related = search_related_records("session storage", paths, config=config)

    assert related == []
    assert format_related_records_for_prompt(related) == ""
