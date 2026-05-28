from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from yanka.ingest.extraction import (
    FINAL_CLARIFYING_ROUND_NUDGE,
    RecordExtractionError,
    build_record_extraction_conversation,
    run_record_extraction_loop,
    run_record_extraction_loop_detailed,
    run_record_extraction_resume_loop_detailed,
)
from yanka.llm.prompts import (
    PromptName,
    format_extraction_record_return,
    get_prompt,
)
from yanka.paths import resolve_data_paths

FIXTURES = Path(__file__).parent / "fixtures" / "records"
CLARIFYING = (FIXTURES / "clarifying-questions.md").read_text(encoding="utf-8")

RECORD_JSON = {
    "date": "2026-05-26",
    "type": "problem-statement",
    "status": "tentative",
    "record_complete": True,
    "context_path": ["data-quality", "sampling", "standardization"],
    "people": ["Rudy"],
    "tags": ["sampling-rate", "data-quality"],
    "decision": "Standardize sampling-rate handling across DQ, Fix, and labeling.",
    "body": {
        "rationale": "100Hz is hardcoded and customer frequencies need support.",
        "implications": "Front-end, back-end, and timeseries library need changes.",
        "ownership": "Data scientists own quality; product functionality is ours.",
    },
}


def _record_json(**overrides) -> str:
    payload = {**RECORD_JSON, **overrides}
    return json.dumps(payload)


def test_build_record_extraction_conversation_includes_dump() -> None:
    messages = build_record_extraction_conversation(
        "We are dropping Redis",
        resolve_data_paths(Path("/tmp/yanka-empty-test")),
    )
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "We are dropping Redis" in messages[1]["content"]


def test_record_extraction_prompt_uses_canonical_json_format() -> None:
    prompt = get_prompt(PromptName.RECORD_EXTRACTION)
    canonical = format_extraction_record_return()

    assert canonical in prompt
    assert "Return ONLY one JSON object" in prompt
    assert "No markdown, no YAML, no prose" in prompt
    assert "record_complete" in prompt


def test_extraction_loop_qa_then_json_record() -> None:
    calls: list[list[dict[str, str]]] = []

    def fake_send(messages, **_kwargs):
        calls.append(list(messages))
        if len(calls) <= 2:
            return CLARIFYING
        return _record_json()

    prompt_user = MagicMock(side_effect=["answer one", "answer two"])

    record = run_record_extraction_loop(
        "Standardize sampling rates",
        resolve_data_paths(Path("/tmp/yanka-extract-json-1")),
        prompt_user=prompt_user,
        send=fake_send,
    )

    assert record.decision.startswith("Standardize sampling-rate")
    assert record.type.value == "problem-statement"
    assert record.status.value == "tentative"
    assert record.people == ["Rudy"]
    assert record.body.rationale is not None
    assert record.body.raw_input == "Standardize sampling rates"
    assert record.body.clarifying_exchange is not None
    assert "**Assistant:**" in record.body.clarifying_exchange
    assert "answer one" in record.body.clarifying_exchange
    assert "answer two" in record.body.clarifying_exchange
    assert FINAL_CLARIFYING_ROUND_NUDGE not in (record.body.clarifying_exchange or "")
    assert prompt_user.call_count == 2
    assert len(calls) == 3


def test_extraction_loop_two_clarifying_rounds_then_json_wrap_up() -> None:
    calls: list[list[dict[str, str]]] = []

    def fake_send(messages, **_kwargs):
        calls.append(list(messages))
        if len(calls) <= 2:
            return CLARIFYING
        return _record_json()

    record = run_record_extraction_loop(
        "Dropping Redis",
        resolve_data_paths(Path("/tmp/yanka-extract-json-2")),
        prompt_user=MagicMock(side_effect=["answer one", "answer two"]),
        send=fake_send,
    )

    assert record.record_complete is True
    round_two_user_texts = [m["content"] for m in calls[1] if m["role"] == "user"]
    assert FINAL_CLARIFYING_ROUND_NUDGE in round_two_user_texts
    wrap_up_users = [m["content"] for m in calls[2] if m["role"] == "user"]
    canonical = format_extraction_record_return(date_value=date.today().isoformat())
    assert any("CONVERSATION ENDED" in text for text in wrap_up_users)
    assert any(date.today().isoformat() in text for text in wrap_up_users)
    assert any(canonical in text for text in wrap_up_users)


def test_extraction_loop_retries_invalid_json_then_succeeds() -> None:
    calls: list[list[dict[str, str]]] = []

    def fake_send(messages, **_kwargs):
        calls.append(list(messages))
        if len(calls) <= 2:
            return CLARIFYING
        if len(calls) == 3:
            return json.dumps({**RECORD_JSON, "type": "not-a-real-type"})
        return _record_json()

    record = run_record_extraction_loop(
        "Standardize frequency handling",
        resolve_data_paths(Path("/tmp/yanka-extract-json-retry")),
        prompt_user=lambda _q: "details",
        send=fake_send,
    )

    assert record.decision.startswith("Standardize sampling-rate")
    assert len(calls) == 4
    retry_user_texts = [m["content"] for m in calls[3] if m["role"] == "user"]
    assert any("previous response did not validate" in text for text in retry_user_texts)


def test_extraction_loop_raises_after_failed_json_finalization() -> None:
    def always_invalid(_messages, **_kwargs):
        return CLARIFYING

    with pytest.raises(RecordExtractionError, match="wrap-up"):
        run_record_extraction_loop(
            "Dropping Redis",
            resolve_data_paths(Path("/tmp/yanka-extract-json-fail")),
            prompt_user=lambda _q: "answers",
            send=always_invalid,
        )


def test_extraction_loop_detailed_returns_messages() -> None:
    result = run_record_extraction_loop_detailed(
        "Dropping Redis",
        resolve_data_paths(Path("/tmp/yanka-extract-json-detailed")),
        prompt_user=lambda _q: "ok",
        send=lambda _messages, **_kwargs: _record_json(),
    )

    assert result.clarifying_rounds == 0
    assert len(result.messages) >= 3
    assert result.record.body.raw_input == "Dropping Redis"
    assert result.record.body.clarifying_exchange is None


def test_resume_extraction_continues_from_saved_messages() -> None:
    seeded = [
        {"role": "system", "content": get_prompt(PromptName.RECORD_EXTRACTION)},
        {"role": "user", "content": "User dump:\nDropping Redis"},
        {"role": "assistant", "content": CLARIFYING},
        {"role": "user", "content": "answer one"},
    ]
    calls: list[list[dict[str, str]]] = []

    def fake_send(messages, **_kwargs):
        calls.append(list(messages))
        return _record_json()

    result = run_record_extraction_resume_loop_detailed(
        "Dropping Redis",
        seeded,
        resolve_data_paths(Path("/tmp/yanka-extract-json-resume")),
        prompt_user=lambda _q: "answer two",
        send=fake_send,
    )

    assert result.record.record_complete is True
    assert calls
