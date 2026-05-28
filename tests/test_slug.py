from datetime import date
from pathlib import Path

from yanka.records.models import (
    Record,
    RecordBody,
    RecordStatus,
    RecordType,
)
from yanka.records.slug import (
    record_filename,
    slugify_decision,
    slugify_text,
    unique_record_path,
)


def _record(
    *,
    decision: str,
    context_path: list[str],
    record_date: date | None = None,
) -> Record:
    return Record(
        date=record_date or date(2026, 5, 18),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=context_path,
        decision=decision,
        body=RecordBody(),
        record_complete=True,
    )


def test_slugify_decision_basic() -> None:
    assert slugify_decision("Drop Redis for session storage") == ("drop-redis-for-session-storage")


def test_slugify_text_fallback_for_empty() -> None:
    assert slugify_text("   ") == "record"


def test_record_filename_includes_project_and_decision() -> None:
    record = _record(
        decision="Use local Ollama for testing",
        context_path=["main-platform", "auth-service"],
    )
    assert record_filename(record) == "2026-05-18-main-platform-use-local-ollama-for-testing.md"


def test_same_decision_different_projects_get_different_names() -> None:
    decision = "Use local Ollama for testing"
    a = _record(decision=decision, context_path=["main-platform"])
    b = _record(decision=decision, context_path=["mobile-app"])

    assert record_filename(a) != record_filename(b)
    assert "main-platform" in record_filename(a)
    assert "mobile-app" in record_filename(b)


def test_unique_record_path_extends_context_before_numeric_suffix(
    tmp_path: Path,
) -> None:
    records_dir = tmp_path / "records"
    records_dir.mkdir()
    record = _record(
        decision="Use local Ollama",
        context_path=["main-platform", "auth-service"],
    )

    first = unique_record_path(records_dir, record)
    first.write_text("existing")

    second = unique_record_path(records_dir, record)
    assert second.name == ("2026-05-18-main-platform-auth-service-use-local-ollama.md")

    second.write_text("existing")

    third = unique_record_path(records_dir, record)
    assert third.name == "2026-05-18-main-platform-auth-service-use-local-ollama-2.md"
