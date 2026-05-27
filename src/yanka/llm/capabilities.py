"""Provider capability helpers for structured LLM output."""

from __future__ import annotations

from enum import StrEnum

from yanka.config import LlmConfig


class StructuredOutputMode(StrEnum):
    """Best structured-output mode to try for a configured model."""

    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"
    TEXT = "text"


def structured_output_modes(config: LlmConfig | None) -> list[StructuredOutputMode]:
    """Return preferred structured-output modes, from strongest to weakest.

    LiteLLM can translate OpenAI-style ``response_format`` for several
    providers, but model support varies. Keep the default conservative and let
    callers fall back cleanly when a provider rejects a stricter mode.
    """
    if config is None:
        return [StructuredOutputMode.TEXT]

    provider = config.provider.lower()
    model = config.model.lower()

    if provider == "openai":
        if _openai_supports_json_schema(model):
            return [
                StructuredOutputMode.JSON_SCHEMA,
                StructuredOutputMode.JSON_OBJECT,
                StructuredOutputMode.TEXT,
            ]
        return [StructuredOutputMode.JSON_OBJECT, StructuredOutputMode.TEXT]

    if provider == "claude":
        if _claude_supports_structured_output(model):
            return [
                StructuredOutputMode.JSON_SCHEMA,
                StructuredOutputMode.JSON_OBJECT,
                StructuredOutputMode.TEXT,
            ]
        return [StructuredOutputMode.TEXT]

    if provider == "google":
        if _gemini_supports_json_schema(model):
            return [
                StructuredOutputMode.JSON_SCHEMA,
                StructuredOutputMode.JSON_OBJECT,
                StructuredOutputMode.TEXT,
            ]
        return [StructuredOutputMode.JSON_OBJECT, StructuredOutputMode.TEXT]

    if provider == "ollama":
        return [StructuredOutputMode.JSON_OBJECT, StructuredOutputMode.TEXT]

    return [StructuredOutputMode.TEXT]


def response_format_for_mode(
    mode: StructuredOutputMode,
    *,
    schema_name: str,
    schema: dict,
) -> dict | None:
    """Build the OpenAI-compatible response_format LiteLLM accepts."""
    if mode is StructuredOutputMode.JSON_SCHEMA:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        }
    if mode is StructuredOutputMode.JSON_OBJECT:
        return {"type": "json_object"}
    return None


def _openai_supports_json_schema(model: str) -> bool:
    return any(
        marker in model
        for marker in (
            "gpt-4o",
            "gpt-4.1",
            "gpt-5",
            "o3",
            "o4",
        )
    )


def _claude_supports_structured_output(model: str) -> bool:
    return "claude-3" in model or "claude-sonnet-4" in model or "claude-opus-4" in model


def _gemini_supports_json_schema(model: str) -> bool:
    return "gemini-2" in model or "gemini-2.5" in model
