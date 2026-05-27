from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from yanka.ingest.write import WriteResult
from yanka.records.io import read_record
from yanka.ui import confirmation_view_from_record, render_ingest_confirmation

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "with-claims.md"


def _capture(view) -> str:
    buffer = StringIO()
    console = Console(file=buffer, width=100, force_terminal=True, legacy_windows=False)
    render_ingest_confirmation(view, console=console)
    return buffer.getvalue()


def test_render_includes_core_record_fields() -> None:
    record = read_record(FIXTURE).record
    view = confirmation_view_from_record(
        record,
        path=Path("2026-05-14-drop-redis-sessions.md"),
    )

    output = _capture(view)

    assert "Record saved" in output
    assert "main-platform / auth-service" in output
    assert "Drop Redis for session storage" in output
    assert "Session data is stored in PostgreSQL" in output
    assert "tentative" in output
    assert "2026-05-14-drop-redis-sessions.md" in output
    assert "infra" in output


def test_render_lists_superseded_file_from_claim() -> None:
    record = read_record(FIXTURE).record
    view = confirmation_view_from_record(record, path=Path("with-claims.md"))

    output = _capture(view)

    assert "2026-02-10-redis-session-store.md" in output
    assert "Supersedes" in output


def test_render_shows_index_warning_from_write_result() -> None:
    record = read_record(FIXTURE).record
    result = WriteResult(
        path=Path("with-claims.md"),
        file_reference="records/with-claims.md",
        graph_ok=True,
        vectors_ok=False,
        index_errors=["[vectors] embed failed"],
    )
    view = confirmation_view_from_record(
        record,
        path=result.path,
        write_result=result,
    )

    output = _capture(view)

    assert "yanka rebuild" in output
    assert "[vectors] embed failed" in output


def test_confirmation_view_collects_extra_warnings() -> None:
    record = read_record(FIXTURE).record
    view = confirmation_view_from_record(
        record,
        path=Path("demo.md"),
        extra_warnings=["Claim coverage may be incomplete."],
    )

    assert "Claim coverage may be incomplete." in view.warnings
