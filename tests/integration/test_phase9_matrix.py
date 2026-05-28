from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from yanka.config import EmbeddingConfig
from yanka.embeddings import EMBEDDING_DIM, register_embedding_backend
from yanka.graph import get_graph_db, init_graph_schema, upsert_context_path
from yanka.graph.store import clear_graph_db_cache
from yanka.ingest.conflict_candidates import ConflictCandidate
from yanka.ingest.extraction import RecordExtractionError
from yanka.ingest.pipeline import run_ingest_pipeline
from yanka.ingest.resume_state import has_pending_log_session
from yanka.ingest.write import write_ingested_record
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.rebuild import rebuild_indexes
from yanka.records import iter_changelog, read_record
from yanka.records.io import write_record
from yanka.records.models import (
    Claim,
    ClaimStatus,
    Record,
    RecordBody,
    RecordStatus,
    RecordType,
)
from yanka.repl.commands.log import run_log_command
from yanka.repl.commands.resume import run_resume_command
from yanka.retrieval import NO_RETRIEVED_RECORDS_ANSWER, STALE_INDEX_WARNING
from yanka.retrieval.pipeline import run_retrieval_pipeline
from yanka.retrieval_enums import RetrievalSource
from yanka.vectors.indexing import index_claims, index_record
from yanka.vectors.search import search_records
from yanka.vectors.store import clear_vector_db_cache

pytest.importorskip("ladybug")
pytest.importorskip("lancedb")

FIXTURES = Path(__file__).parents[1] / "fixtures" / "records"
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
            "raw_input": "integration raw input",
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
        "content": "Redis is not used for sessions",
        "status": "active",
    },
]


def _integration_embed(
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
        elif "15 minutes" in lower:
            vectors.append([0.0, 0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 3))
        elif "30 minutes" in lower:
            vectors.append([0.0, 0.0, 0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 4))
        else:
            vectors.append([0.0] * EMBEDDING_DIM)
    return vectors


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    clear_graph_db_cache()
    clear_vector_db_cache()
    register_embedding_backend("test", _integration_embed)
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
        return conflict_payload

    return fetch


def _seed_retrieval_record(paths) -> None:
    record = read_record(FIXTURES / "with-claims.md").record
    record_path = write_record(paths, record, filename="with-claims.md")
    record = read_record(record_path).record
    graph_db = get_graph_db(paths)
    init_graph_schema(graph_db)
    index_record(record, paths, config=EmbeddingConfig(provider="test", model="fake"))
    index_claims(record, paths, config=EmbeddingConfig(provider="test", model="fake"))
    from yanka.graph import index_record_graph

    index_record_graph(record, graph_db, paths)


def test_log_happy_path_writes_markdown_graph_vectors(paths, graph) -> None:
    result = run_ingest_pipeline(
        "Dropping Redis for sessions",
        paths,
        prompt_user=MagicMock(),
        send=lambda _messages, **_kwargs: COMPLETE_JSON,
        fetch_json=_mock_fetch(),
        graph=graph,
        filename="2026-05-14-integration-log.md",
        embedding_config=EmbeddingConfig(provider="test", model="fake"),
    )

    assert result.write_result.path.is_file()
    assert result.write_result.graph_ok is True
    assert result.write_result.vectors_ok is True


def test_conflict_supersession_creates_graph_edge(paths, graph) -> None:
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
        body=RecordBody(raw_input="old"),
    )
    write_ingested_record(
        paths,
        old,
        filename="2026-03-02-jwt-auth.md",
        graph=graph,
        embedding_config=EmbeddingConfig(provider="test", model="fake"),
    )
    conflicts = [
        {
            "new_claim_id": "c1",
            "existing_claim_id": "records/2026-03-02-jwt-auth.md:c2",
            "reason": "overlap",
        }
    ]
    conflict_claims = [{"id": "c1", "content": "Token lifetime is 30 minutes", "status": "active"}]
    candidate = ConflictCandidate(
        claim_id="records/2026-03-02-jwt-auth.md:c2",
        content="Token lifetime is 15 minutes",
        source_file="records/2026-03-02-jwt-auth.md",
        status="active",
        source=RetrievalSource.GRAPH,
    )

    with patch("yanka.ingest.pipeline.find_conflict_candidates", return_value=[candidate]):
        result = run_ingest_pipeline(
            "JWT tokens now last 30 minutes",
            paths,
            prompt_user=MagicMock(return_value="unused"),
            send=lambda _messages, **_kwargs: COMPLETE_JSON,
            fetch_json=_mock_fetch(conflicts=conflicts, claims=conflict_claims),
            prompt_confirm=lambda _view: True,
            graph=graph,
            filename="2026-05-14-jwt-update.md",
            embedding_config=EmbeddingConfig(provider="test", model="fake"),
        )

    assert len(result.confirmed_conflicts) == 1
    assert graph.connection.execute(
        "MATCH (:Claim {claim_id: 'records/2026-05-14-jwt-update.md:c1'})"
        "-[:supersedes]->"
        "(:Claim {claim_id: 'records/2026-03-02-jwt-auth.md:c2'}) RETURN count(*)"
    ).get_all() == [[1]]


def test_ask_happy_path_returns_answer_and_citations(paths) -> None:
    _seed_retrieval_record(paths)
    graph_db = get_graph_db(paths)

    result = run_retrieval_pipeline(
        "What's our current approach to session storage?",
        paths,
        graph=graph_db,
        embedding_config=EmbeddingConfig(provider="test", model="fake"),
        fetch_json=lambda _messages, **_kwargs: {
            "query_type": "current_state",
            "filters": {
                "project": "main-platform",
                "context_keywords": ["auth"],
                "status_filter": "active",
            },
            "semantic_query": "session storage",
            "graph_hint": "Find auth decisions",
        },
        fetch_text=lambda _messages, **_kwargs: "Sessions are stored in PostgreSQL (source: with-claims.md).",
    )

    assert "PostgreSQL" in result.answer
    assert result.answer_view.citations == ["with-claims.md"]


def test_stale_vector_index_skips_missing_file_and_warns(paths) -> None:
    _seed_retrieval_record(paths)
    (paths.records_dir / "with-claims.md").unlink()
    graph_db = get_graph_db(paths)

    result = run_retrieval_pipeline(
        "What's our current approach to session storage?",
        paths,
        graph=graph_db,
        embedding_config=EmbeddingConfig(provider="test", model="fake"),
        fetch_json=lambda _messages, **_kwargs: {
            "query_type": "current_state",
            "filters": {
                "project": "main-platform",
                "context_keywords": ["auth"],
                "status_filter": "active",
            },
            "semantic_query": "session storage",
            "graph_hint": "Find auth decisions",
        },
        fetch_text=lambda _messages, **_kwargs: "unused",
    )

    assert result.answer == NO_RETRIEVED_RECORDS_ANSWER
    assert result.warnings == [STALE_INDEX_WARNING]


def test_resume_after_extraction_error_keeps_pending(paths) -> None:
    output: list[str] = []

    def fail_runner(*_args, **_kwargs):
        raise RecordExtractionError(
            "record extraction did not produce a complete record after wrap-up",
            messages=[{"role": "assistant", "content": "Need more details"}],
        )

    run_log_command(
        paths,
        statement="This should fail extraction",
        output_fn=output.append,
        ingest_runner=fail_runner,
    )
    assert has_pending_log_session(paths)

    resumed = run_resume_command(
        paths,
        output_fn=output.append,
        ingest_runner=lambda _raw, _paths, **_kwargs: SimpleNamespace(
            write_result=SimpleNamespace(path=paths.records_dir / "resumed.md")
        ),
    )
    assert resumed is not None
    assert has_pending_log_session(paths) is False


def test_index_fail_after_write_keeps_file_and_warning(paths, graph) -> None:
    record = Record(
        date=date(2026, 5, 14),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=["main-platform", "auth-service"],
        decision="Drop Redis for session storage",
        claims=[
            Claim(
                id="c1",
                content="Session data is stored in PostgreSQL",
                status=ClaimStatus.ACTIVE,
            )
        ],
        record_complete=True,
        body=RecordBody(raw_input="integration"),
    )

    with patch("yanka.ingest.write.index_record", side_effect=RuntimeError("vector fail")):
        result = write_ingested_record(
            paths,
            record,
            filename="2026-05-14-index-fail.md",
            graph=graph,
            embedding_config=EmbeddingConfig(provider="test", model="fake"),
        )

    assert result.path.is_file()
    assert any("[vectors]" in error for error in result.index_errors)


def test_rebuild_recovers_search(paths) -> None:
    _seed_retrieval_record(paths)
    config = EmbeddingConfig(provider="test", model="fake")
    rebuild_indexes(paths, config=config)
    shutil.rmtree(paths.vectors_dir)
    rebuild_indexes(paths, config=config)

    hits = search_records("session storage", paths, limit=5, config=config)
    assert any(hit["file_reference"].endswith("with-claims.md") for hit in hits)
    entries = list(iter_changelog(paths))
    assert len(entries) >= 1
