"""Vector retrieval step for the retrieval pipeline — spec §8 step 2."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from whyline.config import EmbeddingConfig, default_config, load_config
from whyline.paths import DataPaths, resolve_data_paths
from whyline.retrieval.query_analysis import QueryAnalysis
from whyline.retrieval_enums import RetrievalSource
from whyline.vectors.retrieve import (
    VectorRetrieveParams,
    retrieval_search_query,
    should_skip_vector_retrieval,
    vector_filters_for_params,
    vector_hit_date,
    vector_hit_score,
)
from whyline.vectors.search import search_records

type SearchRecordsFn = Callable[..., list[dict[str, Any]]]


@dataclass(frozen=True)
class VectorRetrievalHit:
    """A record surfaced from LanceDB vector retrieval."""

    file_reference: str
    date: date
    status: str
    summary: str
    context_path: str
    score: float | None
    source: RetrievalSource = RetrievalSource.VECTOR


def retrieve_from_vector(
    analysis: QueryAnalysis,
    paths: DataPaths | None = None,
    *,
    limit: int | None = None,
    config: EmbeddingConfig | None = None,
    search_records_fn: SearchRecordsFn | None = None,
) -> list[VectorRetrievalHit]:
    """Run semantic record search with filters derived from query analysis."""
    params = _to_vector_params(analysis)
    if should_skip_vector_retrieval(params):
        return []

    query = retrieval_search_query(params)
    if not query:
        return []

    resolved = paths if paths is not None else resolve_data_paths()
    max_results = _resolve_vector_search_limit(resolved, limit)
    search = search_records_fn or search_records
    rows = search(
        query,
        resolved,
        filters=vector_filters_for_params(params),
        limit=max_results,
        config=config,
    )
    return [_hit_from_row(row) for row in rows]


def _hit_from_row(row: dict[str, Any]) -> VectorRetrievalHit:
    summary = row.get("summary")
    if not isinstance(summary, str):
        summary = ""
    context_path = row.get("context_path")
    if not isinstance(context_path, str):
        context_path = ""
    file_reference = row.get("file_reference")
    if not isinstance(file_reference, str):
        msg = "vector hit missing file_reference"
        raise ValueError(msg)
    status = row.get("status")
    if not isinstance(status, str):
        status = ""

    return VectorRetrievalHit(
        file_reference=file_reference,
        date=vector_hit_date(row),
        status=status,
        summary=summary,
        context_path=context_path,
        score=vector_hit_score(row),
    )


def _to_vector_params(analysis: QueryAnalysis) -> VectorRetrieveParams:
    filters = analysis.filters
    status = filters.status_filter.value if filters.status_filter is not None else None
    time_range = filters.time_range
    return VectorRetrieveParams(
        query_type=analysis.query_type,
        project=filters.project,
        context_keywords=list(filters.context_keywords),
        status_filter=status,
        time_range_after=time_range.after if time_range else None,
        time_range_before=time_range.before if time_range else None,
        semantic_query=analysis.semantic_query,
    )


def _resolve_vector_search_limit(paths: DataPaths, limit: int | None) -> int:
    if limit is not None:
        return limit
    if paths.config_path.is_file():
        return load_config(paths).extraction.context_search_limit
    return default_config(paths.data_dir).extraction.context_search_limit
