"""S.3 — LiteLLM: import smoke + optional Ollama completion."""

from __future__ import annotations

import pytest

litellm = pytest.importorskip("litellm")


def test_litellm_import() -> None:
    assert hasattr(litellm, "completion")


def test_litellm_ollama_qwen3_completion(require_ollama_qwen) -> None:
    # Qwen3 defaults to "thinking" mode; Ollama returns content in `thinking`, not
    # `message`, unless think is disabled — see tests/spikes/README.md.
    response = litellm.completion(
        model="ollama/qwen3:8b",
        api_base="http://127.0.0.1:11434",
        messages=[{"role": "user", "content": "Reply with exactly: ok"}],
        max_tokens=32,
        extra_body={"think": False},
    )
    content = response.choices[0].message.content
    assert content
    assert isinstance(content, str)
