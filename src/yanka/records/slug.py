"""Filename generation for decision records on disk."""

from __future__ import annotations

import re
from pathlib import Path

from yanka.records.models import Record

_MAX_SLUG_LEN = 48
_FALLBACK_SLUG = "record"


def slugify_text(text: str, *, max_len: int = _MAX_SLUG_LEN) -> str:
    """Lowercase hyphenated slug from arbitrary text."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        return _FALLBACK_SLUG
    return slug[:max_len].rstrip("-")


def record_filename(record: Record, *, context_depth: int = 1) -> str:
    """Build YYYY-MM-DD-{context}-{decision}.md for the given record."""
    stem = _filename_stem(record, context_depth=context_depth)
    return f"{stem}.md"


def unique_record_path(records_dir: Path, record: Record) -> Path:
    """Return an unused path under records_dir, extending context on collision."""
    records_dir.mkdir(parents=True, exist_ok=True)

    max_depth = max(1, len(record.context_path))
    for depth in range(1, max_depth + 1):
        candidate = records_dir / record_filename(record, context_depth=depth)
        if not candidate.exists():
            return candidate

    base_stem = _filename_stem(record, context_depth=max_depth)
    suffix = 2
    while True:
        candidate = records_dir / f"{base_stem}-{suffix}.md"
        if not candidate.exists():
            return candidate
        suffix += 1


def _filename_stem(record: Record, *, context_depth: int) -> str:
    day = record.date.isoformat()
    context_slug = _context_slug(record.context_path, depth=context_depth)
    decision_slug = slugify_decision(record.decision)
    return f"{day}-{context_slug}-{decision_slug}"


def slugify_decision(text: str) -> str:
    """Slug from the record's decision field."""
    return slugify_text(text)


def _context_slug(context_path: list[str], *, depth: int) -> str:
    if not context_path:
        return "general"
    segments = [slugify_text(part, max_len=32) for part in context_path[:depth]]
    return "-".join(segments)
