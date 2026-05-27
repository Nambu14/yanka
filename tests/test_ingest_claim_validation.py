from __future__ import annotations

from datetime import date

from yanka.ingest.claim_validation import (
    AMBER_COVERAGE_WARNING,
    ClaimValidationIssue,
    extract_claims_validated,
    validate_claims,
)
from yanka.ingest.claims import ClaimExtractionError
from yanka.llm.json_parse import JsonParseError
from yanka.records.models import (
    Claim,
    ClaimStatus,
    Record,
    RecordBody,
    RecordStatus,
    RecordType,
)

GOOD_CLAIMS_JSON = [
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

WEAK_CLAIMS_JSON = [
    {
        "id": "c1",
        "content": "The team met on Tuesday",
        "status": "active",
    },
]


def _record() -> Record:
    return Record(
        date=date(2026, 5, 14),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=["main-platform", "auth-service"],
        decision="Drop Redis for session storage",
        body=RecordBody(rationale="PostgreSQL only."),
        record_complete=True,
    )


def test_validate_claims_passes_when_decision_covered() -> None:
    claims = [
        Claim(
            id="c1",
            content="Redis is not used for sessions",
            status=ClaimStatus.ACTIVE,
        ),
    ]
    assert validate_claims(_record(), claims) == []


def test_validate_claims_flags_empty() -> None:
    assert validate_claims(_record(), []) == [ClaimValidationIssue.EMPTY]


def test_validate_claims_flags_coverage_gap() -> None:
    claims = [
        Claim(
            id="c1",
            content="Weekly sync moved to Thursday",
            status=ClaimStatus.ACTIVE,
        ),
    ]
    assert validate_claims(_record(), claims) == [ClaimValidationIssue.COVERAGE]


def test_extract_claims_validated_passes_without_retry() -> None:
    record = _record()
    calls = 0

    def fetch(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return GOOD_CLAIMS_JSON

    claims, warnings = extract_claims_validated(record, fetch_json=fetch)

    assert calls == 1
    assert len(claims) == 2
    assert warnings == []


def test_extract_claims_validated_retries_then_passes() -> None:
    record = _record()
    calls = 0

    def fetch(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return WEAK_CLAIMS_JSON
        return GOOD_CLAIMS_JSON

    claims, warnings = extract_claims_validated(record, fetch_json=fetch)

    assert calls == 2
    assert len(claims) == 2
    assert claims[1].content.startswith("Redis")
    assert warnings == []


def test_extract_claims_validated_amber_when_retry_still_weak() -> None:
    record = _record()
    calls = 0

    def fetch(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return WEAK_CLAIMS_JSON

    claims, warnings = extract_claims_validated(record, fetch_json=fetch)

    assert calls == 2
    assert len(claims) == 1
    assert warnings == [AMBER_COVERAGE_WARNING]


def test_extract_claims_validated_amber_keeps_first_pass_on_retry_json_error() -> None:
    record = _record()
    calls = 0

    def fetch(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return WEAK_CLAIMS_JSON
        raise JsonParseError("bad")

    claims, warnings = extract_claims_validated(record, fetch_json=fetch)

    assert len(claims) == 1
    assert warnings == [AMBER_COVERAGE_WARNING]


def test_extract_claims_validated_empty_on_extraction_failure() -> None:
    record = _record()

    def failing_fetch(*_args, **_kwargs):
        raise ClaimExtractionError("failed")

    claims, warnings = extract_claims_validated(record, fetch_json=failing_fetch)

    assert claims == []
    assert warnings == [AMBER_COVERAGE_WARNING]
