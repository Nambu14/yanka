from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from yanka.config import EmbeddingConfig
from yanka.embeddings import EMBEDDING_DIM, register_embedding_backend
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.records.io import read_record
from yanka.vectors.claims import get_claims_table
from yanka.vectors.indexing import index_claims
from yanka.vectors.store import clear_vector_db_cache

pytest.importorskip("lancedb")

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "with-claims.md"


def _claim_aware_embed(
    texts: list[str],
    _config: EmbeddingConfig,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        lower = text.lower()
        if "postgresql" in lower:
            vectors.append([1.0] + [0.0] * (EMBEDDING_DIM - 1))
        elif "redis is not" in lower:
            vectors.append([0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2))
        else:
            vectors.append([0.0] * EMBEDDING_DIM)
    return vectors


@pytest.fixture(autouse=True)
def _setup_embed_backend() -> None:
    clear_vector_db_cache()
    register_embedding_backend("test", _claim_aware_embed)
    yield
    clear_vector_db_cache()


def test_index_claims_writes_one_row_per_claim(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / "2026-05-14-redis-session.md"
    config = EmbeddingConfig(provider="test", model="fake")

    claim_ids = index_claims(record, paths, config=config)

    assert claim_ids == [
        "records/2026-05-14-redis-session.md:c1",
        "records/2026-05-14-redis-session.md:c2",
    ]
    table = get_claims_table(paths)
    assert table.count_rows() == 2


def test_index_claims_claim_wording_hit(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / "decision.md"
    config = EmbeddingConfig(provider="test", model="fake")
    index_claims(record, paths, config=config)

    table = get_claims_table(paths)
    query = np.array([1.0] + [0.0] * (EMBEDDING_DIM - 1), dtype=np.float32)
    hit = table.search(query).limit(1).to_list()[0]
    assert hit["claim_id"].endswith(":c1")
    assert hit["content"] == "Session data is stored in PostgreSQL"
    assert hit["project"] == "main-platform"
    assert hit["status"] == "active"

    query_redis = np.array([0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2), dtype=np.float32)
    hit_redis = table.search(query_redis).limit(1).to_list()[0]
    assert hit_redis["claim_id"].endswith(":c2")
    assert "Redis is not used" in hit_redis["content"]


def test_index_claims_upsert_replaces_rows_for_record(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / "decision.md"
    config = EmbeddingConfig(provider="test", model="fake")

    index_claims(record, paths, config=config)
    record.claims[0].content = "PostgreSQL holds all session state"
    index_claims(record, paths, config=config)

    table = get_claims_table(paths)
    assert table.count_rows() == 2
    row = table.search(np.array([1.0] + [0.0] * (EMBEDDING_DIM - 1), dtype=np.float32)).limit(1).to_list()[0]
    assert row["content"] == "PostgreSQL holds all session state"


def test_index_claims_empty_claims_clears_table_rows(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / "decision.md"
    config = EmbeddingConfig(provider="test", model="fake")

    index_claims(record, paths, config=config)
    record.claims = []
    assert index_claims(record, paths, config=config) == []
    assert get_claims_table(paths).count_rows() == 0
