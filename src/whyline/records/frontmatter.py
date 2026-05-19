"""Parse YAML frontmatter from decision record markdown.

Only the first frontmatter block at the top of the file is structural.
Horizontal rules (---) in the body are ignored.
"""

from __future__ import annotations

import re

import yaml

_FENCE = "---"
_OPENING_FENCE_RE = re.compile(r"^---\s*$")


def split_markdown(text: str) -> tuple[dict | None, str]:
    """Split top-of-file YAML frontmatter from the markdown body.

    Returns (frontmatter_dict, body). frontmatter is None if no valid block.
    """
    if not text.strip():
        return None, text

    lines = text.splitlines(keepends=True)
    start = _first_non_empty_line(lines)
    if start is None or not _OPENING_FENCE_RE.match(lines[start].strip()):
        return None, text

    close = _find_closing_fence(lines, start + 1)
    if close is None:
        return None, text

    yaml_text = "".join(lines[start + 1 : close])
    body = "".join(lines[close + 1 :])

    if not yaml_text.strip():
        return None, text

    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return None, text

    if parsed is None:
        return {}, body
    if not isinstance(parsed, dict):
        return None, text

    return parsed, body


def parse_frontmatter(text: str) -> dict | None:
    """Parse YAML frontmatter only. None if missing or invalid."""
    frontmatter, _body = split_markdown(text)
    return frontmatter


def parse_record_markdown(text: str) -> tuple[dict | None, str]:
    """Parse frontmatter dict and body string from a record file."""
    return split_markdown(text)


def _first_non_empty_line(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if line.strip():
            return index
    return None


def _find_closing_fence(lines: list[str], after_open: int) -> int | None:
    for index in range(after_open, len(lines)):
        if _OPENING_FENCE_RE.match(lines[index].strip()):
            return index
    return None
