"""Typed decision record model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from yanka.records.frontmatter import split_markdown

_SECTION_PATTERN = re.compile(r"^## (.+)$", re.MULTILINE)

_SECTION_KEYS: dict[str, str] = {
    "Rationale": "rationale",
    "Alternatives considered": "alternatives",
    "Scope and boundaries": "scope",
    "Implications": "implications",
    "Open questions": "open_questions",
    "Ownership": "ownership",
    "Context snapshot": "context_snapshot",
    "Raw input": "raw_input",
    "Clarifying exchange": "clarifying_exchange",
}


class RecordType(StrEnum):
    DECISION = "decision"
    MEETING_SUMMARY = "meeting-summary"
    DISCOVERY = "discovery"
    CONTEXT = "context"
    PROBLEM_STATEMENT = "problem-statement"


class RecordStatus(StrEnum):
    ACTIVE = "active"
    TENTATIVE = "tentative"
    SUPERSEDED = "superseded"


class ClaimStatus(StrEnum):
    ACTIVE = "active"
    TENTATIVE = "tentative"
    SUPERSEDED = "superseded"


@dataclass
class ClaimSupersedes:
    file: str
    claim: str


@dataclass
class Claim:
    id: str
    content: str
    status: ClaimStatus
    supersedes: ClaimSupersedes | None = None


@dataclass
class RecordBody:
    rationale: str | None = None
    alternatives: str | None = None
    scope: str | None = None
    implications: str | None = None
    open_questions: str | None = None
    ownership: str | None = None
    context_snapshot: str | None = None
    raw_input: str | None = None
    clarifying_exchange: str | None = None


@dataclass
class Record:
    date: date
    type: RecordType
    status: RecordStatus
    context_path: list[str]
    decision: str
    people: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    supersedes: str | None = None
    claims: list[Claim] = field(default_factory=list)
    record_complete: bool = False
    body: RecordBody = field(default_factory=RecordBody)
    source_path: Path | None = None
    raw_markdown: str | None = None


@dataclass
class RecordFile:
    path: Path
    record: Record
    raw_text: str


def parse_record(text: str) -> Record:
    """Parse a markdown record file into a Record."""
    frontmatter, body = split_markdown(text)
    if frontmatter is None:
        msg = "No valid frontmatter block found"
        raise ValueError(msg)
    return record_from_frontmatter(frontmatter, body, raw_markdown=text)


def record_from_frontmatter(
    frontmatter: dict[str, Any],
    body: str = "",
    *,
    raw_markdown: str | None = None,
    source_path: Path | None = None,
) -> Record:
    """Build a Record from a parsed frontmatter dict and markdown body."""
    return Record(
        date=_parse_date(frontmatter["date"]),
        type=_parse_record_type(frontmatter["type"]),
        status=_parse_record_status(frontmatter["status"]),
        context_path=_parse_string_list(frontmatter["context_path"], "context_path"),
        decision=_require_str(frontmatter["decision"], "decision"),
        people=_parse_optional_string_list(frontmatter.get("people")),
        tags=_parse_optional_string_list(frontmatter.get("tags")),
        supersedes=_parse_optional_str(frontmatter.get("supersedes")),
        claims=_parse_claims(frontmatter.get("claims")),
        record_complete=frontmatter.get("record_complete") is True,
        body=_parse_body(body),
        source_path=source_path,
        raw_markdown=raw_markdown,
    )


def _parse_body(body: str) -> RecordBody:
    sections = _split_sections(body.strip())
    kwargs: dict[str, str | None] = {key: None for key in _SECTION_KEYS.values()}
    for heading, content in sections.items():
        field_name = _SECTION_KEYS.get(heading)
        if field_name is None:
            continue
        text = content.strip() or None
        if text is not None and field_name == "raw_input":
            text = _unquote_raw_input(text)
        kwargs[field_name] = text
    return RecordBody(**kwargs)


def _unquote_raw_input(content: str) -> str:
    lines: list[str] = []
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(">"):
            stripped = stripped[1:].lstrip()
        lines.append(stripped)
    return "\n".join(lines).strip()


def _split_sections(body: str) -> dict[str, str]:
    if not body.strip():
        return {}

    matches = list(_SECTION_PATTERN.finditer(body))
    if not matches:
        return {}

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[heading] = body[start:end].strip()
    return sections


def claims_from_json(raw: Any) -> list[Claim]:
    """Parse a JSON claim array (LLM output or YAML frontmatter) into Claim objects."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        msg = "claims must be a list"
        raise ValueError(msg)

    claims: list[Claim] = []
    for item in raw:
        if not isinstance(item, dict):
            msg = "each claim must be a mapping"
            raise ValueError(msg)
        supersedes = None
        raw_supersedes = item.get("supersedes")
        if raw_supersedes is not None:
            if not isinstance(raw_supersedes, dict):
                msg = "claim supersedes must be a mapping"
                raise ValueError(msg)
            supersedes = ClaimSupersedes(
                file=_require_str(raw_supersedes.get("file"), "supersedes.file"),
                claim=_require_str(raw_supersedes.get("claim"), "supersedes.claim"),
            )
        claims.append(
            Claim(
                id=_require_str(item.get("id"), "claim.id"),
                content=_require_str(item.get("content"), "claim.content"),
                status=_parse_claim_status(item.get("status")),
                supersedes=supersedes,
            )
        )
    return claims


def _parse_claims(raw: Any) -> list[Claim]:
    return claims_from_json(raw)


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    msg = "date must be a YYYY-MM-DD value"
    raise ValueError(msg)


def _parse_record_type(value: Any) -> RecordType:
    try:
        return RecordType(str(value))
    except ValueError as exc:
        msg = f"invalid record type: {value!r}"
        raise ValueError(msg) from exc


def _parse_record_status(value: Any) -> RecordStatus:
    try:
        return RecordStatus(str(value))
    except ValueError as exc:
        msg = f"invalid record status: {value!r}"
        raise ValueError(msg) from exc


def _parse_claim_status(value: Any) -> ClaimStatus:
    try:
        return ClaimStatus(str(value))
    except ValueError as exc:
        msg = f"invalid claim status: {value!r}"
        raise ValueError(msg) from exc


def _parse_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = f"{field_name} must be a list of strings"
        raise ValueError(msg)
    return list(value)


def _parse_optional_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    return _parse_string_list(value, "list")


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must be a non-empty string"
        raise ValueError(msg)
    return value


def _parse_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        msg = "value must be a string or null"
        raise ValueError(msg)
    return value
