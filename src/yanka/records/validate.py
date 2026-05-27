"""Validate decision record frontmatter and LLM completion signals."""

from __future__ import annotations

import re

from yanka.records.frontmatter import split_markdown

_OPENING_FENCE_RE = re.compile(r"^---\s*$")

REQUIRED_FRONTMATTER_KEYS = (
    "date",
    "type",
    "status",
    "context_path",
    "decision",
    "record_complete",
)


def validate_frontmatter_keys(frontmatter: dict) -> bool:
    """Return True when all required keys are present."""
    return all(key in frontmatter for key in REQUIRED_FRONTMATTER_KEYS)


def is_complete_record(text: str) -> bool:
    """True when text contains a valid finished record block."""
    return extract_complete_record_text(text) is not None


def extract_complete_record_text(text: str) -> str | None:
    """Return markdown for the first embedded complete record, if any.

    LLM replies often include preamble or closing prose around the record block.
    Scan each ``---`` opener and accept the first slice that passes completion checks.
    """
    if not text.strip():
        return None

    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not _OPENING_FENCE_RE.match(line.strip()):
            continue
        candidate = "".join(lines[index:])
        frontmatter, _body = split_markdown(candidate)
        if frontmatter is None:
            continue
        if not _record_complete_flag(frontmatter):
            continue
        if not validate_frontmatter_keys(frontmatter):
            continue
        return candidate
    return None


def _record_complete_flag(frontmatter: dict) -> bool:
    value = frontmatter.get("record_complete")
    return value is True or value == "true"
