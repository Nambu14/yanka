"""API key storage: system keychain first, environment variables as fallback."""

from __future__ import annotations

import os

import keyring
import keyring.errors

KEYRING_SERVICE = "yanka"

# Provider id (config llm.provider) -> env vars tried in order
PROVIDER_ENV_VARS: dict[str, tuple[str, ...]] = {
    "claude": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "ollama": (),
}


def get_api_key(provider: str) -> str | None:
    """Return API key for provider, or None if not configured."""
    name = provider.lower()
    stored = _get_from_keyring(name)
    if stored:
        return stored
    return _get_from_env(name)


def set_api_key(provider: str, value: str) -> None:
    """Store API key in the system keychain (never in config.yaml)."""
    keyring.set_password(KEYRING_SERVICE, provider.lower(), value)


def delete_api_key(provider: str) -> None:
    """Remove API key from the system keychain."""
    try:
        keyring.delete_password(KEYRING_SERVICE, provider.lower())
    except keyring.errors.PasswordDeleteError:
        pass


def _get_from_keyring(provider: str) -> str | None:
    try:
        return keyring.get_password(KEYRING_SERVICE, provider)
    except Exception:
        return None


def _get_from_env(provider: str) -> str | None:
    for var in PROVIDER_ENV_VARS.get(provider, ()):
        value = os.environ.get(var)
        if value:
            return value
    return None
