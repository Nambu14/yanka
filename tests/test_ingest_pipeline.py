from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yanka.config import EmbeddingConfig
from yanka.embeddings import EMBEDDING_DIM, register_embedding_backend
from yanka.graph import (
    get_graph_db,
    index_record_graph,
    init_graph_schema,
    upsert_context_path,
)
from yanka.graph.store import clear_graph_db_cache
from yanka.ingest.conflict_candidates import ConflictCandidate
from yanka.ingest.pipeline import (
    IngestDuplicateRecordError,
    run_ingest_pipeline,
)
from yanka.ingest.pipeline_stages import (
    CONFLICT_EVALUATION_DEGRADE_WARNING,
    ENTITY_RESOLUTION_DEGRADE_WARNING,
    PipelineStage,
)
from yanka.llm.client import LlmTransportError
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.records import iter_changelog, read_record
from yanka.records.models import (
    Claim,
    ClaimStatus,
    Record,
    RecordBody,
    RecordStatus,
    RecordType,
)
from yanka.retrieval_enums import RetrievalSource
from yanka.ui.pipeline_activity import IngestActivityStage
from yanka.vectors.indexing import index_claims, index_record
from yanka.vectors.store import clear_vector_db_cache

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
        elif (
            "session data is stored in postgresql" in lower
            or ("postgresql" in lower and "session" in lower)
        ):
            vectors.append([0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2))
        elif "redis is not used" in lower:
            vectors.append([0.0, 0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 3))
        elif "30 minutes" in lower:
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
    assert written.record.body.raw_input == "Dropping Redis for sessions"
    assert written.record.claims[0].content.startswith("Session data")

    entries = list(iter_changelog(paths))
    assert len(entries) == 1
    assert entries[0].action == "create"


def test_ingest_pipeline_calls_before_confirmation_when_showing_panel(
    paths, graph
) -> None:
    called = False
    embed_config = EmbeddingConfig(provider="test", model="fake")

    def mark_before_confirmation() -> None:
        nonlocal called
        called = True

    run_ingest_pipeline(
        "Dropping Redis for sessions",
        paths,
        prompt_user=MagicMock(),
        send=lambda _messages, **_kwargs: COMPLETE_JSON,
        fetch_json=_mock_fetch(),
        graph=graph,
        filename="2026-05-14-drop-redis.md",
        embedding_config=embed_config,
        show_confirmation=True,
        before_confirmation=mark_before_confirmation,
        confirmation_output=lambda _line: None,
    )

    assert called


def test_ingest_pipeline_on_stage_order(paths, graph) -> None:
    stages: list[str] = []
    embed_config = EmbeddingConfig(provider="test", model="fake")

    run_ingest_pipeline(
        "Dropping Redis for sessions",
        paths,
        prompt_user=MagicMock(),
        send=lambda _messages, **_kwargs: COMPLETE_JSON,
        fetch_json=_mock_fetch(),
        graph=graph,
        filename="2026-05-14-on-stage.md",
        embedding_config=embed_config,
        on_stage=stages.append,
    )

    assert stages == [
        IngestActivityStage.SEARCHING,
        IngestActivityStage.EXTRACTING,
        IngestActivityStage.VALIDATING,
        IngestActivityStage.DEDUPING,
        IngestActivityStage.CONFLICT_CHECK,
        IngestActivityStage.WRITING,
    ]


def test_ingest_pipeline_on_stage_resume_skips_extraction(paths, graph) -> None:
    stages: list[str] = []
    embed_config = EmbeddingConfig(provider="test", model="fake")
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
            ),
        ],
        record_complete=True,
        body=RecordBody(raw_input="resume note"),
    )

    run_ingest_pipeline(
        "resume note",
        paths,
        prompt_user=MagicMock(),
        send=lambda _messages, **_kwargs: COMPLETE_JSON,
        fetch_json=_mock_fetch(),
        graph=graph,
        filename="2026-05-14-on-stage-resume.md",
        embedding_config=embed_config,
        resume_stage=PipelineStage.ENTITY_RESOLUTION,
        resume_record=record,
        on_stage=stages.append,
    )

    assert stages == [
        IngestActivityStage.DEDUPING,
        IngestActivityStage.CONFLICT_CHECK,
        IngestActivityStage.WRITING,
    ]


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


def test_ingest_pipeline_entity_resolution_llm_error_still_writes(paths, graph) -> None:
    upsert_context_path(["main-platform"], graph)
    upsert_context_path(["other-platform"], graph)
    embed_config = EmbeddingConfig(provider="test", model="fake")
    acme_json = json.dumps(
        {
            **json.loads(COMPLETE_JSON),
            "context_path": ["acme-platform", "auth-service"],
        }
    )

    def failing_resolution(_messages):
        raise LlmTransportError("connection reset")

    result = run_ingest_pipeline(
        "Dropping Redis for sessions",
        paths,
        prompt_user=MagicMock(),
        send=lambda _messages, **_kwargs: acme_json,
        fetch_json=_mock_fetch(),
        fetch_resolution=failing_resolution,
        graph=graph,
        filename="2026-05-14-degraded-entity.md",
        embedding_config=embed_config,
    )

    assert result.write_result.path.is_file()
    assert ENTITY_RESOLUTION_DEGRADE_WARNING in result.warnings


def test_ingest_pipeline_conflict_evaluation_llm_error_still_writes(
    paths,
    graph,
) -> None:
    embed_config = EmbeddingConfig(provider="test", model="fake")
    candidate = ConflictCandidate(
        claim_id="records/old.md:c2",
        content="Token lifetime is 15 minutes",
        source_file="records/old.md",
        status="active",
        source=RetrievalSource.GRAPH,
    )

    def fetch(_messages, expect=None, **_kwargs):
        if expect == "array":
            return CLAIMS
        raise LlmTransportError("provider down")

    with patch(
        "yanka.ingest.pipeline.find_conflict_candidates",
        return_value=[candidate],
    ):
        result = run_ingest_pipeline(
            "Dropping Redis for sessions",
            paths,
            prompt_user=MagicMock(),
            send=lambda _messages, **_kwargs: COMPLETE_JSON,
            fetch_json=fetch,
            graph=graph,
            filename="2026-05-14-degraded-conflict.md",
            embedding_config=embed_config,
        )

    assert result.write_result.path.is_file()
    assert result.confirmed_conflicts == []
    assert CONFLICT_EVALUATION_DEGRADE_WARNING in result.warnings


def _pre_index_existing_record(
    paths,
    graph,
    *,
    claim_contents: list[str],
    filename: str = "2026-04-01-existing.md",
) -> Record:
    existing = Record(
        date=date(2026, 4, 1),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=["main-platform", "auth-service"],
        decision="Existing decision",
        claims=[
            Claim(id=f"c{idx + 1}", content=content, status=ClaimStatus.ACTIVE)
            for idx, content in enumerate(claim_contents)
        ],
        record_complete=True,
        source_path=paths.records_dir / filename,
    )
    paths.records_dir.mkdir(parents=True, exist_ok=True)
    upsert_context_path(["main-platform", "auth-service"], graph)
    index_record_graph(existing, graph, paths)
    embed_config = EmbeddingConfig(provider="test", model="fake")
    index_record(existing, paths, config=embed_config)
    index_claims(existing, paths, config=embed_config)
    return existing


def test_ingest_pipeline_drops_duplicate_claim_and_renumbers(paths, graph) -> None:
    _pre_index_existing_record(
        paths,
        graph,
        claim_contents=["Session data is stored in PostgreSQL"],
    )
    embed_config = EmbeddingConfig(provider="test", model="fake")

    result = run_ingest_pipeline(
        "Dropping Redis for sessions",
        paths,
        prompt_user=MagicMock(),
        send=lambda _messages, **_kwargs: COMPLETE_JSON,
        fetch_json=_mock_fetch(),
        graph=graph,
        filename="2026-05-14-drop-redis-dedupe.md",
        embedding_config=embed_config,
    )

    assert result.write_result.path.is_file()
    assert len(result.record.claims) == 1
    assert [c.id for c in result.record.claims] == ["c1"]
    assert result.record.claims[0].content == "Redis is not used for session storage"
    assert len(result.duplicate_claims) == 1
    assert result.duplicate_claims[0].new_content == "Session data is stored in PostgreSQL"
    assert result.duplicate_claims[0].existing_file == "records/2026-04-01-existing.md"


def test_ingest_pipeline_raises_when_every_claim_is_duplicate(paths, graph) -> None:
    _pre_index_existing_record(
        paths,
        graph,
        claim_contents=[
            "Session data is stored in PostgreSQL",
            "Redis is not used for session storage",
        ],
    )
    embed_config = EmbeddingConfig(provider="test", model="fake")

    with pytest.raises(IngestDuplicateRecordError) as excinfo:
        run_ingest_pipeline(
            "Dropping Redis for sessions",
            paths,
            prompt_user=MagicMock(),
            send=lambda _messages, **_kwargs: COMPLETE_JSON,
            fetch_json=_mock_fetch(),
            graph=graph,
            filename="2026-05-14-drop-redis-all-dupe.md",
            embedding_config=embed_config,
        )

    assert len(excinfo.value.duplicate_claims) == 2
    assert excinfo.value.existing_files == ["records/2026-04-01-existing.md"]
    assert not (paths.records_dir / "2026-05-14-drop-redis-all-dupe.md").exists()
    assert list(iter_changelog(paths)) == []


def test_ingest_pipeline_resumes_from_entity_stage(paths, graph) -> None:
    embed_config = EmbeddingConfig(provider="test", model="fake")
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
            ),
        ],
        record_complete=True,
        body=RecordBody(raw_input="resume note"),
    )

    result = run_ingest_pipeline(
        "resume note",
        paths,
        prompt_user=MagicMock(),
        send=lambda _messages, **_kwargs: COMPLETE_JSON,
        fetch_json=_mock_fetch(),
        graph=graph,
        filename="2026-05-14-resume-entity.md",
        embedding_config=embed_config,
        resume_stage=PipelineStage.ENTITY_RESOLUTION,
        resume_record=record,
    )

    assert result.write_result.path.is_file()
    assert len(result.record.claims) == 1
