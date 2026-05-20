from __future__ import annotations

import pytest

from whyline.config import DEFAULT_EMBEDDING_MODEL, EmbeddingConfig
from whyline.embeddings import (
    EMBEDDING_DIM,
    EmbeddingDimensionError,
    EmbeddingError,
    UnknownEmbeddingProvider,
    embed,
    known_embedding_providers,
    register_embedding_backend,
    reset_embedding_backends,
    unregister_embedding_backend,
)
from whyline.embeddings_fastembed import clear_fastembed_cache


def _fake_backend(texts: list[str], _config: EmbeddingConfig) -> list[list[float]]:
    return [[float(i)] * EMBEDDING_DIM for i, _ in enumerate(texts)]


@pytest.fixture(autouse=True)
def _isolated_backends() -> None:
    reset_embedding_backends()
    clear_fastembed_cache()
    yield
    reset_embedding_backends()
    clear_fastembed_cache()


def test_embed_empty_list() -> None:
    assert embed([]) == []


def test_embed_delegates_to_registered_backend() -> None:
    register_embedding_backend("test", _fake_backend)
    config = EmbeddingConfig(provider="test", model="fake")

    result = embed(["alpha", "beta"], config=config)

    assert len(result) == 2
    assert len(result[0]) == EMBEDDING_DIM
    assert result[0][0] == 0.0
    assert result[1][0] == 1.0


def test_embed_unknown_provider() -> None:
    config = EmbeddingConfig(provider="missing", model="x")

    with pytest.raises(UnknownEmbeddingProvider, match="missing"):
        embed(["hello"], config=config)


def test_embed_wrong_vector_count() -> None:
    def bad_count(_texts: list[str], _config: EmbeddingConfig) -> list[list[float]]:
        return [[0.0] * EMBEDDING_DIM]

    register_embedding_backend("bad-count", bad_count)

    with pytest.raises(EmbeddingError, match="1 vectors for 2"):
        embed(["a", "b"], config=EmbeddingConfig(provider="bad-count"))


def test_embed_wrong_dimension() -> None:
    def bad_dim(_texts: list[str], _config: EmbeddingConfig) -> list[list[float]]:
        return [[0.0, 1.0]]

    register_embedding_backend("bad-dim", bad_dim)

    with pytest.raises(EmbeddingDimensionError, match="384"):
        embed(["a"], config=EmbeddingConfig(provider="bad-dim"))


def test_register_and_unregister_backend() -> None:
    register_embedding_backend("test", _fake_backend)
    assert known_embedding_providers() == ["local", "test"]
    unregister_embedding_backend("test")
    assert known_embedding_providers() == ["local"]


def test_local_provider_registered() -> None:
    assert "local" in known_embedding_providers()


@pytest.mark.embedding
def test_fastembed_local_produces_384_dimensions() -> None:
    pytest.importorskip("fastembed")

    vectors = embed(["hello world"])

    assert len(vectors) == 1
    assert len(vectors[0]) == EMBEDDING_DIM


@pytest.mark.embedding
def test_fastembed_uses_config_model() -> None:
    pytest.importorskip("fastembed")

    config = EmbeddingConfig(
        provider="local",
        model=DEFAULT_EMBEDDING_MODEL,
    )
    vectors = embed(["token"], config=config)

    assert len(vectors[0]) == EMBEDDING_DIM
