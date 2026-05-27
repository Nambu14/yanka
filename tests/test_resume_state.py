from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from yanka.ingest.pipeline_stages import PipelineStage
from yanka.ingest.resume_state import (
    clear_pending_log_session,
    load_pending_log_session,
    save_pending_log_session,
)
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.records.models import (
    Claim,
    ClaimStatus,
    Record,
    RecordBody,
    RecordStatus,
    RecordType,
)


def _sample_record() -> Record:
    return Record(
        date=date(2026, 5, 14),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=["main-platform", "auth-service"],
        decision="Use PostgreSQL for sessions",
        people=["Carlos"],
        tags=["infra"],
        claims=[
            Claim(
                id="c1",
                content="Sessions live in PostgreSQL",
                status=ClaimStatus.ACTIVE,
            )
        ],
        record_complete=True,
        body=RecordBody(rationale="Simpler ops", raw_input="note"),
    )


@pytest.fixture
def paths(tmp_path: Path):
    return ensure_data_layout(resolve_data_paths(tmp_path))


def test_pending_rejects_schema_version_one(paths) -> None:
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.pending_log_session_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "created_at": "2026-05-14T12:00:00+00:00",
                "raw_dump": "old pending",
                "messages": [{"role": "user", "content": "hi"}],
                "stage": "extraction",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema_version"):
        load_pending_log_session(paths)


def test_pending_requires_stage(paths) -> None:
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.pending_log_session_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "created_at": "2026-05-14T12:00:00+00:00",
                "raw_dump": "pending",
                "messages": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="stage"):
        load_pending_log_session(paths)


def test_pending_round_trips_record_and_stage(paths) -> None:
    record = _sample_record()
    save_pending_log_session(
        paths,
        raw_dump="brain dump",
        messages=[],
        stage=PipelineStage.ENTITY_RESOLUTION,
        record=record,
    )

    pending = load_pending_log_session(paths)

    assert pending.stage is PipelineStage.ENTITY_RESOLUTION
    assert pending.record is not None
    assert pending.record.decision == record.decision
    assert pending.record.claims[0].content == "Sessions live in PostgreSQL"
    assert pending.record.body.raw_input == "note"

    clear_pending_log_session(paths)
    assert not paths.pending_log_session_path.is_file()


def test_pending_extraction_stage(paths) -> None:
    save_pending_log_session(
        paths,
        raw_dump="note",
        messages=[{"role": "user", "content": "hi"}],
        stage=PipelineStage.EXTRACTION,
    )

    pending = load_pending_log_session(paths)

    assert pending.stage is PipelineStage.EXTRACTION
    assert pending.record is None
    assert pending.messages == [{"role": "user", "content": "hi"}]
