"""Parse JSON from LLM assistant text — spec §12 malformed output."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from whyline.config import LlmConfig
from whyline.llm.client import LlmError, send_messages
from whyline.paths import DataPaths

ExpectJson = Literal["array", "object"] | None

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


class JsonParseError(LlmError):
    """LLM response text could not be parsed as JSON."""


def parse_llm_json(text: str, *, expect: ExpectJson = None) -> Any:
    """Parse JSON from raw LLM text (bare, fenced, or embedded)."""
    if not text or not text.strip():
        msg = "LLM response is empty"
        raise JsonParseError(msg)

    last_error: json.JSONDecodeError | None = None
    for candidate in _json_candidates(text):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        _validate_expect(value, expect)
        return value

    msg = "LLM response did not contain valid JSON"
    if last_error is not None:
        msg = f"{msg}: {last_error.msg}"
    raise JsonParseError(msg) from last_error


def fetch_llm_json(
    messages: list[dict[str, str]],
    *,
    expect: ExpectJson = None,
    max_attempts: int = 2,
    paths: DataPaths | None = None,
    config: LlmConfig | None = None,
) -> Any:
    """Send messages, parse JSON; retry same messages on parse failure."""
    if max_attempts < 1:
        msg = "max_attempts must be at least 1"
        raise ValueError(msg)

    last_error: JsonParseError | None = None
    for _ in range(max_attempts):
        raw = send_messages(messages, paths=paths, config=config)
        try:
            return parse_llm_json(raw, expect=expect)
        except JsonParseError as exc:
            last_error = exc

    assert last_error is not None
    raise last_error


def _validate_expect(value: Any, expect: ExpectJson) -> None:
    if expect is None:
        return
    if expect == "array" and not isinstance(value, list):
        msg = f"expected JSON array, got {type(value).__name__}"
        raise JsonParseError(msg)
    if expect == "object" and not isinstance(value, dict):
        msg = f"expected JSON object, got {type(value).__name__}"
        raise JsonParseError(msg)


def _json_candidates(text: str) -> list[str]:
    stripped = text.strip()
    candidates: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidates.append(normalized)

    add(stripped)
    for match in _FENCE_PATTERN.finditer(stripped):
        add(match.group(1))
    for opener in ("{", "["):
        index = stripped.find(opener)
        while index != -1:
            slice_text = _balanced_json_slice(stripped, index)
            if slice_text is not None:
                add(slice_text)
            index = stripped.find(opener, index + 1)
    return candidates


def _balanced_json_slice(text: str, start: int) -> str | None:
    opener = text[start]
    if opener not in "{[":
        return None
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None
