from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whyline.llm import JsonParseError, fetch_llm_json, parse_llm_json

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
