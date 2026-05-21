"""Claim validation and retry — spec §7 step 4."""

from __future__ import annotations

import re
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from whyline.config import LlmConfig
from whyline.ingest.claims import ClaimExtractionError, extract_claims
from whyline.llm import JsonParseError, get_prompt
from whyline.llm.json_parse import fetch_llm_json
from whyline.llm.prompts import PromptName
from whyline.paths import DataPaths
from whyline.records.markdown import record_to_markdown
from whyline.records.models import Claim, Record, RecordBody, claims_from_json

AMBER_COVERAGE_WARNING = "Claim coverage may be incomplete."

_STOPWORDS = frozenset({
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "the",
    "to",
    "was",
    "were",
    "with",
})


class ClaimValidationIssue(StrEnum):
    EMPTY = "empty"
    COVERAGE = "coverage"


def validate_claims(record: Record, claims: list[Claim]) -> list[ClaimValidationIssue]:
    """Return validation issues; empty list means pass."""
    issues: list[ClaimValidationIssue] = []
    if not claims:
        issues.append(ClaimValidationIssue.EMPTY)
        return issues
    if not _decision_covered_by_claims(record.decision, claims):
        issues.append(ClaimValidationIssue.COVERAGE)
    return issues


def build_claim_extraction_retry_messages(
    record: Record,
    issues: list[ClaimValidationIssue],
) -> list[dict[str, str]]:
    """Build claim extraction messages with explicit coverage hints for one retry."""
    base = record_to_markdown(record)
    appendix = _retry_appendix(record, issues)
    return [
        {"role": "system", "content": get_prompt(PromptName.CLAIM_EXTRACTION)},
        {"role": "user", "content": f"{base}\n\n{appendix}"},
    ]


def extract_claims_validated(
    record: Record,
    *,
    paths: DataPaths | None = None,
    config: LlmConfig | None = None,
    fetch_json: Callable[..., Any] | None = None,
) -> tuple[list[Claim], list[str]]:
    """Extract claims, validate, retry once, return warnings if still weak."""
    fetch = fetch_json if fetch_json is not None else fetch_llm_json
    warnings: list[str] = []

    try:
        claims = extract_claims(record, paths=paths, config=config, fetch_json=fetch)
    except ClaimExtractionError:
        return [], [AMBER_COVERAGE_WARNING]

    issues = validate_claims(record, claims)
    if not issues:
        return claims, warnings

    try:
        messages = build_claim_extraction_retry_messages(record, issues)
        data = fetch(messages, expect="array", paths=paths, config=config)
        claims = claims_from_json(data)
    except (ClaimExtractionError, JsonParseError, ValueError):
        warnings.append(AMBER_COVERAGE_WARNING)
        return claims, warnings

    if validate_claims(record, claims):
        warnings.append(AMBER_COVERAGE_WARNING)
    return claims, warnings


def _decision_covered_by_claims(decision: str, claims: list[Claim]) -> bool:
    keywords = _significant_tokens(decision)
    if not keywords:
        return True
    blob = " ".join(claim.content.lower() for claim in claims)
    return any(keyword in blob for keyword in keywords)


def _significant_tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {word for word in words if len(word) >= 3 and word not in _STOPWORDS}


def _retry_appendix(record: Record, issues: list[ClaimValidationIssue]) -> str:
    lines = [
        "---",
        "Ensure claims cover the following (prior extraction was incomplete):",
        f"Decision: {record.decision}",
    ]
    lines.extend(_body_lines_for_retry(record.body))
    if ClaimValidationIssue.EMPTY in issues:
        lines.append("Return at least one atomic claim.")
    if ClaimValidationIssue.COVERAGE in issues:
        lines.append(
            "At least one claim must reflect the core decision assertion above."
        )
    return "\n".join(lines)


def _body_lines_for_retry(body: RecordBody) -> list[str]:
    sections: list[tuple[str, str | None]] = [
        ("Rationale", body.rationale),
        ("Alternatives considered", body.alternatives),
        ("Scope and boundaries", body.scope),
        ("Implications", body.implications),
        ("Ownership", body.ownership),
    ]
    lines: list[str] = []
    for heading, content in sections:
        if content and str(content).strip():
            lines.append(f"{heading}: {str(content).strip()}")
    return lines
