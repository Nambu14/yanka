"""JSON contract for LLM record extraction."""

from __future__ import annotations

import copy
from datetime import date
from typing import Any

from yanka.records.models import Record, RecordBody, RecordStatus, RecordType

BODY_FIELDS = (
    "rationale",
    "alternatives",
    "scope",
    "implications",
    "open_questions",
    "ownership",
    "context_snapshot",
    "raw_input",
)


def _body_schema(*, strict: bool) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            field: {"type": ["string", "null"]} for field in BODY_FIELDS
        },
    }
    if strict:
        body["required"] = list(BODY_FIELDS)
    return body


RECORD_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "date",
        "type",
        "status",
        "record_complete",
        "context_path",
        "decision",
    ],
    "properties": {
        "date": {"type": "string", "format": "date"},
        "type": {
            "type": "string",
            "enum": [item.value for item in RecordType],
        },
        "status": {
            "type": "string",
            "enum": [RecordStatus.ACTIVE.value, RecordStatus.TENTATIVE.value],
        },
        "record_complete": {"type": "boolean", "const": True},
        "context_path": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "people": {
            "type": "array",
            "items": {"type": "string"},
        },
        "supersedes": {"type": ["string", "null"]},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
        },
        "decision": {"type": "string", "minLength": 1},
        "body": _body_schema(strict=False),
    },
}


def record_json_schema(*, strict: bool = False) -> dict[str, Any]:
    """Return the record schema, optionally shaped for provider strict JSON mode.

    OpenAI strict structured output requires every nested property to appear
    in that object's ``required`` list. Application validation still treats
    missing or null body fields as omitted.
    """
    schema = copy.deepcopy(RECORD_JSON_SCHEMA)
    if not strict:
        return schema

    schema["required"] = [
        *schema["required"],
        "people",
        "tags",
        "supersedes",
    ]
    schema["properties"]["people"] = {
        "type": ["array", "null"],
        "items": {"type": "string"},
    }
    schema["properties"]["tags"] = {
        "type": ["array", "null"],
        "items": {"type": "string"},
    }
    schema["properties"]["body"] = _body_schema(strict=True)
    return schema


class RecordJsonError(ValueError):
    """Record extraction JSON failed schema validation."""


def record_from_json(payload: Any) -> Record:
    """Build a Record from validated-ish LLM JSON, with strict app checks."""
    if not isinstance(payload, dict):
        raise RecordJsonError("record JSON must be an object")

    _require_keys(payload, RECORD_JSON_SCHEMA["required"])
    _reject_unknown_keys(payload, _allowed_top_level_keys())
    if payload.get("record_complete") is not True:
        raise RecordJsonError("record_complete must be true")

    return Record(
        date=_parse_date(payload["date"]),
        type=_parse_record_type(payload["type"]),
        status=_parse_record_status(payload["status"]),
        context_path=_parse_required_string_list(
            payload["context_path"],
            "context_path",
        ),
        decision=_require_str(payload["decision"], "decision"),
        people=_parse_optional_string_list(payload.get("people"), "people"),
        tags=_parse_optional_string_list(payload.get("tags"), "tags"),
        supersedes=_parse_optional_str(payload.get("supersedes")),
        record_complete=True,
        body=_parse_body(payload.get("body")),
    )


def _require_keys(payload: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise RecordJsonError(f"missing required record keys: {', '.join(missing)}")


def _allowed_top_level_keys() -> set[str]:
    return set(RECORD_JSON_SCHEMA["properties"])


def _reject_unknown_keys(payload: dict[str, Any], properties: dict[str, Any]) -> None:
    unknown = sorted(set(payload) - set(properties))
    if unknown:
        raise RecordJsonError(f"unknown record keys: {', '.join(unknown)}")


def _parse_date(value: Any) -> date:
    if not isinstance(value, str):
        raise RecordJsonError("date must be a YYYY-MM-DD string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RecordJsonError("date must be a valid YYYY-MM-DD value") from exc


def _parse_record_type(value: Any) -> RecordType:
    try:
        return RecordType(str(value))
    except ValueError as exc:
        raise RecordJsonError(f"invalid record type: {value!r}") from exc


def _parse_record_status(value: Any) -> RecordStatus:
    try:
        status = RecordStatus(str(value))
    except ValueError as exc:
        raise RecordJsonError(f"invalid record status: {value!r}") from exc
    if status is RecordStatus.SUPERSEDED:
        raise RecordJsonError("extracted records cannot be superseded")
    return status


def _parse_required_string_list(value: Any, field_name: str) -> list[str]:
    parsed = _parse_optional_string_list(value, field_name)
    if not parsed:
        raise RecordJsonError(f"{field_name} must contain at least one string")
    return parsed


def _parse_optional_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RecordJsonError(f"{field_name} must be a list of strings")

    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise RecordJsonError(f"{field_name} must be a list of strings")
        stripped = item.strip()
        if not stripped or stripped == "[not discussed]":
            continue
        result.append(stripped)
    return result


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecordJsonError(f"{field_name} must be a non-empty string")
    return value.strip()


def _parse_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RecordJsonError("supersedes must be a string or null")
    stripped = value.strip()
    return stripped or None


def _parse_body(value: Any) -> RecordBody:
    if value is None:
        return RecordBody()
    if not isinstance(value, dict):
        raise RecordJsonError("body must be an object")

    unknown = sorted(set(value) - set(BODY_FIELDS))
    if unknown:
        raise RecordJsonError(f"unknown body fields: {', '.join(unknown)}")

    kwargs: dict[str, str | None] = {}
    for field in BODY_FIELDS:
        kwargs[field] = _optional_body_text(value.get(field), field)
    return RecordBody(**kwargs)


def _optional_body_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RecordJsonError(f"body.{field_name} must be a string or null")
    stripped = value.strip()
    if not stripped or stripped == "[not discussed]":
        return None
    return stripped
