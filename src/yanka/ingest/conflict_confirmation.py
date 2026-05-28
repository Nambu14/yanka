"""User confirmation for detected conflicts — spec §7 step 8."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from yanka.ingest.conflict_candidates import ConflictCandidate
from yanka.ingest.conflict_evaluation import DetectedConflict
from yanka.records.models import Claim, ClaimSupersedes

PromptConfirm = Callable[["ConflictPromptView"], bool]


@dataclass(frozen=True)
class ConflictPromptView:
    """One conflict surfaced for yes/no confirmation."""

    detected: DetectedConflict
    old_content: str
    new_content: str


def confirm_detected_conflicts(
    detected: list[DetectedConflict],
    new_claims: list[Claim],
    candidates: list[ConflictCandidate],
    *,
    prompt_confirm: PromptConfirm | None = None,
) -> tuple[list[DetectedConflict], list[Claim]]:
    """Ask the user per conflict; return confirmed rows and updated claims."""
    if not detected:
        return [], list(new_claims)

    if prompt_confirm is None:
        from yanka.ui.conflict_confirm import default_conflict_prompt

        prompt_confirm = default_conflict_prompt

    candidate_by_id = {candidate.claim_id: candidate for candidate in candidates}
    claim_by_id = {claim.id: claim for claim in new_claims}
    confirmed: list[DetectedConflict] = []

    for conflict in detected:
        view = build_conflict_prompt_view(
            conflict,
            candidate_by_id=candidate_by_id,
            claim_by_id=claim_by_id,
        )
        if prompt_confirm(view):
            confirmed.append(conflict)

    updated_claims = apply_confirmed_supersedes(new_claims, confirmed)
    return confirmed, updated_claims


def build_conflict_prompt_view(
    detected: DetectedConflict,
    *,
    candidate_by_id: dict[str, ConflictCandidate],
    claim_by_id: dict[str, Claim],
) -> ConflictPromptView:
    """Resolve old/new claim text for display."""
    candidate = candidate_by_id.get(detected.existing_claim_id)
    if candidate is not None:
        old_content = candidate.content
    else:
        old_content = detected.existing_claim_id
    new_claim = claim_by_id.get(detected.new_claim_id)
    if new_claim is not None:
        new_content = new_claim.content
    else:
        new_content = detected.new_claim_id
    return ConflictPromptView(
        detected=detected,
        old_content=old_content,
        new_content=new_content,
    )


def apply_confirmed_supersedes(
    claims: list[Claim],
    confirmed: list[DetectedConflict],
) -> list[Claim]:
    """Return a new claims list with ``supersedes`` set on confirmed new claims."""
    if not confirmed:
        return list(claims)

    supersede_by_new_id = {
        conflict.new_claim_id: parse_existing_claim_id(conflict.existing_claim_id) for conflict in confirmed
    }
    updated: list[Claim] = []
    for claim in claims:
        target = supersede_by_new_id.get(claim.id)
        if target is None:
            updated.append(claim)
        else:
            updated.append(replace(claim, supersedes=target))
    return updated


def parse_existing_claim_id(existing_claim_id: str) -> ClaimSupersedes:
    """Parse composite claim id into frontmatter ``supersedes`` shape."""
    file_part, separator, claim_id = existing_claim_id.rpartition(":")
    if not separator:
        msg = f"invalid existing_claim_id: {existing_claim_id!r}"
        raise ValueError(msg)

    file_ref = file_part
    if file_ref.startswith("records/"):
        file_ref = file_ref.removeprefix("records/")
    return ClaimSupersedes(file=file_ref, claim=claim_id)
