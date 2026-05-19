import json
from datetime import date
from pathlib import Path

from whyline.paths import resolve_data_paths
from whyline.records.changelog import (
    ChangelogEntry,
    append_changelog,
    content_hash,
    create_entry,
    iter_changelog,
    utc_timestamp,
)
from whyline.records.io import write_record
from whyline.records.models import Record, RecordBody, RecordStatus, RecordType


def _record() -> Record:
    return Record(
        date=date(2026, 5, 18),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=["main-platform"],
        decision="Changelog test decision",
        body=RecordBody(rationale="Because."),
        record_complete=True,
    )


def test_content_hash_is_stable() -> None:
    text = "same content\n"
    assert content_hash(text) == content_hash(text)
    assert len(content_hash(text)) == 64


def test_append_changelog_writes_create_line(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    entry = create_entry("2026-05-18-demo.md", "---\ndate: 2026-05-18\n---\n")

    append_changelog(paths, entry)

    lines = paths.changelog_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["action"] == "create"
    assert parsed["file"] == "2026-05-18-demo.md"
    assert parsed["hash"] == entry.hash
    assert "supersedes_file" not in parsed


def test_iter_changelog_reads_entries_in_order(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    first = ChangelogEntry(
        ts=utc_timestamp(),
        action="create",
        file="a.md",
        hash=content_hash("a"),
    )
    second = ChangelogEntry(
        ts=utc_timestamp(),
        action="create",
        file="b.md",
        hash=content_hash("b"),
    )
    append_changelog(paths, first)
    append_changelog(paths, second)

    entries = list(iter_changelog(paths))

    assert [entry.file for entry in entries] == ["a.md", "b.md"]


def test_write_record_appends_changelog(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    written = write_record(paths, _record())

    entries = list(iter_changelog(paths))
    assert len(entries) == 1
    assert entries[0].action == "create"
    assert entries[0].file == written.name
    assert entries[0].hash == content_hash(written.read_text(encoding="utf-8"))
