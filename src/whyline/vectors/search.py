"""Vector search with metadata filters."""

from __future__ import annotations

from typing import Any

import numpy as np

from whyline.config import EmbeddingConfig, default_config, load_config
from whyline.embeddings import embed
from whyline.paths import DataPaths, resolve_data_paths
from whyline.vectors.claims import get_claims_table
from whyline.vectors.filters import VectorSearchFilters, build_where_clause
from whyline.vectors.records import get_records_table

DEFAULT_SEARCH_LIMIT = 10


def search_records(
    query: str | list[float],
    paths: DataPaths | None = None,
    *,
    filters: VectorSearchFilters | None = None,
    limit: int | None = None,
    config: EmbeddingConfig | None = None,
) -> list[dict[str, Any]]:
    """Semantic search on the records table with optional metadata filters."""
    resolved = paths if paths is not None else resolve_data_paths()
    table = get_records_table(resolved)
    vector = _query_vector(query, config=config)
    max_results = _resolve_limit(resolved, limit)
    return _vector_search(table, vector, build_where_clause(filters), max_results)


def search_claims(
    query: str | list[float],
    paths: DataPaths | None = None,
    *,
    filters: VectorSearchFilters | None = None,
    limit: int | None = None,
    config: EmbeddingConfig | None = None,
) -> list[dict[str, Any]]:
    """Semantic search on the claims table with optional metadata filters."""
    resolved = paths if paths is not None else resolve_data_paths()
    table = get_claims_table(resolved)
    vector = _query_vector(query, config=config)
    max_results = _resolve_limit(resolved, limit)
    return _vector_search(table, vector, build_where_clause(filters), max_results)


def _query_vector(
    query: str | list[float],
    *,
    config: EmbeddingConfig | None,
) -> np.ndarray:
    if isinstance(query, str):
        vector = embed([query], config=config)[0]
    else:
        vector = query
    return np.asarray(vector, dtype=np.float32)


def _resolve_limit(paths: DataPaths, limit: int | None) -> int:
    if limit is not None:
        return limit
    if paths.config_path.is_file():
        return load_config(paths).extraction.conflict_search_limit
    return default_config(paths.data_dir).extraction.conflict_search_limit


def _vector_search(
    table: Any,
    vector: np.ndarray,
    where: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    builder = table.search(vector)
    if where is not None:
        builder = builder.where(where)
    return builder.limit(limit).to_list()
