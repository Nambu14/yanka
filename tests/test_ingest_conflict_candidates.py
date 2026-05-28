from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from yanka.config import EmbeddingConfig
from yanka.embeddings import EMBEDDING_DIM, register_embedding_backend
from yanka.graph import (
    get_graph_db,
    index_record_graph,
    init_graph_schema,
)
from yanka.graph.store import clear_graph_db_cache
from yanka.ingest.conflict_candidates import (
    ConflictCandidate,
    find_conflict_candidates,
    merge_conflict_candidates,
    vector_conflict_candidates,
)
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.records.io import read_record
from yanka.records.models import (
    Claim,
    ClaimStatus,
    Record,
    RecordStatus,
    RecordType,
)
from yanka.vectors.indexing import index_claims, index_record
from yanka.vectors.store import clear_vector_db_cache

pytest.importorskip("ladybug")
pytest.importorskip("lancedb")

VECTOR_FIXTURE = Path(__file__).parent / "fixtures" / "records" / "with-claims.md"


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
def _clear_caches() -> None:
    clear_graph_db_cache()
    clear_vector_db_cache()
    register_embedding_backend("test", _search_embed)
    yield
    clear_graph_db_cache()
    clear_vector_db_cache()


@pytest.fixture
def paths(tmp_path: Path):
    return ensure_data_layout(resolve_data_paths(tmp_path))


@pytest.fixture
def graph(paths):
    graph_db = get_graph_db(paths)
    init_graph_schema(graph_db)
    return graph_db


def _indexed_vector_record(
    paths,
    filename: str = "2026-05-14-redis-session.md",
) -> Record:
    record = read_record(VECTOR_FIXTURE).record
    record.source_path = paths.records_dir / filename
    config = EmbeddingConfig(provider="test", model="fake")
    index_record(record, paths, config=config)
    index_claims(record, paths, config=config)
    return record


def _graph_record(
    paths,
    filename: str,
    *,
    context_path: list[str],
    claim_content: str,
) -> Record:
    return Record(
        date=date(2026, 5, 14),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=context_path,
        decision=f"Decision in {filename}",
        claims=[
            Claim(
                id="c1",
                content=claim_content,
                status=ClaimStatus.ACTIVE,
            )
        ],
        record_complete=True,
        source_path=paths.records_dir / filename,
    )


def test_find_conflict_candidates_empty_claims(graph, paths) -> None:
    assert find_conflict_candidates([], ["main-platform"], graph, paths) == []


def test_find_conflict_candidates_graph_only(graph, paths) -> None:
    index_record_graph(
        _graph_record(
            paths,
            "auth-a.md",
            context_path=["main-platform", "auth-service"],
            claim_content="JWT in cookies",
        ),
        graph,
        paths,
    )
    index_record_graph(
        _graph_record(
            paths,
            "auth-b.md",
            context_path=["main-platform", "auth-service"],
            claim_content="Sessions in PostgreSQL",
        ),
        graph,
        paths,
    )

    new_claims = [
        Claim(
            id="c1",
            content="Token lifetime is 30 minutes",
            status=ClaimStatus.ACTIVE,
        )
    ]
    candidates = find_conflict_candidates(
        new_claims,
        ["main-platform", "auth-service"],
        graph,
        paths,
        search_claims_fn=lambda *_a, **_k: [],
    )

    assert len(candidates) == 2
    assert all(c.source == "graph" for c in candidates)
    assert {c.claim_id for c in candidates} == {
        "records/auth-a.md:c1",
        "records/auth-b.md:c1",
    }


def test_find_conflict_candidates_vector_only(graph, paths) -> None:
    indexed = _indexed_vector_record(paths)
    new_claims = [Claim(id="c1", content="PostgreSQL session storage", status=ClaimStatus.ACTIVE)]

    candidates = find_conflict_candidates(
        new_claims,
        indexed.context_path,
        graph,
        paths,
        config=EmbeddingConfig(provider="test", model="fake"),
    )

    assert len(candidates) == 1
    assert candidates[0].source == "vector"
    assert candidates[0].claim_id.endswith(":c1")
    assert candidates[0].status == "active"


def test_merge_conflict_candidates_graph_wins_dedupe() -> None:
    graph_rows = [
        {
            "claim_id": "records/a.md:c1",
            "content": "From graph",
            "source_file": "records/a.md",
            "status": "active",
        }
    ]
    vector = [
        ConflictCandidate(
            claim_id="records/a.md:c1",
            content="From vector",
            source_file="records/a.md",
            status="active",
            source="vector",
            similarity=0.1,
        ),
        ConflictCandidate(
            claim_id="records/b.md:c1",
            content="Vector only",
            source_file="records/b.md",
            status="active",
            source="vector",
            similarity=0.5,
        ),
    ]

    merged = merge_conflict_candidates(graph_rows, vector, limit=10)

    assert len(merged) == 2
    assert merged[0].source == "graph"
    assert merged[0].content == "From graph"
    assert merged[1].claim_id == "records/b.md:c1"


def test_merge_conflict_candidates_respects_limit() -> None:
    graph_rows = [
        {
            "claim_id": f"records/r{i}.md:c1",
            "content": f"claim {i}",
            "source_file": f"records/r{i}.md",
            "status": "active",
        }
        for i in range(5)
    ]

    merged = merge_conflict_candidates(graph_rows, [], limit=2)

    assert len(merged) == 2
    assert merged[0].claim_id == "records/r0.md:c1"


def test_vector_conflict_candidates_excludes_tentative(paths) -> None:
    _indexed_vector_record(paths)
    config = EmbeddingConfig(provider="test", model="fake")

    candidates = vector_conflict_candidates(
        [Claim(id="c1", content="Redis is not used", status=ClaimStatus.ACTIVE)],
        ["main-platform", "auth-service"],
        paths,
        config=config,
    )

    assert len(candidates) == 1
    assert candidates[0].claim_id.endswith(":c1")
    assert all(c.status == "active" for c in candidates)


def test_find_conflict_candidates_respects_config_limit(
    graph,
    paths,
) -> None:
    for index in range(5):
        index_record_graph(
            _graph_record(
                paths,
                f"auth-{index}.md",
                context_path=["main-platform", "auth-service"],
                claim_content=f"Claim {index}",
            ),
            graph,
            paths,
        )

    paths.config_path.write_text("extraction:\n  conflict_search_limit: 2\n")

    candidates = find_conflict_candidates(
        [Claim(id="c1", content="anything", status=ClaimStatus.ACTIVE)],
        ["main-platform", "auth-service"],
        graph,
        paths,
        search_claims_fn=lambda *_a, **_k: [],
    )

    assert len(candidates) == 2
