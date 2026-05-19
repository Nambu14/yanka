"""Validate decision record frontmatter and LLM completion signals."""

from __future__ import annotations

from whyline.records.frontmatter import split_markdown

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
    """True when text has valid top frontmatter signaling a finished record.

    Completion requires record_complete: true (YAML boolean) and all required keys.
    Never treats bare --- fences alone as completion.
    """
    frontmatter, _body = split_markdown(text)
    if frontmatter is None:
        return False
    if frontmatter.get("record_complete") is not True:
        return False
    return validate_frontmatter_keys(frontmatter)
