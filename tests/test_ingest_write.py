from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from whyline.config import EmbeddingConfig
from whyline.embeddings import EMBEDDING_DIM, EmbeddingError, register_embedding_backend
from whyline.graph.store import clear_graph_db_cache
from whyline.ingest.write import write_ingested_record
from whyline.paths import ensure_data_layout, resolve_data_paths
from whyline.records.changelog import iter_changelog
from whyline.records.io import read_record
from whyline.vectors.records import get_records_table
from whyline.vectors.store import clear_vector_db_cache

pytest.importorskip("lancedb")
pytest.importorskip("ladybug")

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "with-claims.md"
EMBED_CONFIG = EmbeddingConfig(provider="test", model="fake")


@pytest.fixture(autouse=True)
def _clear_store_caches() -> None:
    clear_graph_db_cache()
    clear_vector_db_cache()
    yield
    clear_graph_db_cache()
    clear_vector_db_cache()


@pytest.fixture(autouse=True)
def _unit_embed_backend() -> None:
    def _embed(texts: list[str], _config) -> list[list[float]]:
        return [[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts]

    register_embedding_backend("test", _embed)
    yield


def test_write_ingested_record_indexes_graph_and_vectors(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record = read_record(FIXTURE).record

    result = write_ingested_record(
        paths,
        record,
        filename="with-claims.md",
        embedding_config=EMBED_CONFIG,
    )

    assert result.path.exists()
    assert result.graph_ok is True
    assert result.vectors_ok is True
    assert result.index_errors == []
    assert result.file_reference == "records/with-claims.md"

    table = get_records_table(paths)
    rows = table.search().limit(10).to_list()
    assert any(row["file_reference"] == result.file_reference for row in rows)


def test_write_ingested_record_leaves_file_when_vectors_fail(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record = read_record(FIXTURE).record

    with patch(
        "whyline.ingest.write.index_record",
        side_effect=EmbeddingError("embed failed"),
    ):
        result = write_ingested_record(
            paths,
            record,
            filename="ingest-vector-fail.md",
            embedding_config=EMBED_CONFIG,
        )

    assert result.path.is_file()
    assert result.graph_ok is True
    assert result.vectors_ok is False
    assert len(result.index_errors) == 1
    assert "[vectors]" in result.index_errors[0]


def test_write_ingested_record_leaves_file_when_graph_fails(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record = read_record(FIXTURE).record

    with patch(
        "whyline.ingest.write.index_record_graph",
        side_effect=RuntimeError("graph down"),
    ):
        result = write_ingested_record(
            paths,
            record,
            filename="ingest-graph-fail.md",
            embedding_config=EMBED_CONFIG,
        )

    assert result.path.is_file()
    assert result.graph_ok is False
    assert result.vectors_ok is True
    assert "[graph]" in result.index_errors[0]


def test_write_ingested_record_supersede_changelog(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    record = read_record(FIXTURE).record

    write_ingested_record(
        paths,
        record,
        filename="with-claims.md",
        embedding_config=EMBED_CONFIG,
    )

    entries = list(iter_changelog(paths))
    assert len(entries) == 1
    assert entries[0].action == "supersede"
    assert entries[0].supersedes_claims is not None
    old_ref = entries[0].supersedes_claims[0]["old"]
    assert old_ref == "2026-02-10-redis-session-store.md:c1"

    raw = paths.changelog_path.read_text(encoding="utf-8").splitlines()[0]
    line = json.loads(raw)
    assert line["action"] == "supersede"
    assert line["supersedes_claims"][0]["new"] == "c2"
