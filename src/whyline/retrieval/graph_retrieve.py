"""Graph retrieval step for the retrieval pipeline — spec §8 step 2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from whyline.config import default_config, load_config
from whyline.graph.retrieve import GraphRetrieveFilters, retrieve_decisions_by_type
from whyline.graph.store import GraphDb
from whyline.paths import DataPaths, resolve_data_paths
from whyline.retrieval.query_analysis import QueryAnalysis
from whyline.retrieval_enums import QueryType, StatusFilter

GraphHitSource = Literal["graph"]


@dataclass(frozen=True)
class GraphRetrievalHit:
    """A decision surfaced from Ladybug graph retrieval."""

    file_reference: str
    date: date
    status: str
    summary: str
    context_canonical: str
    source: GraphHitSource = "graph"


def retrieve_from_graph(
    analysis: QueryAnalysis,
    graph: GraphDb,
    paths: DataPaths | None = None,
    *,
    limit: int | None = None,
) -> list[GraphRetrievalHit]:
    """Dispatch graph retrieval by ``analysis.query_type`` and filters."""
    resolved = paths if paths is not None else resolve_data_paths()
    max_results = _resolve_graph_search_limit(resolved, limit)
    rows = retrieve_decisions_by_type(
        analysis.query_type,
        _to_graph_filters(analysis),
        graph,
        semantic_query=analysis.semantic_query,
        limit=max_results,
    )
    return [_hit_from_row(row) for row in rows]


def _to_graph_filters(analysis: QueryAnalysis) -> GraphRetrieveFilters:
    filters = analysis.filters
    status = filters.status_filter.value if filters.status_filter is not None else None
    if analysis.query_type is QueryType.CURRENT_STATE and status is None:
        status = StatusFilter.ACTIVE.value
    time_range = filters.time_range
    return GraphRetrieveFilters(
        project=filters.project,
        context_keywords=list(filters.context_keywords),
        people=list(filters.people),
        time_range_after=time_range.after if time_range else None,
        time_range_before=time_range.before if time_range else None,
        status_filter=status,
    )


def _hit_from_row(row: dict) -> GraphRetrievalHit:
    value = row["date"]
    if not isinstance(value, date):
        value = date.fromisoformat(str(value))
    return GraphRetrievalHit(
        file_reference=row["file_reference"],
        date=value,
        status=row["status"],
        summary=row["summary"],
        context_canonical=row["context_canonical"],
    )


def _resolve_graph_search_limit(paths: DataPaths, limit: int | None) -> int:
    if limit is not None:
        return limit
    if paths.config_path.is_file():
        return load_config(paths).extraction.context_search_limit
    return default_config(paths.data_dir).extraction.context_search_limit
