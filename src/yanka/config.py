from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

import yaml

from yanka.paths import DEFAULT_DATA_DIR, DataPaths, _expand

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Default chat model per ``llm.provider`` — fast/cheap tier (~gpt-4o-mini class).
DEFAULT_LLM_MODEL_BY_PROVIDER: dict[str, str] = {
    "claude": "claude-3-5-haiku-latest",
    "openai": "gpt-4o-mini",
    "google": "gemini-2.0-flash-lite",
    "ollama": "llama3.2:3b",
}

DEFAULT_LLM_MODEL = DEFAULT_LLM_MODEL_BY_PROVIDER["claude"]


@dataclass
class LlmConfig:
    provider: str = "claude"
    model: str = DEFAULT_LLM_MODEL
    endpoint: str | None = None


def default_model_for_provider(provider: str) -> str:
    """Return the default model string for a configured LLM provider."""
    key = provider.lower()
    try:
        return DEFAULT_LLM_MODEL_BY_PROVIDER[key]
    except KeyError as exc:
        known = ", ".join(sorted(DEFAULT_LLM_MODEL_BY_PROVIDER))
        msg = f"unknown LLM provider {provider!r}; known: {known}"
        raise ValueError(msg) from exc


def default_llm_config(provider: str = "claude") -> LlmConfig:
    """Build ``LlmConfig`` with the default model for the given provider."""
    key = provider.lower()
    return LlmConfig(
        provider=key,
        model=default_model_for_provider(key),
        endpoint=None,
    )


@dataclass
class EmbeddingConfig:
    provider: str = "local"
    model: str = DEFAULT_EMBEDDING_MODEL


@dataclass
class ExtractionConfig:
    max_rounds: int = 2
    conflict_search_limit: int = 10
    context_search_limit: int = 5
    # LanceDB L2 distance threshold for per-claim duplicate detection.
    # Lower = stricter. 0.15 matches near-identical claims only.
    duplicate_claim_max_distance: float = 0.15


@dataclass
class YankaConfig:
    llm: LlmConfig
    embedding: EmbeddingConfig
    extraction: ExtractionConfig
    data_dir: Path


def default_config(data_dir: Path | None = None) -> YankaConfig:
    root = _expand(data_dir if data_dir is not None else DEFAULT_DATA_DIR)
    return YankaConfig(
        llm=default_llm_config("openai"),
        embedding=EmbeddingConfig(),
        extraction=ExtractionConfig(),
        data_dir=root,
    )


def load_config(paths: DataPaths) -> YankaConfig:
    if not paths.config_path.is_file():
        return default_config(paths.data_dir)
    raw = yaml.safe_load(paths.config_path.read_text()) or {}
    if not isinstance(raw, dict):
        msg = f"Invalid config: expected mapping, got {type(raw).__name__}"
        raise ValueError(msg)
    return _config_from_dict(raw, fallback_data_dir=paths.data_dir)


def save_config(paths: DataPaths, config: YankaConfig) -> None:
    paths.config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _config_to_dict(config)
    paths.config_path.write_text(yaml.safe_dump(payload, sort_keys=False, default_flow_style=False))


def _config_from_dict(raw: dict[str, Any], fallback_data_dir: Path) -> YankaConfig:
    defaults = default_config(fallback_data_dir)
    data_dir_raw = raw.get("data_dir", defaults.data_dir)
    return YankaConfig(
        llm=_merge_dataclass(defaults.llm, raw.get("llm")),
        embedding=_merge_dataclass(defaults.embedding, raw.get("embedding")),
        extraction=_merge_dataclass(defaults.extraction, raw.get("extraction")),
        data_dir=_expand(data_dir_raw),
    )


def _config_to_dict(config: YankaConfig) -> dict[str, Any]:
    data = {
        "llm": asdict(config.llm),
        "embedding": asdict(config.embedding),
        "extraction": asdict(config.extraction),
        "data_dir": _format_path_for_yaml(config.data_dir),
    }
    if data["llm"]["endpoint"] is None:
        data["llm"]["endpoint"] = None
    return data


def _merge_dataclass[T](default: T, overrides: Any) -> T:
    if not overrides:
        return default
    if not isinstance(overrides, dict):
        kind = type(overrides).__name__
        msg = f"Invalid config section: expected mapping, got {kind}"
        raise ValueError(msg)
    values = {**asdict(default), **overrides}
    return type(default)(**{f.name: values[f.name] for f in fields(default)})


def format_config_display(paths: DataPaths) -> str:
    """Format effective config for ``/config`` (no secret values)."""
    from yanka.secrets import PROVIDER_ENV_VARS, get_api_key

    has_file = paths.config_path.is_file()
    config = load_config(paths) if has_file else default_config(paths.data_dir)
    lines: list[str] = []
    if has_file:
        lines.append(f"Config file: {paths.config_path}")
    else:
        lines.append("Config file: (none — defaults)")

    providers = sorted({config.llm.provider.lower(), *PROVIDER_ENV_VARS})
    for provider in providers:
        status = "set" if get_api_key(provider) else "not set"
        lines.append(f"api_key ({provider}): {status}")

    lines.append("")
    lines.append(
        yaml.safe_dump(
            _config_to_dict(config),
            sort_keys=False,
            default_flow_style=False,
        ).rstrip()
    )
    return "\n".join(lines)


def _format_path_for_yaml(path: Path) -> str:
    home = Path.home()
    try:
        relative = path.relative_to(home)
    except ValueError:
        return str(path)
    return f"~/{relative}" if relative.parts else str(path)
