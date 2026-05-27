"""Conflict evaluation (Prompt 3) — spec §7 step 7."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from yanka.config import LlmConfig
from yanka.ingest.conflict_candidates import ConflictCandidate
from yanka.llm import JsonParseError, fetch_llm_json, get_prompt
from yanka.llm.client import LlmError
from yanka.llm.prompts import PromptName
from yanka.paths import DataPaths
from yanka.records.models import Claim


class ConflictEvaluationError(LlmError):
    """Conflict evaluation LLM transport failed."""


@dataclass(frozen=True)
class DetectedConflict:
    """A genuine conflict where a new claim supersedes an existing one."""

    new_claim_id: str
    existing_claim_id: str
    reason: str


def build_conflict_evaluation_messages(
    new_claims: list[Claim],
    candidates: list[ConflictCandidate],
    *,
    context_path: list[str] | None = None,
) -> list[dict[str, str]]:
    """Build messages for the conflict evaluation LLM call (spec Prompt 3)."""
    return [
        {"role": "system", "content": get_prompt(PromptName.CONFLICT_EVALUATION)},
        {
            "role": "user",
            "content": _format_evaluation_input(
                new_claims,
                candidates,
                context_path=context_path,
            ),
        },
    ]


def evaluate_conflicts(
    new_claims: list[Claim],
    candidates: list[ConflictCandidate],
    *,
    context_path: list[str] | None = None,
    paths: DataPaths | None = None,
    config: LlmConfig | None = None,
    fetch_json: Callable[..., Any] | None = None,
) -> list[DetectedConflict]:
    """Run Prompt 3; return conflicts (empty if no candidates or on parse failure)."""
    if not candidates:
        return []

    fetch = fetch_json if fetch_json is not None else fetch_llm_json
    messages = build_conflict_evaluation_messages(
        new_claims,
        candidates,
        context_path=context_path,
    )
    try:
        data = fetch(
            messages,
            expect="object",
            paths=paths,
            config=config,
        )
    except JsonParseError:
        return []

    return _parse_conflicts_response(data, new_claims, candidates)


def _format_evaluation_input(
    new_claims: list[Claim],
    candidates: list[ConflictCandidate],
    *,
    context_path: list[str] | None,
) -> str:
    project = context_path[0] if context_path else "unknown"
    context_label = "/".join(context_path) if context_path else "unknown"

    new_lines = [
        f'- {claim.id}: "{claim.content}"' for claim in new_claims
    ]
    existing_lines = [
        _format_candidate_line(candidate, project=project, context=context_label)
        for candidate in candidates
    ]

    parts = [
        "NEW CLAIMS (being recorded now):",
        *new_lines,
        "",
        "EXISTING CLAIMS (from vector search and graph — tag each with source):",
        *existing_lines,
    ]
    return "\n".join(parts)


def _format_candidate_line(
    candidate: ConflictCandidate,
    *,
    project: str,
    context: str,
) -> str:
    return (
        f'- {candidate.claim_id}: "{candidate.content}" '
        f"[source: {candidate.source}, project: {project}, context: {context}]"
    )


def _parse_conflicts_response(
    data: Any,
    new_claims: list[Claim],
    candidates: list[ConflictCandidate],
) -> list[DetectedConflict]:
    if not isinstance(data, dict):
        return []

    raw_conflicts = data.get("conflicts")
    if raw_conflicts is None:
        return []
    if not isinstance(raw_conflicts, list):
        return []

    valid_new_ids = {claim.id for claim in new_claims}
    valid_existing_ids = {candidate.claim_id for candidate in candidates}
    detected: list[DetectedConflict] = []

    for item in raw_conflicts:
        parsed = _parse_conflict_item(item)
        if parsed is None:
            continue
        new_id, existing_id, reason = parsed
        if new_id not in valid_new_ids:
            continue
        if existing_id not in valid_existing_ids:
            continue
        detected.append(
            DetectedConflict(
                new_claim_id=new_id,
                existing_claim_id=existing_id,
                reason=reason,
            )
        )

    return detected


def _parse_conflict_item(item: Any) -> tuple[str, str, str] | None:
    if not isinstance(item, dict):
        return None

    new_claim_id = item.get("new_claim_id")
    existing_claim_id = item.get("existing_claim_id")
    reason = item.get("reason")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (new_claim_id, existing_claim_id, reason)
    ):
        return None

    return new_claim_id, existing_claim_id, reason.strip()
