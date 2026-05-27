"""Deterministic session transcript for saved records — spec body archive sections."""

from __future__ import annotations

from yanka.llm.json_parse import JsonParseError, parse_llm_json

FINAL_CLARIFYING_ROUND_NUDGE = """\
Final clarifying round: at most 2 brief questions in this message ONLY.
The next user message ends Q&A — after that you must output ONLY the record JSON."""
from yanka.records.json_schema import RecordJsonError, record_from_json
from yanka.records.models import Record

_WRAP_UP_MARKERS = ("CONVERSATION ENDED", "produce the record now")
_INJECTED_USER_PREFIXES = (
    "Return ONLY a JSON object named",
    "The previous response did not validate",
)


def apply_session_transcript(
    record: Record,
    raw_dump: str,
    messages: list[dict[str, str]],
) -> None:
    """Set Raw input and Clarifying exchange from the live session (not the LLM)."""
    record.body.raw_input = raw_dump.strip() or None
    record.body.clarifying_exchange = build_clarifying_exchange(messages)


def build_clarifying_exchange(messages: list[dict[str, str]]) -> str | None:
    """Format assistant/user clarifying rounds as markdown."""
    rounds: list[str] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.get("role") != "assistant":
            index += 1
            continue

        assistant_text = message.get("content", "")
        if _looks_like_record_json(assistant_text):
            index += 1
            continue

        user_index = index + 1
        while user_index < len(messages) and messages[user_index].get("role") != "user":
            user_index += 1
        if user_index >= len(messages):
            break

        user_text = messages[user_index].get("content", "")
        if _is_injected_user_message(user_text):
            index += 1
            continue

        rounds.append(_format_round(len(rounds) + 1, assistant_text, user_text))
        index = user_index + 1

    if not rounds:
        return None
    return "\n\n".join(rounds)


def _format_round(round_number: int, assistant: str, user: str) -> str:
    return (
        f"### Round {round_number}\n\n"
        f"**Assistant:**\n{assistant.strip()}\n\n"
        f"**User:**\n{user.strip()}"
    )


def _is_injected_user_message(content: str) -> bool:
    stripped = content.strip()
    if not stripped:
        return True
    if stripped == FINAL_CLARIFYING_ROUND_NUDGE.strip():
        return True
    if any(marker in stripped for marker in _WRAP_UP_MARKERS):
        return True
    return any(stripped.startswith(prefix) for prefix in _INJECTED_USER_PREFIXES)


def _looks_like_record_json(content: str) -> bool:
    try:
        payload = parse_llm_json(content, expect="object")
        record_from_json(payload)
    except (JsonParseError, RecordJsonError, ValueError):
        return False
    return True
