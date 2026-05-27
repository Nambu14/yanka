from __future__ import annotations

from datetime import date

from yanka.ingest.session_transcript import (
    FINAL_CLARIFYING_ROUND_NUDGE,
    apply_session_transcript,
    build_clarifying_exchange,
)
from yanka.records.models import Record, RecordBody, RecordStatus, RecordType


def _minimal_record() -> Record:
    return Record(
        date=date(2026, 5, 27),
        type=RecordType.PROBLEM_STATEMENT,
        status=RecordStatus.TENTATIVE,
        context_path=["data-quality"],
        decision="Standardize sampling rates",
        record_complete=True,
        body=RecordBody(rationale="from model"),
    )


def test_build_clarifying_exchange_pairs_assistant_and_user() -> None:
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "Related records\n\n---\n\nUser dump:\nInitial note"},
        {"role": "assistant", "content": "What timeline?"},
        {"role": "user", "content": "One sprint for code"},
        {"role": "assistant", "content": "Any budget constraints?"},
        {"role": "user", "content": "No budget yet"},
    ]

    exchange = build_clarifying_exchange(messages)

    assert exchange is not None
    assert "### Round 1" in exchange
    assert "**Assistant:**\nWhat timeline?" in exchange
    assert "**User:**\nOne sprint for code" in exchange
    assert "### Round 2" in exchange
    assert "**User:**\nNo budget yet" in exchange


def test_build_clarifying_exchange_ignores_injected_user_messages() -> None:
    messages = [
        {"role": "user", "content": "Initial"},
        {"role": "assistant", "content": "Question?"},
        {"role": "user", "content": "Answer"},
        {"role": "user", "content": FINAL_CLARIFYING_ROUND_NUDGE},
        {"role": "assistant", "content": "Last question?"},
        {"role": "user", "content": "CONVERSATION ENDED — finalize now"},
    ]

    exchange = build_clarifying_exchange(messages)

    assert exchange is not None
    assert "Question?" in exchange
    assert "Answer" in exchange
    assert FINAL_CLARIFYING_ROUND_NUDGE not in exchange
    assert "CONVERSATION ENDED" not in exchange


def test_apply_session_transcript_sets_raw_input_from_dump() -> None:
    record = _minimal_record()
    record.body.raw_input = "model paraphrase"

    apply_session_transcript(
        record,
        "today i talked with Rudy about sampling",
        [{"role": "user", "content": "ignored"}],
    )

    assert record.body.raw_input == "today i talked with Rudy about sampling"
    assert record.body.clarifying_exchange is None
