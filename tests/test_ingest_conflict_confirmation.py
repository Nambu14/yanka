from __future__ import annotations

from yanka.ingest.conflict_candidates import ConflictCandidate
from yanka.ingest.conflict_confirmation import (
    apply_confirmed_supersedes,
    confirm_detected_conflicts,
    parse_existing_claim_id,
)
from yanka.ingest.conflict_evaluation import DetectedConflict
from yanka.records.models import Claim, ClaimStatus, ClaimSupersedes


def _detected() -> DetectedConflict:
    return DetectedConflict(
        new_claim_id="c1",
        existing_claim_id="records/old.md:c2",
        reason="Different token lifetimes",
    )


def _candidate() -> ConflictCandidate:
    return ConflictCandidate(
        claim_id="records/old.md:c2",
        content="Token lifetime is 15 minutes",
        source_file="records/old.md",
        status="active",
        source="graph",
    )


def _claims() -> list[Claim]:
    return [
        Claim(
            id="c1",
            content="Token lifetime is 30 minutes",
            status=ClaimStatus.ACTIVE,
        ),
        Claim(
            id="c2",
            content="Refresh tokens rotate",
            status=ClaimStatus.ACTIVE,
        ),
    ]


def test_confirm_detected_conflicts_skips_when_empty() -> None:
    called = False

    def prompt(_view) -> bool:
        nonlocal called
        called = True
        return True

    confirmed, claims = confirm_detected_conflicts(
        [],
        _claims(),
        [_candidate()],
        prompt_confirm=prompt,
    )

    assert confirmed == []
    assert claims == _claims()
    assert called is False


def test_confirm_detected_conflicts_all_yes() -> None:
    prompts: list[str] = []

    def prompt(view) -> bool:
        prompts.append(view.old_content)
        return True

    confirmed, claims = confirm_detected_conflicts(
        [_detected()],
        _claims(),
        [_candidate()],
        prompt_confirm=prompt,
    )

    assert confirmed == [_detected()]
    assert claims[0].supersedes == ClaimSupersedes(file="old.md", claim="c2")
    assert claims[1].supersedes is None
    assert prompts == ["Token lifetime is 15 minutes"]


def test_confirm_detected_conflicts_all_no() -> None:
    confirmed, claims = confirm_detected_conflicts(
        [_detected()],
        _claims(),
        [_candidate()],
        prompt_confirm=lambda _view: False,
    )

    assert confirmed == []
    assert all(claim.supersedes is None for claim in claims)


def test_confirm_detected_conflicts_mixed() -> None:
    second = DetectedConflict(
        new_claim_id="c2",
        existing_claim_id="records/other.md:c1",
        reason="Storage choice",
    )
    other = ConflictCandidate(
        claim_id="records/other.md:c1",
        content="Sessions in Redis",
        source_file="records/other.md",
        status="active",
        source="vector",
    )

    def prompt(view) -> bool:
        return view.detected.new_claim_id == "c1"

    confirmed, claims = confirm_detected_conflicts(
        [_detected(), second],
        _claims(),
        [_candidate(), other],
        prompt_confirm=prompt,
    )

    assert confirmed == [_detected()]
    assert claims[0].supersedes == ClaimSupersedes(file="old.md", claim="c2")
    assert claims[1].supersedes is None


def test_parse_existing_claim_id_strips_records_prefix() -> None:
    assert parse_existing_claim_id("records/old.md:c2") == ClaimSupersedes(
        file="old.md",
        claim="c2",
    )


def test_parse_existing_claim_id_accepts_bare_filename() -> None:
    assert parse_existing_claim_id("2026-03-02-jwt.md:c2") == ClaimSupersedes(
        file="2026-03-02-jwt.md",
        claim="c2",
    )


def test_apply_confirmed_supersedes_noop_when_empty() -> None:
    updated = apply_confirmed_supersedes(_claims(), [])
    assert updated == _claims()
    assert updated is not _claims()
