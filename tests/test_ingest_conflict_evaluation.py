from __future__ import annotations

from whyline.ingest.conflict_candidates import ConflictCandidate
from whyline.ingest.conflict_evaluation import (
    DetectedConflict,
    build_conflict_evaluation_messages,
    evaluate_conflicts,
)
from whyline.llm import JsonParseError
from whyline.records.models import Claim, ClaimStatus


def _candidate(claim_id: str = "records/old.md:c2") -> ConflictCandidate:
    return ConflictCandidate(
        claim_id=claim_id,
        content="Token lifetime is 15 minutes",
        source_file="records/old.md",
        status="active",
        source="graph",
    )


def _new_claims() -> list[Claim]:
    return [
        Claim(
            id="c1",
            content="Token lifetime is 30 minutes",
            status=ClaimStatus.ACTIVE,
        ),
        Claim(
            id="c2",
            content="Refresh tokens rotate on each use",
            status=ClaimStatus.ACTIVE,
        ),
    ]


def test_evaluate_conflicts_skips_llm_when_no_candidates() -> None:
    called = False

    def fetch(_messages, **_kwargs):
        nonlocal called
        called = True
        return {"conflicts": []}

    result = evaluate_conflicts(
        _new_claims(),
        [],
        fetch_json=fetch,
    )

    assert result == []
    assert called is False


def test_evaluate_conflicts_parses_one_conflict() -> None:
    def fetch(_messages, **_kwargs):
        return {
            "conflicts": [
                {
                    "new_claim_id": "c1",
                    "existing_claim_id": "records/old.md:c2",
                    "reason": "Different token lifetimes",
                }
            ]
        }

    result = evaluate_conflicts(
        _new_claims(),
        [_candidate()],
        context_path=["main-platform", "auth-service"],
        fetch_json=fetch,
    )

    assert result == [
        DetectedConflict(
            new_claim_id="c1",
            existing_claim_id="records/old.md:c2",
            reason="Different token lifetimes",
        )
    ]


def test_evaluate_conflicts_empty_array() -> None:
    def fetch(_messages, **_kwargs):
        return {"conflicts": []}

    assert evaluate_conflicts(_new_claims(), [_candidate()], fetch_json=fetch) == []


def test_evaluate_conflicts_bad_json_returns_empty() -> None:
    def fetch(_messages, **_kwargs):
        raise JsonParseError("bad")

    assert evaluate_conflicts(_new_claims(), [_candidate()], fetch_json=fetch) == []


def test_evaluate_conflicts_drops_unknown_new_claim_id() -> None:
    def fetch(_messages, **_kwargs):
        return {
            "conflicts": [
                {
                    "new_claim_id": "c9",
                    "existing_claim_id": "records/old.md:c2",
                    "reason": "invalid new id",
                }
            ]
        }

    assert evaluate_conflicts(_new_claims(), [_candidate()], fetch_json=fetch) == []


def test_evaluate_conflicts_drops_unknown_existing_claim_id() -> None:
    def fetch(_messages, **_kwargs):
        return {
            "conflicts": [
                {
                    "new_claim_id": "c1",
                    "existing_claim_id": "records/other.md:c9",
                    "reason": "not a candidate",
                }
            ]
        }

    assert evaluate_conflicts(_new_claims(), [_candidate()], fetch_json=fetch) == []


def test_evaluate_conflicts_malformed_payload_returns_empty() -> None:
    def fetch(_messages, **_kwargs):
        return {"conflicts": "none"}

    assert evaluate_conflicts(_new_claims(), [_candidate()], fetch_json=fetch) == []


def test_build_conflict_evaluation_messages_includes_sources() -> None:
    messages = build_conflict_evaluation_messages(
        _new_claims(),
        [_candidate()],
        context_path=["main-platform", "auth-service"],
    )

    user = messages[1]["content"]
    assert "NEW CLAIMS" in user
    assert '- c1: "Token lifetime is 30 minutes"' in user
    assert "[source: graph, project: main-platform" in user
    assert "context: main-platform/auth-service]" in user
    assert "records/old.md:c2" in user


def test_evaluate_conflicts_accepts_preamble_style_payload() -> None:
    def fetch(_messages, **_kwargs):
        return {
            "conflicts": [
                {
                    "new_claim_id": "c1",
                    "existing_claim_id": "a.md:c2",
                    "reason": "overlap",
                }
            ]
        }

    candidates = [
        ConflictCandidate(
            claim_id="a.md:c2",
            content="overlap",
            source_file="a.md",
            status="active",
            source="vector",
        )
    ]
    claims = [Claim(id="c1", content="x", status=ClaimStatus.ACTIVE)]

    result = evaluate_conflicts(claims, candidates, fetch_json=fetch)

    assert result[0].existing_claim_id == "a.md:c2"
