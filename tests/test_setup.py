from pathlib import Path

import pytest
import yaml

from yanka import secrets
from yanka.config import load_config
from yanka.paths import DATA_DIR_ENV_VAR, resolve_data_paths
from yanka.secrets import get_api_key
from yanka.setup import config_exists, run_first_run


@pytest.fixture
def mock_keyring(monkeypatch):
    store: dict[tuple[str, str], str] = {}

    def get_password(service: str, username: str) -> str | None:
        return store.get((service, username))

    def set_password(service: str, username: str, password: str) -> None:
        store[(service, username)] = password

    monkeypatch.setattr(secrets.keyring, "get_password", get_password)
    monkeypatch.setattr(secrets.keyring, "set_password", set_password)
    return store


def test_config_exists(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    assert not config_exists(paths)
    paths.config_path.write_text("llm:\n  provider: claude\n")
    assert config_exists(paths)


def test_run_first_run_writes_config_and_key(
    tmp_path: Path, monkeypatch, mock_keyring
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(tmp_path))
    bootstrap = resolve_data_paths()
    prompts = iter([str(tmp_path), "1", "sk-test-key"])

    def fake_prompt(*_args, **_kwargs):
        return next(prompts)

    paths, config = run_first_run(
        bootstrap=bootstrap,
        prompt_fn=fake_prompt,
        echo_fn=lambda _msg: None,
    )

    assert paths.data_dir == tmp_path.resolve()
    assert paths.records_dir.is_dir()
    assert config.llm.provider == "claude"
    assert get_api_key("claude") == "sk-test-key"

    loaded = load_config(paths)
    assert loaded.llm.provider == "claude"
    raw = yaml.safe_load(paths.config_path.read_text())
    assert raw["data_dir"] == str(tmp_path)


def test_run_first_run_skips_api_key_prompt_when_keyring_has_key(
    tmp_path: Path, monkeypatch, mock_keyring
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(tmp_path))
    mock_keyring[("yanka", "openai")] = "sk-from-keyring"
    bootstrap = resolve_data_paths()
    prompts = iter([str(tmp_path), "2"])
    prompt_calls: list[str] = []

    def fake_prompt(text: str, **_kwargs):
        prompt_calls.append(text)
        return next(prompts)

    paths, config = run_first_run(
        bootstrap=bootstrap,
        prompt_fn=fake_prompt,
        echo_fn=lambda _msg: None,
    )

    assert config.llm.provider == "openai"
    assert get_api_key("openai") == "sk-from-keyring"
    assert not any("API key" in call for call in prompt_calls)
    assert paths.config_path.is_file()


def test_run_first_run_allows_empty_api_key_when_env_set(
    tmp_path: Path, monkeypatch, mock_keyring
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    bootstrap = resolve_data_paths()
    prompts = iter([str(tmp_path), "2", ""])

    paths, config = run_first_run(
        bootstrap=bootstrap,
        prompt_fn=lambda *_a, **_k: next(prompts),
        echo_fn=lambda _msg: None,
    )

    assert config.llm.provider == "openai"
    assert get_api_key("openai") == "sk-env"
    assert paths.config_path.is_file()


def test_run_first_run_skips_api_key_for_ollama(
    tmp_path: Path, monkeypatch, mock_keyring
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(tmp_path))
    bootstrap = resolve_data_paths()
    prompts = iter([str(tmp_path), "4"])

    paths, config = run_first_run(
        bootstrap=bootstrap,
        prompt_fn=lambda *_a, **_k: next(prompts),
        echo_fn=lambda _msg: None,
    )

    assert config.llm.provider == "ollama"
    assert get_api_key("ollama") is None


def test_cli_runs_first_setup_when_no_config(
    tmp_path: Path, monkeypatch, mock_keyring
) -> None:
    from click.testing import CliRunner

    from yanka.cli import main

    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(tmp_path))
    prompts = iter([str(tmp_path), "2", "sk-openai"])

    monkeypatch.setattr(
        "yanka.setup.click.prompt",
        lambda *_a, **_k: next(prompts),
    )
    monkeypatch.setattr("yanka.setup.click.echo", lambda _msg: None)

    result = CliRunner().invoke(main, [])

    assert result.exit_code == 0
    config_path = tmp_path / "config.yaml"
    assert config_path.is_file()
    assert yaml.safe_load(config_path.read_text())["llm"]["provider"] == "openai"
    assert get_api_key("openai") == "sk-openai"
