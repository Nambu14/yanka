import keyring.errors
import pytest

from yanka import secrets


@pytest.fixture
def mock_keyring(monkeypatch):
    store: dict[tuple[str, str], str] = {}

    def get_password(service: str, username: str) -> str | None:
        return store.get((service, username))

    def set_password(service: str, username: str, password: str) -> None:
        store[(service, username)] = password

    def delete_password(service: str, username: str) -> None:
        key = (service, username)
        if key not in store:
            raise keyring.errors.PasswordDeleteError("not found")
        del store[key]

    monkeypatch.setattr(secrets.keyring, "get_password", get_password)
    monkeypatch.setattr(secrets.keyring, "set_password", set_password)
    monkeypatch.setattr(secrets.keyring, "delete_password", delete_password)
    return store


def test_set_and_get_from_keyring(mock_keyring) -> None:
    secrets.set_api_key("claude", "sk-keyring")
    assert secrets.get_api_key("claude") == "sk-keyring"


def test_keyring_takes_precedence_over_env(mock_keyring, monkeypatch) -> None:
    secrets.set_api_key("openai", "sk-keyring")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    assert secrets.get_api_key("openai") == "sk-keyring"


def test_env_fallback_when_keyring_empty(mock_keyring, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    assert secrets.get_api_key("claude") == "sk-env"


def test_google_tries_gemini_then_google_env(mock_keyring, monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-env")
    assert secrets.get_api_key("google") == "google-env"


def test_ollama_returns_none(mock_keyring, monkeypatch) -> None:
    assert secrets.get_api_key("ollama") is None


def test_unknown_provider_returns_none(mock_keyring) -> None:
    assert secrets.get_api_key("unknown") is None


def test_delete_api_key(mock_keyring) -> None:
    secrets.set_api_key("claude", "sk-keyring")
    secrets.delete_api_key("claude")
    assert secrets.get_api_key("claude") is None


def test_keyring_error_falls_back_to_env(mock_keyring, monkeypatch) -> None:
    def fail_get(*_args, **_kwargs):
        raise RuntimeError("keychain unavailable")

    monkeypatch.setattr(secrets.keyring, "get_password", fail_get)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    assert secrets.get_api_key("claude") == "sk-env"
