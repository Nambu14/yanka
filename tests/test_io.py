from datetime import date
from pathlib import Path

import pytest

from whyline.paths import resolve_data_paths
from whyline.records.io import iter_records, read_record, write_record
from whyline.records.models import (
    Record,
    RecordBody,
    RecordStatus,
    RecordType,
    parse_record,
)


def _record(*, decision: str, context_path: list[str]) -> Record:
    return Record(
        date=date(2026, 5, 18),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=context_path,
        decision=decision,
        body=RecordBody(rationale="Because."),
        record_complete=True,
    )


def test_write_record_creates_markdown_file(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    record = _record(
        decision="Use local Ollama for testing",
        context_path=["main-platform"],
    )

    written = write_record(paths, record)

    assert written.exists()
    assert written.name == "2026-05-18-main-platform-use-local-ollama-for-testing.md"
    restored = parse_record(written.read_text(encoding="utf-8"))
    assert restored.decision == record.decision
    assert restored.context_path == record.context_path


def test_write_record_same_decision_different_projects(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    decision = "Use local Ollama for testing"

    first = write_record(
        paths,
        _record(decision=decision, context_path=["main-platform"]),
    )
    second = write_record(
        paths,
        _record(decision=decision, context_path=["mobile-app"]),
    )

    assert first != second
    assert first.exists() and second.exists()


def test_write_record_explicit_filename(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    record = _record(decision="Explicit path", context_path=["demo"])

    written = write_record(paths, record, filename="custom-name.md")

    assert written.name == "custom-name.md"


def test_read_record_round_trip(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    record = _record(decision="Readable record", context_path=["demo"])
    written = write_record(paths, record)

    loaded = read_record(written)

    assert loaded.path == written.resolve()
    assert loaded.record.decision == record.decision
    assert loaded.record.source_path == written.resolve()
    assert loaded.raw_text == written.read_text(encoding="utf-8")


def test_iter_records_yields_all_written(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    write_record(
        paths,
        _record(decision="First", context_path=["alpha"]),
    )
    write_record(
        paths,
        _record(decision="Second", context_path=["beta"]),
    )

    files = list(iter_records(paths))

    assert len(files) == 2
    assert files[0].path.name <= files[1].path.name
    decisions = {item.record.decision for item in files}
    assert decisions == {"First", "Second"}


def test_iter_records_empty_dir(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    paths.records_dir.mkdir(parents=True)

    assert list(iter_records(paths)) == []


def test_write_record_refuses_overwrite(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    record = _record(decision="No overwrite", context_path=["demo"])

    write_record(paths, record, filename="taken.md")

    with pytest.raises(FileExistsError):
        write_record(paths, record, filename="taken.md")
