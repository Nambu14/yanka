from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whyline.config import LlmConfig
from whyline.llm import (
    JsonParseError,
    LlmError,
    fetch_llm_json,
    fetch_typed_json,
    parse_llm_json,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "llm_json"


def _fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_parse_bare_object_fixture() -> None:
    data = parse_llm_json(_fixture("bare-object.txt"), expect="object")
    assert data == {"conflicts": []}


def test_parse_fenced_array_fixture() -> None:
    data = parse_llm_json(_fixture("fenced-array.txt"), expect="array")
    assert len(data) == 1
    assert data[0]["id"] == "c1"


def test_parse_preamble_fence_fixture() -> None:
    data = parse_llm_json(_fixture("preamble-fence.txt"), expect="object")
    assert data["query_type"] == "exploratory"


def test_parse_preamble_bare_object_fixture() -> None:
    data = parse_llm_json(_fixture("preamble-bare.txt"), expect="object")
    assert len(data["conflicts"]) == 1


def test_parse_malformed_fixture_raises() -> None:
    with pytest.raises(JsonParseError, match="did not contain valid JSON"):
        parse_llm_json(_fixture("malformed.txt"))


def test_parse_empty_raises() -> None:
    with pytest.raises(JsonParseError, match="empty"):
        parse_llm_json("   ")


def test_expect_array_rejects_object() -> None:
    with pytest.raises(JsonParseError, match="expected JSON array"):
        parse_llm_json('{"conflicts": []}', expect="array")


def test_expect_object_rejects_array() -> None:
    with pytest.raises(JsonParseError, match="expected JSON object"):
        parse_llm_json("[]", expect="object")


def test_fetch_llm_json_retries_on_parse_failure() -> None:
    messages = [{"role": "user", "content": "extract"}]
    mock_send = MagicMock(
        side_effect=[
            "not json",
            _fixture("bare-object.txt"),
        ]
    )

    with patch("whyline.llm.json_parse.send_messages", mock_send):
        data = fetch_llm_json(messages, expect="object", max_attempts=2)

    assert data == {"conflicts": []}
    assert mock_send.call_count == 2
    assert mock_send.call_args_list[0].kwargs == mock_send.call_args_list[1].kwargs


def test_fetch_llm_json_raises_after_exhausted_attempts() -> None:
    messages = [{"role": "user", "content": "extract"}]
    mock_send = MagicMock(return_value="still not json")

    with (
        patch("whyline.llm.json_parse.send_messages", mock_send),
        pytest.raises(JsonParseError),
    ):
        fetch_llm_json(messages, max_attempts=2)

    assert mock_send.call_count == 2


def test_fetch_llm_json_succeeds_on_first_attempt() -> None:
    messages = [{"role": "user", "content": "extract"}]
    mock_send = MagicMock(return_value=_fixture("bare-object.txt"))

    with patch("whyline.llm.json_parse.send_messages", mock_send):
        data = fetch_llm_json(messages, expect="object")

    assert data == {"conflicts": []}
    mock_send.assert_called_once()


def test_fetch_typed_json_uses_strict_schema_when_supported() -> None:
    calls = []

    def fake_send(_messages, **kwargs):
        calls.append(kwargs)
        return '{"name": "Rudy"}'

    data = fetch_typed_json(
        [{"role": "user", "content": "extract"}],
        schema_name="person",
        schema={"type": "object", "properties": {"name": {"type": "string"}}},
        validate=lambda payload: payload,
        config=LlmConfig(provider="openai", model="gpt-4o-mini"),
        send=fake_send,
    )

    assert data == {"name": "Rudy"}
    assert calls[0]["response_format"]["type"] == "json_schema"


def test_fetch_typed_json_falls_back_to_json_object_mode() -> None:
    calls = []

    def fake_send(_messages, **kwargs):
        calls.append(kwargs)
        if kwargs["response_format"]["type"] == "json_schema":
            raise LlmError("schema unsupported")
        return '{"name": "Rudy"}'

    data = fetch_typed_json(
        [{"role": "user", "content": "extract"}],
        schema_name="person",
        schema={"type": "object", "properties": {"name": {"type": "string"}}},
        validate=lambda payload: payload,
        config=LlmConfig(provider="openai", model="gpt-4o-mini"),
        send=fake_send,
    )

    assert data == {"name": "Rudy"}
    assert [call["response_format"]["type"] for call in calls] == [
        "json_schema",
        "json_object",
    ]


def test_fetch_typed_json_retries_validation_errors() -> None:
    calls = []

    def validate(payload):
        if "name" not in payload:
            raise ValueError("missing name")
        return payload

    def fake_send(messages, **kwargs):
        calls.append((messages, kwargs))
        if len(calls) == 1:
            return '{"bad": true}'
        return '{"name": "Rudy"}'

    data = fetch_typed_json(
        [{"role": "user", "content": "extract"}],
        schema_name="person",
        schema={"type": "object", "properties": {"name": {"type": "string"}}},
        validate=validate,
        config=LlmConfig(provider="ollama", model="qwen3:8b"),
        send=fake_send,
    )

    assert data == {"name": "Rudy"}
    retry_messages = calls[1][0]
    assert "previous response did not validate" in retry_messages[-1]["content"]
