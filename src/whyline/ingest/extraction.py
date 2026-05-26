"""Conversational record extraction — spec §7 step 2."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from whyline.config import EmbeddingConfig, LlmConfig, load_config
from whyline.ingest.context_search import (
    format_related_records_for_prompt,
    search_related_records,
)
from whyline.llm import get_prompt
from whyline.llm.client import LlmError, send_messages
from whyline.llm.json_parse import JsonParseError, fetch_typed_json, parse_llm_json
from whyline.llm.prompts import PromptName, format_extraction_record_return
from whyline.paths import DataPaths, resolve_data_paths
from whyline.records.json_schema import (
    RECORD_JSON_SCHEMA,
    record_from_json,
)
from whyline.records.models import Record

WRAP_UP_USER_MESSAGE = """\
CONVERSATION ENDED — no further user replies.

You already have enough information to write a useful record.
You MUST output ONLY one final JSON record now.
- Do not ask questions.
- Do not split this into multiple records.
- If the outcome is not final, use type: problem-statement and status: tentative.
- Use today's date: {today}.
- Include every required JSON key.
- Omit unknown optional arrays/body keys instead of adding [not discussed].
- NO questions. NO preamble. NO closing remarks. NO markdown.

{record_template}"""

FINAL_CLARIFYING_ROUND_NUDGE = """\
Final clarifying round: at most 2 brief questions in this message ONLY.
The next user message ends Q&A — after that you must output ONLY the record JSON."""


class RecordExtractionError(LlmError):
    """Record extraction did not produce a complete record after wrap-up."""

    def __init__(self, message: str, *, messages: list[dict[str, str]]) -> None:
        super().__init__(message)
        self.messages = messages
        self.last_assistant_response = ""
        for message_entry in reversed(messages):
            if message_entry.get("role") == "assistant":
                self.last_assistant_response = message_entry.get("content", "")
                break


@dataclass
class RecordExtractionResult:
    """Outcome of a successful extraction loop."""

    record: Record
    messages: list[dict[str, str]]
    clarifying_rounds: int


def build_record_extraction_conversation(
    raw_dump: str,
    paths: DataPaths | None = None,
    *,
    embedding_config: EmbeddingConfig | None = None,
) -> list[dict[str, str]]:
    """Build the initial message list (system + context + user dump)."""
    resolved = paths if paths is not None else resolve_data_paths()
    embed_config = _resolve_embedding_config(resolved, embedding_config)
    related = search_related_records(raw_dump, resolved, config=embed_config)
    context_block = format_related_records_for_prompt(related)
    return [
        {"role": "system", "content": get_prompt(PromptName.RECORD_EXTRACTION)},
        {"role": "user", "content": _initial_user_content(raw_dump, context_block)},
    ]


def run_record_extraction_loop(
    raw_dump: str,
    paths: DataPaths | None = None,
    *,
    prompt_user: Callable[[str], str],
    send: Callable[..., str] | None = None,
    config: LlmConfig | None = None,
) -> Record:
    """Run the extraction conversation until a complete record is produced."""
    result = run_record_extraction_loop_detailed(
        raw_dump,
        paths,
        prompt_user=prompt_user,
        send=send,
        config=config,
    )
    return result.record


def run_record_extraction_loop_detailed(
    raw_dump: str,
    paths: DataPaths | None = None,
    *,
    prompt_user: Callable[[str], str],
    send: Callable[..., str] | None = None,
    config: LlmConfig | None = None,
) -> RecordExtractionResult:
    """Run extraction and return the record plus conversation state."""
    resolved = paths if paths is not None else resolve_data_paths()
    llm_config = _resolve_llm_config(resolved, config)
    sender = send if send is not None else send_messages
    messages = build_record_extraction_conversation(raw_dump, resolved)
    max_rounds = _max_clarifying_rounds(resolved)

    for round_index in range(max_rounds):
        if round_index == 1:
            messages.append({"role": "user", "content": FINAL_CLARIFYING_ROUND_NUDGE})
        response = sender(messages, paths=resolved, config=llm_config)
        messages.append({"role": "assistant", "content": response})
        record = _parse_record_json_response(response)
        if record is not None:
            return RecordExtractionResult(
                record=record,
                messages=messages,
                clarifying_rounds=round_index,
            )
        user_reply = prompt_user(response)
        messages.append({"role": "user", "content": user_reply})
    clarifying_rounds = max_rounds

    record = _run_wrap_up(sender, messages, paths=resolved, config=llm_config)
    if record is not None:
        return RecordExtractionResult(
            record=record,
            messages=messages,
            clarifying_rounds=clarifying_rounds,
        )

    msg = "record extraction did not produce a complete record after wrap-up"
    raise RecordExtractionError(msg, messages=messages)


def _run_wrap_up(
    sender: Callable[..., str],
    messages: list[dict[str, str]],
    *,
    paths: DataPaths,
    config: LlmConfig | None,
) -> Record | None:
    """Force final JSON output and build a Record from validated data."""
    instruction = _format_wrap_up_instruction(WRAP_UP_USER_MESSAGE)
    messages.append({"role": "user", "content": instruction})
    try:
        return fetch_typed_json(
            messages,
            schema_name="whyline_record",
            schema=RECORD_JSON_SCHEMA,
            validate=record_from_json,
            expect="object",
            paths=paths,
            config=config,
            send=sender,
        )
    except LlmError:
        return None


def _format_wrap_up_instruction(template: str) -> str:
    return template.format(
        today=date.today().isoformat(),
        record_template=_record_return_format(),
    )


def _record_return_format() -> str:
    return format_extraction_record_return(date_value=date.today().isoformat())


def _parse_record_json_response(response: str) -> Record | None:
    try:
        payload = parse_llm_json(response, expect="object")
        return record_from_json(payload)
    except (JsonParseError, ValueError):
        return None


def _initial_user_content(raw_dump: str, context_block: str) -> str:
    if context_block.strip():
        return f"{context_block.rstrip()}\n\n---\n\nUser dump:\n{raw_dump.strip()}\n"
    return raw_dump.strip()


def _max_clarifying_rounds(paths: DataPaths) -> int:
    if paths.config_path.is_file():
        return load_config(paths).extraction.max_rounds
    from whyline.config import default_config

    return default_config(paths.data_dir).extraction.max_rounds


def _resolve_llm_config(
    paths: DataPaths,
    config: LlmConfig | None,
) -> LlmConfig | None:
    if config is not None:
        return config
    if paths.config_path.is_file():
        return load_config(paths).llm
    return None


def _resolve_embedding_config(
    paths: DataPaths,
    config: EmbeddingConfig | None,
) -> EmbeddingConfig | None:
    if config is not None:
        return config
    if paths.config_path.is_file():
        return load_config(paths).embedding
    return None
