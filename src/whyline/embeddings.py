"""Text embedding abstraction — swappable backends via config."""

from __future__ import annotations

from collections.abc import Callable

from whyline.config import EmbeddingConfig, default_config

# Spec §5 / FastEmbed all-MiniLM-L6-v2
EMBEDDING_DIM = 384

type EmbedFn = Callable[[list[str], EmbeddingConfig], list[list[float]]]

_backends: dict[str, EmbedFn] = {}


class EmbeddingError(Exception):
    """Base error for embedding failures."""


class UnknownEmbeddingProvider(EmbeddingError):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(
            f"Unknown embedding provider {provider!r}. "
            f"Known providers: {known_embedding_providers() or '(none registered)'}"
        )


class EmbeddingDimensionError(EmbeddingError):
    def __init__(self, expected: int, got: int) -> None:
        self.expected = expected
        self.got = got
        super().__init__(f"Expected embedding dimension {expected}, got {got}")


def known_embedding_providers() -> list[str]:
    return sorted(_backends)


def register_embedding_backend(provider: str, fn: EmbedFn) -> None:
    """Register a backend. Used by production backends and tests."""
    _backends[provider] = fn


def unregister_embedding_backend(provider: str) -> None:
    _backends.pop(provider, None)


def clear_embedding_backends() -> None:
    """Clear all backends (tests only — prefer reset_embedding_backends)."""
    _backends.clear()


def reset_embedding_backends() -> None:
    """Clear registry and re-register built-in backends."""
    clear_embedding_backends()
    _register_builtin_backends()


def _register_builtin_backends() -> None:
    from whyline.embeddings_fastembed import register_fastembed_backend

    register_fastembed_backend()


_register_builtin_backends()


def embed(
    texts: list[str],
    *,
    config: EmbeddingConfig | None = None,
) -> list[list[float]]:
    """Embed texts using the configured provider. Returns one vector per input."""
    if not texts:
        return []

    cfg = config if config is not None else default_config().embedding
    backend = _backends.get(cfg.provider)
    if backend is None:
        raise UnknownEmbeddingProvider(cfg.provider)

    vectors = backend(texts, cfg)
    _validate_batch(vectors, len(texts))
    return vectors


def _validate_batch(vectors: list[list[float]], expected_count: int) -> None:
    if len(vectors) != expected_count:
        msg = f"Backend returned {len(vectors)} vectors for {expected_count} texts"
        raise EmbeddingError(msg)
    for row in vectors:
        if len(row) != EMBEDDING_DIM:
            raise EmbeddingDimensionError(EMBEDDING_DIM, len(row))
