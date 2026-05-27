"""Local embeddings via FastEmbed (ONNX, spec default: all-MiniLM-L6-v2)."""

from __future__ import annotations

from yanka.config import EmbeddingConfig
from yanka.embeddings import (
    EmbeddingError,
    register_embedding_backend,
)

LOCAL_PROVIDER = "local"

_models: dict[str, object] = {}


def register_fastembed_backend() -> None:
    register_embedding_backend(LOCAL_PROVIDER, _fastembed_local)


def _fastembed_local(texts: list[str], config: EmbeddingConfig) -> list[list[float]]:
    if config.provider != LOCAL_PROVIDER:
        msg = f"FastEmbed backend called with provider {config.provider!r}"
        raise EmbeddingError(msg)

    model = _get_text_embedding(config.model)
    return [vector.tolist() for vector in model.embed(texts)]


def _get_text_embedding(model_name: str):
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        msg = (
            "fastembed is not installed. "
            'Install with: pip install -e ".[embedding]"'
        )
        raise EmbeddingError(msg) from exc

    if model_name not in _models:
        _models[model_name] = TextEmbedding(model_name=model_name)
    return _models[model_name]


def clear_fastembed_cache() -> None:
    """Drop cached models (tests only)."""
    _models.clear()
