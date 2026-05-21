from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from whyline.ingest.extraction import (
    FINAL_CLARIFYING_ROUND_NUDGE,
    WRAP_UP_USER_MESSAGE,
    RecordExtractionError,
    build_record_extraction_conversation,
    run_record_extraction_loop,
    run_record_extraction_loop_detailed,
)
from whyline.paths import resolve_data_paths
from whyline.records.validate import is_complete_record

FIXTURES = Path(__file__).parent / "fixtures" / "records"
CLARIFYING = (FIXTURES / "clarifying-questions.md").read_text(encoding="utf-8")
COMPLETE = (FIXTURES / "valid-decision.md").read_text(encoding="utf-8")
def test_build_record_extraction_conversation_includes_dump() -> None:
    messages = build_record_extraction_conversation(
        "We are dropping Redis",
        resolve_data_paths(Path("/tmp/whyline-empty-test")),
    )
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "We are dropping Redis" in messages[1]["content"]


def test_extraction_loop_qa_then_record() -> None:
    calls: list[list[dict[str, str]]] = []

    def fake_send(messages, **_kwargs):
        calls.append(list(messages))
        if len(calls) == 1:
            return CLARIFYING
        return COMPLETE

    prompt_user = MagicMock(return_value="PostgreSQL only, no Redis.")

    record = run_record_extraction_loop(
        "Dropping Redis for sessions",
        resolve_data_paths(Path("/tmp/whyline-extract-1")),
        prompt_user=prompt_user,
        send=fake_send,
    )

    assert record.decision == "Drop Redis for session storage"
    assert is_complete_record(COMPLETE)
    prompt_user.assert_called_once()
    assert len(calls) == 2


def test_extraction_loop_accepts_record_with_preamble_and_trailing_prose() -> None:
    preamble_record = (
        "Thanks! Here is the record:\n\n"
        f"{COMPLETE}\n\n"
        "Happy to help if you need edits.\n"
    )

    record = run_record_extraction_loop(
        "Dropping Redis",
        resolve_data_paths(Path("/tmp/whyline-extract-embedded")),
        prompt_user=MagicMock(),
        send=lambda _messages, **_kwargs: preamble_record,
    )

    assert record.decision == "Drop Redis for session storage"


def test_extraction_loop_single_shot_record() -> None:
    prompt_user = MagicMock()

    record = run_record_extraction_loop(
        "Dropping Redis",
        resolve_data_paths(Path("/tmp/whyline-extract-2")),
        prompt_user=prompt_user,
        send=lambda _messages, **_kwargs: COMPLETE,
    )

    assert record.decision == "Drop Redis for session storage"
    prompt_user.assert_not_called()


def test_extraction_loop_two_clarifying_rounds_then_wrap_up() -> None:
    calls: list[list[dict[str, str]]] = []

    def fake_send(messages, **_kwargs):
        calls.append(list(messages))
        if len(calls) <= 2:
            return CLARIFYING
        return COMPLETE

    prompt_user = MagicMock(side_effect=["answer one", "answer two"])

    record = run_record_extraction_loop(
        "Dropping Redis",
        resolve_data_paths(Path("/tmp/whyline-extract-3")),
        prompt_user=prompt_user,
        send=fake_send,
    )

    assert record.decision == "Drop Redis for session storage"
    assert prompt_user.call_count == 2
    assert len(calls) == 3
    round_two_user_texts = [m["content"] for m in calls[1] if m["role"] == "user"]
    assert FINAL_CLARIFYING_ROUND_NUDGE in round_two_user_texts
    wrap_up_users = [m["content"] for m in calls[2] if m["role"] == "user"]
    assert any(WRAP_UP_USER_MESSAGE in text for text in wrap_up_users)


def test_extraction_loop_raises_after_failed_wrap_up() -> None:
    def always_clarify(_messages, **_kwargs):
        return CLARIFYING

    with pytest.raises(RecordExtractionError, match="wrap-up"):
        run_record_extraction_loop(
            "Dropping Redis",
            resolve_data_paths(Path("/tmp/whyline-extract-4")),
            prompt_user=lambda _q: "answers",
            send=always_clarify,
        )


def test_extraction_loop_wrap_up_retries_then_succeeds() -> None:
    calls: list[int] = []

    def fake_send(_messages, **_kwargs):
        calls.append(len(calls))
        if len(calls) <= 2:
            return CLARIFYING
        if len(calls) == 3:
            return "Still thinking..."
        return COMPLETE

    record = run_record_extraction_loop(
        "Dropping Redis",
        resolve_data_paths(Path("/tmp/whyline-extract-retry")),
        prompt_user=lambda _q: "detail",
        send=fake_send,
    )

    assert record.decision == "Drop Redis for session storage"
    assert len(calls) == 4


def test_extraction_loop_detailed_returns_messages() -> None:
    result = run_record_extraction_loop_detailed(
        "Dropping Redis",
        resolve_data_paths(Path("/tmp/whyline-extract-5")),
        prompt_user=lambda _q: "ok",
        send=lambda _messages, **_kwargs: COMPLETE,
    )

    assert result.clarifying_rounds == 0
    assert len(result.messages) >= 2
