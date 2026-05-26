"""LiteLLM-backed LLM calls — spec §6 LLM abstraction."""

from __future__ import annotations

from typing import Any

from whyline.config import LlmConfig, load_config
from whyline.paths import DataPaths, resolve_data_paths
from whyline.secrets import get_api_key

DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434"

_PROVIDER_PREFIX = {
    "claude": "anthropic",
    "openai": "openai",
    "google": "gemini",
    "ollama": "ollama",
}


class LlmError(Exception):
    """LLM setup, configuration, or provider failures."""


def send_messages(
    messages: list[dict[str, str]],
    *,
    paths: DataPaths | None = None,
    config: LlmConfig | None = None,
    response_format: dict | None = None,
) -> str:
    """Send a message list to the configured LLM and return assistant text."""
    if not messages:
        msg = "messages must not be empty"
        raise ValueError(msg)

    resolved = paths if paths is not None else resolve_data_paths()
    llm_config = config if config is not None else load_config(resolved).llm
    kwargs = _build_completion_kwargs(
        llm_config,
        messages,
        response_format=response_format,
    )
    response = _call_litellm(**kwargs)
    return _extract_assistant_text(response)


def _build_completion_kwargs(
    config: LlmConfig,
    messages: list[dict[str, str]],
    *,
    response_format: dict | None = None,
) -> dict[str, Any]:
    provider = config.provider.lower()
    kwargs: dict[str, Any] = {
        "model": _litellm_model(provider, config.model),
        "messages": messages,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    if provider == "ollama":
        kwargs["api_base"] = config.endpoint or DEFAULT_OLLAMA_BASE
        return kwargs

    api_key = get_api_key(provider)
    if not api_key:
        msg = (
            f"API key not configured for LLM provider {provider!r}. "
            "Set via first-run wizard, keyring, or environment variables."
        )
        raise LlmError(msg)

    kwargs["api_key"] = api_key
    if config.endpoint:
        kwargs["api_base"] = config.endpoint
    return kwargs


def _litellm_model(provider: str, model: str) -> str:
    if "/" in model:
        return model
    prefix = _PROVIDER_PREFIX.get(provider)
    if prefix is None:
        return model
    return f"{prefix}/{model}"


def _call_litellm(**kwargs: Any) -> Any:
    try:
        import litellm
    except ImportError as exc:
        msg = (
            "[llm] litellm is not installed. "
            'Install with: pip install -e ".[llm]" or pip install -e ".[spike]"'
        )
        raise LlmError(msg) from exc
    return litellm.completion(**kwargs)


def _extract_assistant_text(response: Any) -> str:
    try:
        message = response.choices[0].message
        content = message.content
    except (AttributeError, IndexError, TypeError) as exc:
        msg = "LLM response did not contain assistant message content"
        raise LlmError(msg) from exc

    if content and isinstance(content, str):
        return content

    tool_arguments = _extract_tool_arguments(message)
    if tool_arguments is not None:
        return tool_arguments

    if not content or not isinstance(content, str):
        msg = "LLM returned empty assistant message content"
        raise LlmError(msg)
    return content


def _extract_tool_arguments(message: Any) -> str | None:
    tool_calls = getattr(message, "tool_calls", None)
    if not tool_calls:
        return None
    try:
        arguments = tool_calls[0].function.arguments
    except (AttributeError, IndexError, TypeError):
        return None
    if isinstance(arguments, str) and arguments.strip():
        return arguments
    return None
