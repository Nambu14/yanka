"""Serialize records for pending /log resume state (schema v2)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from yanka.records.json_schema import BODY_FIELDS, record_from_json
from yanka.records.markdown import record_to_frontmatter_dict
from yanka.records.models import Record, RecordBody, claims_from_json


def record_to_snapshot(record: Record) -> dict[str, Any]:
    """Build a JSON-serializable dict for ``pending_log_session.json``."""
    data = record_to_frontmatter_dict(record)
    data["date"] = record.date.isoformat()
    data["body"] = {field: getattr(record.body, field) for field in BODY_FIELDS}
    return data


def record_from_snapshot(payload: Any) -> Record:
    """Restore a Record from a pending-session snapshot dict."""
    if not isinstance(payload, dict):
        msg = "record snapshot must be a JSON object"
        raise ValueError(msg)

    snapshot = dict(payload)
    claims_raw = snapshot.pop("claims", None)
    body_raw = snapshot.pop("body", None)

    record = record_from_json(snapshot)
    if claims_raw is not None:
        record = replace(record, claims=claims_from_json(claims_raw))
    if body_raw is not None:
        record = replace(record, body=_body_from_snapshot(body_raw))
    return record


def _body_from_snapshot(body_raw: Any) -> RecordBody:
    if not isinstance(body_raw, dict):
        msg = "record snapshot body must be an object"
        raise ValueError(msg)
    kwargs: dict[str, str | None] = {}
    for field in BODY_FIELDS:
        value = body_raw.get(field)
        if value is None:
            kwargs[field] = None
        elif isinstance(value, str):
            kwargs[field] = value.strip() or None
        else:
            msg = f"body.{field} must be a string or null"
            raise ValueError(msg)
    return RecordBody(**kwargs)
