from pathlib import Path

import pytest
import yaml

from yanka.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL_BY_PROVIDER,
    default_config,
    default_llm_config,
    default_model_for_provider,
    load_config,
    save_config,
)
from yanka.paths import resolve_data_paths


def test_default_model_for_provider() -> None:
    assert default_model_for_provider("openai") == DEFAULT_LLM_MODEL_BY_PROVIDER["openai"]
    assert default_llm_config("google").model == DEFAULT_LLM_MODEL_BY_PROVIDER["google"]


def test_default_config_values() -> None:
    config = default_config()
    assert config.llm.provider == "openai"
    assert config.llm.model == DEFAULT_LLM_MODEL_BY_PROVIDER["openai"]
    assert config.llm.endpoint is None
    assert config.embedding.provider == "local"
    assert config.embedding.model == DEFAULT_EMBEDDING_MODEL
    assert config.extraction.max_rounds == 2
    assert config.extraction.conflict_search_limit == 10
    assert config.extraction.context_search_limit == 5
    assert config.extraction.duplicate_claim_max_distance == 0.15


def test_load_config_missing_file_uses_defaults(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    config = load_config(paths)
    assert config.data_dir == tmp_path.resolve()
    assert config.llm.provider == "openai"


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    original = default_config(tmp_path)
    original.llm.provider = "openai"
    original.llm.model = "gpt-4o"
    original.extraction.max_rounds = 4

    save_config(paths, original)
    loaded = load_config(paths)

    assert loaded.llm.provider == "openai"
    assert loaded.llm.model == "gpt-4o"
    assert loaded.extraction.max_rounds == 4
    assert loaded.data_dir == tmp_path.resolve()


def test_load_config_merges_partial_yaml(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    paths.config_path.write_text("llm:\n  provider: ollama\n")

    config = load_config(paths)

    assert config.llm.provider == "ollama"
    # Model is not overridden in YAML → keeps the default-config model.
    assert config.llm.model == DEFAULT_LLM_MODEL_BY_PROVIDER["openai"]
    assert config.embedding.model == DEFAULT_EMBEDDING_MODEL


def test_resolve_data_paths_uses_config_data_dir(tmp_path: Path, monkeypatch) -> None:
    bootstrap = tmp_path / "bootstrap"
    target = tmp_path / "storage"
    bootstrap.mkdir()
    (bootstrap / "config.yaml").write_text(yaml.safe_dump({"data_dir": str(target)}))
    monkeypatch.setenv("YANKA_DATA_DIR", str(bootstrap))

    paths = resolve_data_paths()

    assert paths.data_dir == target.resolve()
    assert paths.records_dir == target / "records"


def test_explicit_data_dir_overrides_config(tmp_path: Path) -> None:
    bootstrap = tmp_path / "bootstrap"
    explicit = tmp_path / "explicit"
    bootstrap.mkdir()
    (bootstrap / "config.yaml").write_text(yaml.safe_dump({"data_dir": str(tmp_path / "from-config")}))

    paths = resolve_data_paths(explicit)

    assert paths.data_dir == explicit.resolve()


def test_load_config_rejects_invalid_yaml(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    paths.config_path.write_text("not a mapping\n")

    with pytest.raises(ValueError, match="expected mapping"):
        load_config(paths)
