"""LiteLLM-backed LLM calls — spec §6 LLM abstraction."""

from __future__ import annotations

import logging
import os
from typing import Any

from yanka.config import LlmConfig, load_config
from yanka.paths import DataPaths, resolve_data_paths
from yanka.secrets import get_api_key

DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434"
DEFAULT_LLM_TIMEOUT_SECONDS = 45
_LLM_SEND_MAX_ATTEMPTS = 2

_PROVIDER_PREFIX = {
    "claude": "anthropic",
    "openai": "openai",
    "google": "gemini",
    "ollama": "ollama",
}

_litellm_module: Any | None = None
_litellm_import_env_applied = False


class LlmError(Exception):
    """LLM setup, configuration, or provider failures."""


class LlmAuthError(LlmError):
    """Authentication or missing API credentials."""


class LlmRateLimitError(LlmError):
    """Provider rate limit or quota exceeded."""


class LlmTimeoutError(LlmError):
    """Provider did not respond within the configured timeout."""


class LlmTransportError(LlmError):
    """Network or upstream availability failure (retryable)."""


_RETRYABLE_ERRORS = (LlmTransportError, LlmRateLimitError, LlmTimeoutError)


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

    last_error: LlmError | None = None
    for attempt in range(_LLM_SEND_MAX_ATTEMPTS):
        try:
            response = _call_litellm(**kwargs)
            return _extract_assistant_text(response)
        except _RETRYABLE_ERRORS as exc:
            last_error = exc
            if attempt + 1 < _LLM_SEND_MAX_ATTEMPTS:
                continue
            raise

    if last_error is not None:
        raise last_error
    msg = "LLM send failed without a classified error"
    raise LlmError(msg)


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
        "timeout": DEFAULT_LLM_TIMEOUT_SECONDS,
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
        raise LlmAuthError(msg)

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


def _ensure_litellm_import_env() -> None:
    """Apply env/logging defaults before the first ``import litellm``."""
    global _litellm_import_env_applied
    if _litellm_import_env_applied:
        return
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    logging.getLogger("LiteLLM").setLevel(logging.ERROR)
    _litellm_import_env_applied = True


def _get_litellm() -> Any:
    global _litellm_module
    if _litellm_module is not None:
        return _litellm_module

    _ensure_litellm_import_env()
    try:
        import litellm
    except ImportError as exc:
        msg = '[llm] litellm is not installed. Install with: pip install -e ".[llm]" or pip install -e ".[spike]"'
        raise LlmError(msg) from exc

    _configure_litellm_runtime(litellm)
    _litellm_module = litellm
    return litellm


def _call_litellm(**kwargs: Any) -> Any:
    litellm = _get_litellm()
    try:
        return litellm.completion(**kwargs)
    except Exception as exc:
        raise _classify_litellm_exception(exc) from exc


def _classify_litellm_exception(exc: Exception) -> LlmError:
    litellm_exc = _litellm_exception_types()
    if litellm_exc is not None:
        auth_errors = (
            litellm_exc.AuthenticationError,
            litellm_exc.PermissionDeniedError,
        )
        if isinstance(exc, auth_errors):
            return LlmAuthError(str(exc))

        if isinstance(exc, litellm_exc.RateLimitError):
            return LlmRateLimitError(str(exc))

        if isinstance(exc, litellm_exc.Timeout):
            return LlmTimeoutError(str(exc))

        transport_errors = (
            litellm_exc.APIConnectionError,
            litellm_exc.InternalServerError,
            litellm_exc.ServiceUnavailableError,
            litellm_exc.BadGatewayError,
        )
        if isinstance(exc, transport_errors):
            return LlmTransportError(str(exc))

    return _classify_litellm_exception_heuristic(exc)


def _litellm_exception_types() -> Any | None:
    try:
        from litellm import exceptions as litellm_exceptions
    except ImportError:
        return None
    return litellm_exceptions


def _classify_litellm_exception_heuristic(exc: Exception) -> LlmError:
    message = str(exc).lower()
    if "rate limit" in message or "rate_limit" in message or "429" in message:
        return LlmRateLimitError(str(exc))
    if "timeout" in message or "timed out" in message:
        return LlmTimeoutError(str(exc))
    if (
        "api key" in message
        or "authentication" in message
        or "unauthorized" in message
        or "401" in message
        or "403" in message
    ):
        return LlmAuthError(str(exc))
    if (
        "connection" in message
        or "connect" in message
        or "503" in message
        or "502" in message
        or "500" in message
        or "unavailable" in message
    ):
        return LlmTransportError(str(exc))
    return LlmError(str(exc))


def _configure_litellm_runtime(litellm: Any) -> None:
    """Reduce noisy provider warnings and feedback banners in REPL."""
    try:
        litellm.suppress_debug_info = True
    except Exception:
        pass
    logging.getLogger("LiteLLM").setLevel(logging.ERROR)


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
