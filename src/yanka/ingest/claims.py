"""Claim extraction from a finished record — spec §7 step 3."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from yanka.config import LlmConfig
from yanka.llm import JsonParseError, fetch_llm_json, get_prompt
from yanka.llm.client import LlmError
from yanka.llm.prompts import PromptName
from yanka.paths import DataPaths
from yanka.records.markdown import record_to_markdown
from yanka.records.models import Claim, Record, claims_from_json


class ClaimExtractionError(LlmError):
    """Claim extraction LLM call or response validation failed."""


def build_claim_extraction_messages(record: Record) -> list[dict[str, str]]:
    """Build the message list for the claim extraction LLM call."""
    return [
        {"role": "system", "content": get_prompt(PromptName.CLAIM_EXTRACTION)},
        {"role": "user", "content": record_to_markdown(record)},
    ]


def extract_claims(
    record: Record,
    *,
    paths: DataPaths | None = None,
    config: LlmConfig | None = None,
    fetch_json: Callable[..., Any] | None = None,
) -> list[Claim]:
    """Run claim extraction (Prompt 2) and return parsed claims."""
    fetch = fetch_json if fetch_json is not None else fetch_llm_json
    messages = build_claim_extraction_messages(record)
    try:
        data = fetch(
            messages,
            expect="array",
            paths=paths,
            config=config,
        )
    except JsonParseError as exc:
        msg = "claim extraction returned invalid JSON"
        raise ClaimExtractionError(msg) from exc

    try:
        return claims_from_json(data)
    except ValueError as exc:
        msg = "claim extraction returned invalid claim objects"
        raise ClaimExtractionError(msg) from exc
