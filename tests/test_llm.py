from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from whyline.config import LlmConfig
from whyline.llm import LlmError, send_messages
from whyline.paths import ensure_data_layout, resolve_data_paths


def _fake_response(text: str = "assistant reply") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def _fake_tool_response(arguments: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(arguments=arguments)
                        )
                    ],
                )
            )
        ]
    )


def test_send_messages_returns_assistant_text() -> None:
    config = LlmConfig(provider="claude", model="claude-sonnet-4-20250514")
    messages = [{"role": "user", "content": "Say ok"}]
    mock_completion = MagicMock(return_value=_fake_response("ok"))

    with (
        patch("whyline.llm.client.get_api_key", return_value="sk-test"),
        patch("whyline.llm.client._call_litellm", mock_completion),
    ):
        result = send_messages(messages, config=config)

    assert result == "ok"
    mock_completion.assert_called_once()
    call_kwargs = mock_completion.call_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-sonnet-4-20250514"
    assert call_kwargs["messages"] == messages
    assert call_kwargs["api_key"] == "sk-test"


def test_send_messages_passes_response_format() -> None:
    config = LlmConfig(provider="openai", model="gpt-4o-mini")
    messages = [{"role": "user", "content": "Extract"}]
    response_format = {"type": "json_object"}
    mock_completion = MagicMock(return_value=_fake_response('{"ok": true}'))

    with (
        patch("whyline.llm.client.get_api_key", return_value="sk-test"),
        patch("whyline.llm.client._call_litellm", mock_completion),
    ):
        result = send_messages(
            messages,
            config=config,
            response_format=response_format,
        )

    assert result == '{"ok": true}'
    assert mock_completion.call_args.kwargs["response_format"] == response_format


def test_send_messages_returns_tool_arguments_when_content_empty() -> None:
    config = LlmConfig(provider="claude", model="claude-sonnet-4-20250514")
    mock_completion = MagicMock(return_value=_fake_tool_response('{"ok": true}'))

    with (
        patch("whyline.llm.client.get_api_key", return_value="sk-test"),
        patch("whyline.llm.client._call_litellm", mock_completion),
    ):
        result = send_messages([{"role": "user", "content": "Extract"}], config=config)

    assert result == '{"ok": true}'


def test_send_messages_ollama_uses_api_base_without_api_key() -> None:
    config = LlmConfig(provider="ollama", model="qwen3:8b", endpoint="http://127.0.0.1:11434")
    mock_completion = MagicMock(return_value=_fake_response())

    with (
        patch("whyline.llm.client.get_api_key") as mock_key,
        patch("whyline.llm.client._call_litellm", mock_completion),
    ):
        send_messages([{"role": "user", "content": "hi"}], config=config)

    mock_key.assert_not_called()
    assert mock_completion.call_args.kwargs["model"] == "ollama/qwen3:8b"
    assert mock_completion.call_args.kwargs["api_base"] == "http://127.0.0.1:11434"
    assert "api_key" not in mock_completion.call_args.kwargs


def test_send_messages_missing_api_key_raises() -> None:
    config = LlmConfig(provider="openai", model="gpt-4o")

    with (
        patch("whyline.llm.client.get_api_key", return_value=None),
        patch("whyline.llm.client._call_litellm") as mock_completion,
    ):
        with pytest.raises(LlmError, match="API key not configured"):
            send_messages([{"role": "user", "content": "hi"}], config=config)

    mock_completion.assert_not_called()


def test_send_messages_empty_messages_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        send_messages([], config=LlmConfig())


def test_send_messages_missing_litellm_raises() -> None:
    with patch(
        "whyline.llm.client._call_litellm",
        side_effect=LlmError('[llm] litellm is not installed'),
    ):
        with pytest.raises(LlmError, match=r"\[llm\] litellm is not installed"):
            send_messages(
                [{"role": "user", "content": "hi"}],
                config=LlmConfig(provider="ollama", model="qwen3:8b"),
            )


def test_call_litellm_missing_dependency() -> None:
    import builtins

    real_import = builtins.__import__

    def fail_import(name: str, *args: object, **kwargs: object):
        if name == "litellm":
            msg = "No module named 'litellm'"
            raise ImportError(msg)
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", fail_import):
        with pytest.raises(LlmError, match=r"\[llm\] litellm is not installed"):
            from whyline.llm.client import _call_litellm

            _call_litellm(model="ollama/qwen3:8b", messages=[])


def test_send_messages_loads_config_from_paths(tmp_path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    paths.config_path.write_text(
        "llm:\n  provider: openai\n  model: gpt-4o\n",
        encoding="utf-8",
    )
    mock_completion = MagicMock(return_value=_fake_response("loaded"))

    with (
        patch("whyline.llm.client.get_api_key", return_value="sk-openai"),
        patch("whyline.llm.client._call_litellm", mock_completion),
    ):
        send_messages([{"role": "user", "content": "hi"}], paths=paths)

    assert mock_completion.call_args.kwargs["model"] == "openai/gpt-4o"
