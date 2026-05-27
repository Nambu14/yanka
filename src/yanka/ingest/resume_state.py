"""Persist and restore interrupted /log sessions for `/resume`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from yanka.paths import DataPaths

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PendingLogSession:
    raw_dump: str
    messages: list[dict[str, str]]
    created_at: str


def save_pending_log_session(
    paths: DataPaths,
    *,
    raw_dump: str,
    messages: list[dict[str, str]],
) -> None:
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "raw_dump": raw_dump,
        "messages": messages,
    }
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
    return PendingLogSession(
        raw_dump=raw_dump,
        messages=parsed_messages,
        created_at=created_at,
    )
