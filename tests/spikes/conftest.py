"""Shared fixtures for Phase S dependency spikes."""

from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest


def ollama_available(base_url: str = "http://127.0.0.1:11434") -> bool:
    if os.environ.get("WHYLINE_RUN_SPIKES") != "1":
        return False
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def ollama_has_model(model: str, base_url: str = "http://127.0.0.1:11434") -> bool:
    if not ollama_available(base_url):
        return False
    import json

    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode())
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False
    names = {m.get("name", "") for m in data.get("models", [])}
    return model in names or any(n.startswith(f"{model}:") for n in names)


@pytest.fixture
def require_ollama_qwen() -> None:
    if not ollama_has_model("qwen3:8b"):
        pytest.skip(
            "Ollama with qwen3:8b not available; "
            "set WHYLINE_RUN_SPIKES=1 and start Ollama"
        )
