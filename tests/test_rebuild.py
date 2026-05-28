from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from yanka.config import EmbeddingConfig
from yanka.embeddings import EMBEDDING_DIM, register_embedding_backend
from yanka.graph import get_graph_db, init_graph_schema
from yanka.graph.store import clear_graph_db_cache
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.rebuild import rebuild_indexes, reset_indexes
from yanka.records.io import write_record
from yanka.records.models import RecordStatus
from yanka.vectors.records import get_records_table
from yanka.vectors.search import search_records
from yanka.vectors.store import clear_vector_db_cache

pytest.importorskip("lancedb")
pytest.importorskip("ladybug")

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "with-claims.md"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "records"


def _rebuild_embed(
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
def _clear_store_caches() -> None:
    clear_graph_db_cache()
    clear_vector_db_cache()
    yield
    clear_graph_db_cache()
    clear_vector_db_cache()


@pytest.fixture(autouse=True)
def _test_embed_backend() -> None:
    register_embedding_backend("test", _rebuild_embed)
    yield


def _seed_records(paths) -> None:
    from yanka.records.io import read_record

    for fixture_name in ("with-claims.md", "valid-decision.md"):
        record = read_record(FIXTURES_DIR / fixture_name).record
        write_record(paths, record, filename=fixture_name)


def test_reset_indexes_wipes_and_recreates_graph_and_vectors(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    paths.graph_dir.mkdir(parents=True, exist_ok=True)
    paths.vectors_dir.mkdir(parents=True, exist_ok=True)
    (paths.graph_dir / "stale.txt").write_text("stale", encoding="utf-8")
    (paths.vectors_dir / "stale.txt").write_text("stale", encoding="utf-8")

    reset_indexes(paths)

    assert paths.graph_dir.is_dir()
    assert paths.vectors_dir.is_dir()
    assert not (paths.graph_dir / "stale.txt").exists()
    assert not (paths.vectors_dir / "stale.txt").exists()


def test_rebuild_indexes_populates_graph_and_vectors(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_records(paths)
    config = EmbeddingConfig(provider="test", model="fake")

    count = rebuild_indexes(paths, config=config)

    assert count == 2
    graph = get_graph_db(paths)
    init_graph_schema(graph)
    assert graph.connection.execute("MATCH (d:Decision) RETURN count(*)").get_all() == [[2]]
    assert get_records_table(paths).count_rows() == 2


def test_rebuild_indexes_search_works_post_rebuild(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_records(paths)
    config = EmbeddingConfig(provider="test", model="fake")
    rebuild_indexes(paths, config=config)

    hits = search_records(
        "session storage",
        paths,
        limit=5,
        config=config,
    )

    matching = [hit for hit in hits if hit["file_reference"].endswith("with-claims.md")]
    assert len(matching) == 1
    assert matching[0]["status"] == RecordStatus.ACTIVE.value


def test_rebuild_indexes_recovers_from_corrupt_vectors(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_records(paths)
    config = EmbeddingConfig(provider="test", model="fake")
    rebuild_indexes(paths, config=config)

    shutil.rmtree(paths.vectors_dir)

    rebuild_indexes(paths, config=config)

    hits = search_records(
        "session storage",
        paths,
        limit=5,
        config=config,
    )
    assert any(hit["file_reference"].endswith("with-claims.md") for hit in hits)
