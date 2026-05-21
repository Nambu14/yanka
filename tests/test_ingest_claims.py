from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from whyline.ingest.claims import (
    ClaimExtractionError,
    build_claim_extraction_messages,
    extract_claims,
)
from whyline.llm import PromptName, get_prompt
from whyline.llm.json_parse import JsonParseError
from whyline.records.io import read_record
from whyline.records.models import (
    ClaimStatus,
    Record,
    RecordBody,
    RecordStatus,
    RecordType,
    claims_from_json,
)

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "valid-decision.md"

MOCK_CLAIMS_JSON = [
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


def _record_without_claims() -> Record:
    return Record(
        date=date(2026, 5, 14),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=["main-platform", "auth-service"],
        decision="Drop Redis for session storage",
        body=RecordBody(rationale="PostgreSQL only."),
        record_complete=True,
    )


def test_claims_from_json_parses_valid_array() -> None:
    claims = claims_from_json(MOCK_CLAIMS_JSON)

    assert len(claims) == 2
    assert claims[0].id == "c1"
    assert claims[0].status is ClaimStatus.ACTIVE
    assert claims[1].content.startswith("Redis")


def test_claims_from_json_rejects_non_list() -> None:
    with pytest.raises(ValueError, match="claims must be a list"):
        claims_from_json({"id": "c1"})


def test_build_claim_extraction_messages() -> None:
    record = read_record(FIXTURE).record
    messages = build_claim_extraction_messages(record)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == get_prompt(PromptName.CLAIM_EXTRACTION)
    assert messages[1]["role"] == "user"
    assert "decision:" in messages[1]["content"] or "decision" in messages[1]["content"]


def test_extract_claims_mocked_json() -> None:
    record = _record_without_claims()

    def fake_fetch(*_args, **_kwargs):
        return MOCK_CLAIMS_JSON

    claims = extract_claims(record, fetch_json=fake_fetch)

    assert len(claims) == 2
    assert claims[0].id == "c1"


def test_extract_claims_raises_on_json_parse_failure() -> None:
    record = _record_without_claims()

    def failing_fetch(*_args, **_kwargs):
        raise JsonParseError("bad json")

    with pytest.raises(ClaimExtractionError, match="invalid JSON"):
        extract_claims(record, fetch_json=failing_fetch)


def test_extract_claims_raises_on_invalid_claim_shape() -> None:
    record = _record_without_claims()

    def bad_claims_fetch(*_args, **_kwargs):
        return [{"id": "c1"}]

    with pytest.raises(ClaimExtractionError, match="invalid claim objects"):
        extract_claims(record, fetch_json=bad_claims_fetch)


def test_extract_claims_uses_fetch_llm_json_by_default() -> None:
    record = _record_without_claims()

    with patch(
        "whyline.ingest.claims.fetch_llm_json",
        return_value=MOCK_CLAIMS_JSON,
    ) as mock_fetch:
        claims = extract_claims(record)

    assert len(claims) == 2
    mock_fetch.assert_called_once()
    call_kwargs = mock_fetch.call_args.kwargs
    assert call_kwargs["expect"] == "array"
