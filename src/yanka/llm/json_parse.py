"""Parse JSON from LLM assistant text — spec §12 malformed output."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Literal

from yanka.config import LlmConfig
from yanka.llm.capabilities import (
    StructuredOutputMode,
    response_format_for_mode,
    structured_output_modes,
)
from yanka.llm.client import LlmError, send_messages
from yanka.paths import DataPaths

ExpectJson = Literal["array", "object"] | None

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


class JsonParseError(LlmError):
    """LLM response text could not be parsed as JSON."""


class JsonValidationError(JsonParseError):
    """Parsed JSON did not satisfy the expected application schema."""


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


def fetch_typed_json[T](
    messages: list[dict[str, str]],
    *,
    schema_name: str,
    schema: dict,
    validate: Callable[[Any], T],
    expect: ExpectJson = "object",
    max_attempts: int = 2,
    paths: DataPaths | None = None,
    config: LlmConfig | None = None,
    send: Callable[..., str] | None = None,
) -> T:
    """Fetch JSON using strongest available provider mode, then validate."""
    if max_attempts < 1:
        msg = "max_attempts must be at least 1"
        raise ValueError(msg)

    sender = send if send is not None else send_messages
    last_error: LlmError | None = None
    modes = structured_output_modes(config)
    for mode in modes:
        response_format = response_format_for_mode(
            mode,
            schema_name=schema_name,
            schema=schema,
        )
        mode_messages = _messages_for_mode(messages, mode, schema_name, schema)
        for attempt_index in range(max_attempts):
            attempt_messages = _retry_messages(mode_messages, last_error)
            try:
                raw = sender(
                    attempt_messages,
                    paths=paths,
                    config=config,
                    response_format=response_format,
                )
                parsed = parse_llm_json(raw, expect=expect)
                return validate(parsed)
            except JsonParseError as exc:
                last_error = exc
                continue
            except ValueError as exc:
                last_error = JsonValidationError(str(exc))
                continue
            except LlmError as exc:
                last_error = exc
                if mode is StructuredOutputMode.TEXT:
                    raise
                break
            except Exception as exc:
                last_error = LlmError(str(exc))
                if mode is StructuredOutputMode.TEXT:
                    raise last_error from exc
                break

    if last_error is not None:
        raise last_error
    msg = "LLM response did not produce valid typed JSON"
    raise JsonValidationError(msg)


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


def _messages_for_mode(
    messages: list[dict[str, str]],
    mode: StructuredOutputMode,
    schema_name: str,
    schema: dict,
) -> list[dict[str, str]]:
    if mode is StructuredOutputMode.JSON_SCHEMA:
        return messages
    schema_text = json.dumps(schema, sort_keys=True)
    suffix = (
        f"Return ONLY a JSON object named {schema_name} matching this schema. "
        f"No prose, no markdown fences.\nSchema:\n{schema_text}"
    )
    return [*messages, {"role": "user", "content": suffix}]


def _retry_messages(
    messages: list[dict[str, str]],
    error: LlmError | None,
) -> list[dict[str, str]]:
    if error is None:
        return messages
    return [
        *messages,
        {
            "role": "user",
            "content": (f"The previous response did not validate. Fix the JSON only. Error: {error}"),
        },
    ]


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
