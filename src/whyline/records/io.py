"""Read and write decision record files on disk."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

from whyline.paths import DataPaths
from whyline.records.changelog import append_changelog, entry_for_written_record
from whyline.records.markdown import record_to_markdown
from whyline.records.models import Record, RecordFile, parse_record
from whyline.records.slug import unique_record_path


def read_record(path: Path) -> RecordFile:
    """Read and parse a single record markdown file."""
    raw_text = path.read_text(encoding="utf-8")
    record = parse_record(raw_text)
    record.source_path = path.resolve()
    record.raw_markdown = raw_text
    return RecordFile(path=path.resolve(), record=record, raw_text=raw_text)


def iter_records(paths: DataPaths) -> Iterator[RecordFile]:
    """Yield all .md records under paths.records_dir, sorted by path."""
    if not paths.records_dir.is_dir():
        return

    for path in sorted(paths.records_dir.glob("*.md")):
        if path.is_file():
            yield read_record(path)


def write_record(
    paths: DataPaths,
    record: Record,
    *,
    filename: str | None = None,
) -> Path:
    """Write a record to records_dir. Returns the path written."""
    paths.records_dir.mkdir(parents=True, exist_ok=True)

    if filename is not None:
        target = paths.records_dir / filename
        if target.exists():
            msg = f"Record already exists: {target}"
            raise FileExistsError(msg)
    else:
        target = unique_record_path(paths.records_dir, record)

    content = record_to_markdown(record)
    _atomic_write_text(target, content)
    append_changelog(paths, entry_for_written_record(target.name, content, record))
    return target


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temp = Path(temp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
