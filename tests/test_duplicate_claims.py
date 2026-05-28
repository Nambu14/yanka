from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from yanka.config import EmbeddingConfig
from yanka.embeddings import EMBEDDING_DIM, register_embedding_backend
from yanka.ingest.duplicate_claims import (
    DuplicateClaimMatch,
    drop_duplicate_claims,
    find_duplicate_claims,
)
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.records.io import read_record
from yanka.records.models import Claim, ClaimStatus
from yanka.vectors.indexing import index_claims, index_record
from yanka.vectors.store import clear_vector_db_cache

pytest.importorskip("lancedb")

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "with-claims.md"


def _dedupe_embed(
    texts: list[str],
    _config: EmbeddingConfig,
) -> list[list[float]]:
    """Hash claim content to a stable basis vector so identical text → distance 0."""
    vectors: list[list[float]] = []
    for text in texts:
        normalized = " ".join(text.lower().split())
        vector = [0.0] * EMBEDDING_DIM
        if normalized:
            digest = hashlib.md5(normalized.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
            vector[bucket] = 1.0
        vectors.append(vector)
    return vectors


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_vector_db_cache()
    register_embedding_backend("test", _dedupe_embed)
    yield
    clear_vector_db_cache()


@pytest.fixture
def paths(tmp_path: Path):
    return ensure_data_layout(resolve_data_paths(tmp_path))


def _index_fixture_record(paths) -> None:
    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / "with-claims.md"
    config = EmbeddingConfig(provider="test", model="fake")
    index_record(record, paths, config=config)
    index_claims(record, paths, config=config)


def test_identical_claim_is_detected_as_duplicate(paths) -> None:
    _index_fixture_record(paths)
    new_claims = [
        Claim(id="c1", content="Session data is stored in PostgreSQL", status=ClaimStatus.ACTIVE),
    ]

    matches = find_duplicate_claims(
        new_claims,
        ["main-platform", "auth-service"],
        paths,
        config=EmbeddingConfig(provider="test", model="fake"),
    )

    assert len(matches) == 1
    assert matches[0].new_claim_id == "c1"
    assert matches[0].existing_file == "records/with-claims.md"
    assert matches[0].distance == 0.0


def test_novel_claim_is_not_flagged(paths) -> None:
    _index_fixture_record(paths)
    new_claims = [
        Claim(
            id="c1",
            content="Frontend uses React with TypeScript",
            status=ClaimStatus.ACTIVE,
        ),
    ]

    matches = find_duplicate_claims(
        new_claims,
        ["main-platform", "auth-service"],
        paths,
        config=EmbeddingConfig(provider="test", model="fake"),
    )

    assert matches == []


def test_empty_index_returns_no_matches(paths) -> None:
    new_claims = [
        Claim(id="c1", content="Anything goes", status=ClaimStatus.ACTIVE),
    ]

    matches = find_duplicate_claims(
        new_claims,
        ["main-platform"],
        paths,
        config=EmbeddingConfig(provider="test", model="fake"),
    )

    assert matches == []


def test_cross_project_existing_claim_is_ignored(paths) -> None:
    _index_fixture_record(paths)
    new_claims = [
        Claim(id="c1", content="Session data is stored in PostgreSQL", status=ClaimStatus.ACTIVE),
    ]

    matches = find_duplicate_claims(
        new_claims,
        ["other-platform", "auth-service"],
        paths,
        config=EmbeddingConfig(provider="test", model="fake"),
    )

    assert matches == []


def test_distance_threshold_overrides_config(paths) -> None:
    _index_fixture_record(paths)
    new_claims = [
        Claim(id="c1", content="Session data is stored in PostgreSQL", status=ClaimStatus.ACTIVE),
    ]

    matches = find_duplicate_claims(
        new_claims,
        ["main-platform", "auth-service"],
        paths,
        config=EmbeddingConfig(provider="test", model="fake"),
        max_distance=-0.1,
    )

    assert matches == []


def test_drop_duplicate_claims_renumbers_survivors() -> None:
    claims = [
        Claim(id="c1", content="A", status=ClaimStatus.ACTIVE),
        Claim(id="c2", content="B", status=ClaimStatus.ACTIVE),
        Claim(id="c3", content="C", status=ClaimStatus.ACTIVE),
    ]
    matches = [
        DuplicateClaimMatch(
            new_claim_id="c2",
            new_content="B",
            existing_claim_id="records/old.md:c1",
            existing_content="B",
            existing_file="records/old.md",
            distance=0.0,
        ),
    ]

    survivors = drop_duplicate_claims(claims, matches)

    assert [(c.id, c.content) for c in survivors] == [("c1", "A"), ("c2", "C")]


def test_drop_duplicate_claims_empty_match_returns_input_ids() -> None:
    claims = [
        Claim(id="c1", content="A", status=ClaimStatus.ACTIVE),
        Claim(id="c2", content="B", status=ClaimStatus.ACTIVE),
    ]

    survivors = drop_duplicate_claims(claims, [])

    assert [c.id for c in survivors] == ["c1", "c2"]
