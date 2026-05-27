"""Append-only audit log for record filesystem operations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from yanka.paths import DataPaths
from yanka.records.models import Record

ChangelogAction = Literal["create", "supersede"]


@dataclass
class ChangelogEntry:
    ts: str
    action: ChangelogAction
    file: str
    hash: str
    supersedes_file: str | None = None
    supersedes_claims: list[dict[str, str]] | None = None


def content_hash(text: str) -> str:
    """SHA-256 hex digest of the record file content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def append_changelog(paths: DataPaths, entry: ChangelogEntry) -> None:
    """Append one JSON line to changelog.jsonl."""
    paths.changelog_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry_to_dict(entry), separators=(",", ":")) + "\n"
    with paths.changelog_path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def iter_changelog(paths: DataPaths) -> Iterator[ChangelogEntry]:
    """Read all changelog entries in order."""
    if not paths.changelog_path.is_file():
        return

    for line in paths.changelog_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        yield ChangelogEntry(
            ts=raw["ts"],
            action=raw["action"],
            file=raw["file"],
            hash=raw["hash"],
            supersedes_file=raw.get("supersedes_file"),
            supersedes_claims=raw.get("supersedes_claims"),
        )


def entry_to_dict(entry: ChangelogEntry) -> dict[str, Any]:
    """Serialize a changelog entry, omitting unset optional fields."""
    data = asdict(entry)
    if entry.supersedes_file is None:
        data.pop("supersedes_file", None)
    if entry.supersedes_claims is None:
        data.pop("supersedes_claims", None)
    return data


def utc_timestamp() -> str:
    """Current UTC time in ISO-8601 with Z suffix."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_entry(file: str, content: str, *, ts: str | None = None) -> ChangelogEntry:
    """Build a create entry for a newly written record file."""
    return ChangelogEntry(
        ts=ts or utc_timestamp(),
        action="create",
        file=file,
        hash=content_hash(content),
    )


def entry_for_written_record(
    file: str,
    content: str,
    record: Record,
    *,
    ts: str | None = None,
) -> ChangelogEntry:
    """Build a changelog entry for a record write (create or supersede)."""
    superseded_claims = _supersedes_claims_for_record(record)
    if record.supersedes is not None or superseded_claims is not None:
        return ChangelogEntry(
            ts=ts or utc_timestamp(),
            action="supersede",
            file=file,
            hash=content_hash(content),
            supersedes_file=record.supersedes,
            supersedes_claims=superseded_claims,
        )
    return create_entry(file, content, ts=ts)


def _supersedes_claims_for_record(record: Record) -> list[dict[str, str]] | None:
    pairs: list[dict[str, str]] = []
    for claim in record.claims:
        if claim.supersedes is None:
            continue
        pairs.append(
            {
                "new": claim.id,
                "old": f"{claim.supersedes.file}:{claim.supersedes.claim}",
            }
        )
    if not pairs:
        return None
    return pairs
