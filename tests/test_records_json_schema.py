from __future__ import annotations

from yanka.records.json_schema import (
    BODY_FIELDS,
    RecordJsonError,
    record_from_json,
    record_json_schema,
)

VALID_RECORD_JSON = {
    "date": "2026-05-26",
    "type": "problem-statement",
    "status": "tentative",
    "record_complete": True,
    "context_path": ["data-quality", "sampling"],
    "people": ["Rudy", "[not discussed]"],
    "tags": ["sampling-rate"],
    "decision": "Standardize customer sampling-rate handling.",
    "body": {
        "rationale": "100Hz is hardcoded in several paths.",
        "ownership": "[not discussed]",
    },
}


def test_strict_record_json_schema_lists_all_body_fields_as_required() -> None:
    schema = record_json_schema(strict=True)
    body = schema["properties"]["body"]

    assert set(body["required"]) == set(BODY_FIELDS)


def test_record_from_json_builds_record() -> None:
    record = record_from_json(VALID_RECORD_JSON)

    assert record.date.isoformat() == "2026-05-26"
    assert record.type.value == "problem-statement"
    assert record.status.value == "tentative"
    assert record.context_path == ["data-quality", "sampling"]
    assert record.people == ["Rudy"]
    assert record.body.rationale == "100Hz is hardcoded in several paths."
    assert record.body.ownership is None


def test_record_from_json_rejects_invalid_enum() -> None:
    payload = {**VALID_RECORD_JSON, "type": "not-real"}

    try:
        record_from_json(payload)
    except RecordJsonError as exc:
        assert "invalid record type" in str(exc)
    else:
        raise AssertionError("expected RecordJsonError")


def test_record_from_json_requires_context_path() -> None:
    payload = {**VALID_RECORD_JSON}
    payload.pop("context_path")

    try:
        record_from_json(payload)
    except RecordJsonError as exc:
        assert "missing required record keys" in str(exc)
    else:
        raise AssertionError("expected RecordJsonError")


def test_record_from_json_rejects_superseded_status() -> None:
    payload = {**VALID_RECORD_JSON, "status": "superseded"}

    try:
        record_from_json(payload)
    except RecordJsonError as exc:
        assert "superseded" in str(exc)
    else:
        raise AssertionError("expected RecordJsonError")
