from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from whyline.config import EmbeddingConfig
from whyline.embeddings import EMBEDDING_DIM, register_embedding_backend
from whyline.graph import (
    get_graph_db,
    index_record_graph,
    init_graph_schema,
    upsert_context_path,
)
from whyline.graph.store import clear_graph_db_cache
from whyline.ingest.pipeline import run_ingest_pipeline
from whyline.paths import ensure_data_layout, resolve_data_paths
from whyline.records import iter_changelog, read_record
from whyline.records.models import (
    Claim,
    ClaimStatus,
    Record,
    RecordStatus,
    RecordType,
)
from whyline.vectors.indexing import index_claims, index_record
from whyline.vectors.store import clear_vector_db_cache

pytest.importorskip("ladybug")
pytest.importorskip("lancedb")

FIXTURES = Path(__file__).parent / "fixtures" / "records"
COMPLETE = (FIXTURES / "valid-decision.md").read_text(encoding="utf-8")
COMPLETE_JSON = json.dumps(
    {
        "date": "2026-05-14",
        "type": "decision",
        "status": "active",
        "record_complete": True,
        "context_path": ["main-platform", "auth-service"],
        "people": ["Carlos"],
        "supersedes": None,
        "tags": ["infrastructure"],
        "decision": "Drop Redis for session storage",
        "body": {
            "rationale": "We chose PostgreSQL.",
            "raw_input": "user pasted --- here, not a fence",
        },
    }
)

CLAIMS = [
    {
        "id": "c1",
        "content": "Session data is stored in PostgreSQL",
        "status": "active",
    },
    {
        "id": "c2",
        "content": "Redis is not used for session storage",
        "status": "active",
    },
]

CONFLICT_CLAIMS = [
    {
        "id": "c1",
        "content": "Token lifetime is 30 minutes",
        "status": "active",
    },
]


def _pipeline_embed(
    texts: list[str],
    _config: EmbeddingConfig,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        lower = text.lower()
        if "15 minutes" in lower or "token lifetime is 15" in lower:
            vectors.append([1.0] + [0.0] * (EMBEDDING_DIM - 1))
        elif "30 minutes" in lower or "postgresql" in lower:
            vectors.append([0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2))
        else:
            vectors.append([0.0] * EMBEDDING_DIM)
    return vectors


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    clear_graph_db_cache()
    clear_vector_db_cache()
    register_embedding_backend("test", _pipeline_embed)
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


def _mock_fetch(*, conflicts: list[dict] | None = None, claims: list | None = None):
    conflict_payload = {"conflicts": conflicts or []}
    claims_payload = claims if claims is not None else CLAIMS

    def fetch(_messages, expect=None, **_kwargs):
        if expect == "array":
            return claims_payload
        if expect == "object":
            return conflict_payload
        return conflict_payload

    return fetch


def test_ingest_pipeline_happy_path(paths, graph) -> None:
    prompt_user = MagicMock()
    embed_config = EmbeddingConfig(provider="test", model="fake")

    result = run_ingest_pipeline(
        "Dropping Redis for sessions",
        paths,
        prompt_user=prompt_user,
        send=lambda _messages, **_kwargs: COMPLETE_JSON,
        fetch_json=_mock_fetch(),
        graph=graph,
        filename="2026-05-14-drop-redis.md",
        embedding_config=embed_config,
    )

    prompt_user.assert_not_called()
    assert result.write_result.path.is_file()
    assert result.write_result.graph_ok
    assert result.write_result.vectors_ok
    assert result.confirmed_conflicts == []
    assert len(result.record.claims) == 2

    written = read_record(result.write_result.path)
    assert written.record.decision == "Drop Redis for session storage"
    assert written.record.claims[0].content.startswith("Session data")

    entries = list(iter_changelog(paths))
    assert len(entries) == 1
    assert entries[0].action == "create"


def test_ingest_pipeline_with_confirmed_conflict(paths, graph) -> None:
    upsert_context_path(["main-platform", "auth-service"], graph)
    old = Record(
        date=date(2026, 3, 2),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=["main-platform", "auth-service"],
        decision="JWT token policy",
        claims=[
            Claim(
                id="c2",
                content="Token lifetime is 15 minutes",
                status=ClaimStatus.ACTIVE,
            )
        ],
        record_complete=True,
        source_path=paths.records_dir / "2026-03-02-jwt-auth.md",
    )
    paths.records_dir.mkdir(parents=True, exist_ok=True)
    index_record_graph(old, graph, paths)
    embed_config = EmbeddingConfig(provider="test", model="fake")
    index_record(old, paths, config=embed_config)
    index_claims(old, paths, config=embed_config)

    conflicts = [
        {
            "new_claim_id": "c1",
            "existing_claim_id": "records/2026-03-02-jwt-auth.md:c2",
            "reason": "Different token lifetimes",
        }
    ]
    prompts: list[str] = []

    def prompt_confirm(view) -> bool:
        prompts.append(view.old_content)
        return True

    result = run_ingest_pipeline(
        "JWT tokens now last 30 minutes",
        paths,
        prompt_user=MagicMock(return_value="unused"),
        send=lambda _messages, **_kwargs: COMPLETE_JSON,
        fetch_json=_mock_fetch(conflicts=conflicts, claims=CONFLICT_CLAIMS),
        prompt_confirm=prompt_confirm,
        graph=graph,
        filename="2026-05-14-jwt-update.md",
        embedding_config=embed_config,
    )

    assert len(result.confirmed_conflicts) == 1
    assert result.record.claims[0].supersedes is not None
    assert result.record.claims[0].supersedes.file == "2026-03-02-jwt-auth.md"
    assert result.record.claims[0].supersedes.claim == "c2"
    assert prompts == ["Token lifetime is 15 minutes"]

    written = read_record(result.write_result.path)
    assert "supersedes:" in written.raw_text
    assert "2026-03-02-jwt-auth.md" in written.raw_text

    entries = list(iter_changelog(paths))
    assert entries[-1].action == "supersede"
    assert entries[-1].supersedes_claims == [
        {"new": "c1", "old": "2026-03-02-jwt-auth.md:c2"},
    ]
