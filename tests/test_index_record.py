from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from yanka.config import EmbeddingConfig
from yanka.embeddings import EMBEDDING_DIM, register_embedding_backend
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.records.io import read_record
from yanka.vectors.indexing import index_record
from yanka.vectors.records import get_records_table
from yanka.vectors.store import clear_vector_db_cache

pytest.importorskip("lancedb")

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "with-claims.md"


def _redis_aware_embed(
    texts: list[str],
    _config: EmbeddingConfig,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        if "redis" in text.lower():
            vectors.append([1.0] + [0.0] * (EMBEDDING_DIM - 1))
        else:
            vectors.append([0.0] * EMBEDDING_DIM)
    return vectors


def _marker_embed(texts: list[str], _config: EmbeddingConfig) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        vector = [0.0] * EMBEDDING_DIM
        lower = text.lower()
        if "zzz_unique_marker" in lower:
            vector[2] = 1.0
        elif "drop redis" in lower:
            vector[0] = 1.0
        vectors.append(vector)
    return vectors


@pytest.fixture(autouse=True)
def _setup_embed_backend() -> None:
    clear_vector_db_cache()
    register_embedding_backend("test", _redis_aware_embed)
    yield
    clear_vector_db_cache()


def test_index_record_semantic_hit(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record_file = read_record(FIXTURE)
    record = record_file.record
    record.source_path = paths.records_dir / "2026-05-14-redis-session.md"

    config = EmbeddingConfig(provider="test", model="fake")
    file_ref = index_record(record, paths, config=config)

    assert file_ref == "records/2026-05-14-redis-session.md"
    table = get_records_table(paths)
    assert table.count_rows() == 1

    query = np.array([1.0] + [0.0] * (EMBEDDING_DIM - 1), dtype=np.float32)
    hit = table.search(query).limit(1).to_list()[0]
    assert hit["file_reference"] == file_ref
    assert hit["summary"] == record.decision
    assert hit["project"] == "main-platform"
    assert hit["status"] == "active"


def test_index_record_upsert_replaces_row(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record_file = read_record(FIXTURE)
    record = record_file.record
    record.source_path = paths.records_dir / "decision.md"
    config = EmbeddingConfig(provider="test", model="fake")

    index_record(record, paths, config=config)
    record.decision = "Updated decision summary"
    index_record(record, paths, config=config)

    table = get_records_table(paths)
    assert table.count_rows() == 1
    row = table.search(np.zeros(EMBEDDING_DIM, dtype=np.float32)).limit(1).to_list()[0]
    assert row["summary"] == "Updated decision summary"


def test_index_record_reindex_uses_current_record_fields(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record_file = read_record(FIXTURE)
    record = record_file.record
    record.source_path = paths.records_dir / "decision.md"
    register_embedding_backend("marker", _marker_embed)
    config = EmbeddingConfig(provider="marker", model="fake")

    index_record(record, paths, config=config)
    record.decision = "ZZZ_UNIQUE_MARKER"
    index_record(record, paths, config=config)

    query = np.array(
        [0.0, 0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 3),
        dtype=np.float32,
    )
    row = (
        get_records_table(paths)
        .search(query)
        .limit(1)
        .to_list()[0]
    )
    assert row["summary"] == "ZZZ_UNIQUE_MARKER"
    assert row["vector"][2] == 1.0
