"""Serialize decision records to markdown with YAML frontmatter."""

from __future__ import annotations

import yaml

from yanka.records.models import Claim, Record, RecordBody
from yanka.records.verbatim import format_verbatim_block

_BODY_SECTIONS: tuple[tuple[str, str], ...] = (
    ("Rationale", "rationale"),
    ("Alternatives considered", "alternatives"),
    ("Scope and boundaries", "scope"),
    ("Implications", "implications"),
    ("Open questions", "open_questions"),
    ("Ownership", "ownership"),
    ("Context snapshot", "context_snapshot"),
    ("Raw input", "raw_input"),
    ("Clarifying exchange", "clarifying_exchange"),
)


def record_to_markdown(record: Record) -> str:
    """Serialize a Record to markdown with top-of-file YAML frontmatter."""
    frontmatter = record_to_frontmatter_dict(record)
    yaml_text = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    ).rstrip()
    body = _format_body(record.body)
    if body:
        return f"---\n{yaml_text}\n---\n\n{body}\n"
    return f"---\n{yaml_text}\n---\n"


def record_to_frontmatter_dict(record: Record) -> dict:
    """Build a YAML-serializable frontmatter dict from a Record."""
    data: dict = {
        "date": record.date,
        "type": record.type.value,
        "status": record.status.value,
        "record_complete": record.record_complete,
        "context_path": list(record.context_path),
        "people": list(record.people),
        "supersedes": record.supersedes,
        "tags": list(record.tags),
        "decision": record.decision,
    }
    if record.claims:
        data["claims"] = [_claim_to_dict(claim) for claim in record.claims]
    return data


def _claim_to_dict(claim: Claim) -> dict:
    payload: dict = {
        "id": claim.id,
        "content": claim.content,
        "status": claim.status.value,
    }
    if claim.supersedes is not None:
        payload["supersedes"] = {
            "file": claim.supersedes.file,
            "claim": claim.supersedes.claim,
        }
    return payload


def _format_body(body: RecordBody) -> str:
    parts: list[str] = []
    for heading, field_name in _BODY_SECTIONS:
        content = getattr(body, field_name)
        if not content or not str(content).strip():
            continue
        if field_name in {"raw_input", "clarifying_exchange"}:
            content = format_verbatim_block(str(content))
        parts.append(f"## {heading}\n{content}")
    return "\n\n".join(parts)
