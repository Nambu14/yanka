"""Persist and restore interrupted /log sessions for `/resume`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from yanka.ingest.pipeline_stages import PipelineStage
from yanka.ingest.record_snapshot import record_from_snapshot, record_to_snapshot
from yanka.paths import DataPaths
from yanka.records.json_schema import RecordJsonError
from yanka.records.models import Record

_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class PendingLogSession:
    raw_dump: str
    messages: list[dict[str, str]]
    created_at: str
    stage: PipelineStage
    record: Record | None = None


def save_pending_log_session(
    paths: DataPaths,
    *,
    raw_dump: str,
    messages: list[dict[str, str]] | None = None,
    stage: PipelineStage = PipelineStage.EXTRACTION,
    record: Record | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "raw_dump": raw_dump,
        "messages": messages if messages is not None else [],
        "stage": stage.value,
    }
    if record is not None:
        payload["record"] = record_to_snapshot(record)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.pending_log_session_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def has_pending_log_session(paths: DataPaths) -> bool:
    return paths.pending_log_session_path.is_file()


def clear_pending_log_session(paths: DataPaths) -> None:
    paths.pending_log_session_path.unlink(missing_ok=True)


def load_pending_log_session(paths: DataPaths) -> PendingLogSession:
    payload = json.loads(paths.pending_log_session_path.read_text(encoding="utf-8"))
    return _parse_pending(payload)


def _parse_pending(payload: Any) -> PendingLogSession:
    if not isinstance(payload, dict):
        raise ValueError("pending log session must be a JSON object")
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError("unsupported pending log session schema_version")

    raw_dump = payload.get("raw_dump")
    created_at = payload.get("created_at")
    messages = payload.get("messages", [])
    if not isinstance(raw_dump, str) or not raw_dump.strip():
        raise ValueError("pending log session missing raw_dump")
    if not isinstance(created_at, str) or not created_at.strip():
        raise ValueError("pending log session missing created_at")
    if not isinstance(messages, list):
        raise ValueError("pending log session messages must be a list")

    parsed_messages: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            raise ValueError("pending log session message must be an object")
        role = item.get("role")
        content = item.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            raise ValueError("pending log session message must have role/content")
        parsed_messages.append({"role": role, "content": content})

    stage = _parse_stage(payload.get("stage"))

    record: Record | None = None
    record_payload = payload.get("record")
    if record_payload is not None:
        try:
            record = record_from_snapshot(record_payload)
        except (ValueError, RecordJsonError) as exc:
            msg = f"pending log session record snapshot invalid: {exc}"
            raise ValueError(msg) from exc

    return PendingLogSession(
        raw_dump=raw_dump,
        messages=parsed_messages,
        created_at=created_at,
        stage=stage,
        record=record,
    )


def _parse_stage(value: Any) -> PipelineStage:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("pending log session missing stage")
    try:
        return PipelineStage(value)
    except ValueError as exc:
        msg = f"invalid pending log session stage: {value!r}"
        raise ValueError(msg) from exc
