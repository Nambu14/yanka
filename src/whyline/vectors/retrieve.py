"""Vector retrieval for the retrieval pipeline — spec §8 step 2 (vector column)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from whyline.graph.context import normalize_context_segment
from whyline.retrieval_enums import QueryType, StatusFilter
from whyline.vectors.filters import VectorSearchFilters


@dataclass
class VectorRetrieveParams:
    """Inputs for vector retrieval (mirrors QueryAnalysis without retrieval imports)."""

    query_type: QueryType
    project: str | None = None
    context_keywords: list[str] = field(default_factory=list)
    status_filter: str | None = None
    time_range_after: date | None = None
    time_range_before: date | None = None
    semantic_query: str | None = None


def retrieval_search_query(params: VectorRetrieveParams) -> str | None:
    """Text to embed for vector search; ``None`` when retrieval should skip."""
    if params.semantic_query:
        return params.semantic_query.strip()

    keywords = [keyword.strip() for keyword in params.context_keywords if keyword.strip()]
    if keywords:
        return " ".join(keywords)

    return None


def should_skip_vector_retrieval(params: VectorRetrieveParams) -> bool:
    """Whether vector search should not run for this analysis."""
    if params.query_type is not QueryType.PERSON:
        return False
    return retrieval_search_query(params) is None


def vector_filters_for_params(params: VectorRetrieveParams) -> VectorSearchFilters:
    """Map retrieval filters to LanceDB metadata filters (spec §8 table)."""
    status = _status_for_query_type(params.query_type, params.status_filter)
    return VectorSearchFilters(
        status=status,
        project=params.project,
        context_path_prefix=_context_path_prefix(params.project, params.context_keywords),
        date_after=params.time_range_after,
        date_before=params.time_range_before,
    )


def _status_for_query_type(
    query_type: QueryType,
    status_filter: str | None,
) -> str | None:
    if query_type is QueryType.CURRENT_STATE:
        return status_filter or StatusFilter.ACTIVE.value

    if query_type is QueryType.HISTORICAL:
        return None if status_filter in (None, StatusFilter.ALL.value) else status_filter

    if query_type is QueryType.EXPLORATORY:
        return status_filter

    if query_type is QueryType.PERSON:
        return status_filter

    return status_filter


def _context_path_prefix(
    project: str | None,
    context_keywords: list[str],
) -> str | None:
    if project and context_keywords:
        segment = normalize_context_segment(context_keywords[0])
        return f"{project}/{segment}"
    if project:
        return project
    if context_keywords:
        return normalize_context_segment(context_keywords[0])
    return None


def vector_hit_score(hit: dict[str, Any]) -> float | None:
    """Extract a similarity score from a LanceDB search row."""
    for key in ("_distance", "_score", "score"):
        value = hit.get(key)
        if isinstance(value, int | float):
            return float(value)
    return None


def vector_hit_date(hit: dict[str, Any]) -> date:
    value = hit.get("date")
    if isinstance(value, date):
        return value
    if hasattr(value, "isoformat"):
        return date.fromisoformat(str(value)[:10])
    msg = f"unexpected date in vector hit: {value!r}"
    raise TypeError(msg)
