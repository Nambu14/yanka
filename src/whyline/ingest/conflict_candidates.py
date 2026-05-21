"""Conflict candidate search for ingest — spec §7 step 6."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from whyline.config import EmbeddingConfig, default_config, load_config
from whyline.graph.conflicts import graph_conflict_candidates
from whyline.graph.store import GraphDb
from whyline.paths import DataPaths, resolve_data_paths
from whyline.records.models import Claim
from whyline.vectors.filters import VectorSearchFilters
from whyline.vectors.search import search_claims

ConflictSource = Literal["graph", "vector"]
type SearchClaimsFn = Callable[..., list[dict[str, Any]]]


@dataclass(frozen=True)
class ConflictCandidate:
    """A candidate existing claim that may conflict with new ingest claims."""

    claim_id: str
    content: str
    source_file: str
    status: str
    source: ConflictSource
    similarity: float | None = None


def find_conflict_candidates(
    claims: list[Claim],
    context_path: list[str],
    graph: GraphDb,
    paths: DataPaths | None = None,
    *,
    limit: int | None = None,
    config: EmbeddingConfig | None = None,
    search_claims_fn: SearchClaimsFn | None = None,
) -> list[ConflictCandidate]:
    """Merge graph subtree claims and vector semantic neighbors (spec §7 step 6)."""
    if not claims:
        return []
    if not context_path:
        msg = "context_path must not be empty"
        raise ValueError(msg)

    resolved = paths if paths is not None else resolve_data_paths()
    max_results = _resolve_conflict_search_limit(resolved, limit)
    graph_rows = graph_conflict_candidates(context_path, graph)
    vector_rows = vector_conflict_candidates(
        claims,
        context_path,
        resolved,
        limit_per_claim=max_results,
        config=config,
        search_claims_fn=search_claims_fn,
    )
    return merge_conflict_candidates(graph_rows, vector_rows, limit=max_results)


def vector_conflict_candidates(
    claims: list[Claim],
    context_path: list[str],
    paths: DataPaths | None = None,
    *,
    limit_per_claim: int | None = None,
    config: EmbeddingConfig | None = None,
    search_claims_fn: SearchClaimsFn | None = None,
) -> list[ConflictCandidate]:
    """Embed each new claim and search LanceDB for active semantic neighbors."""
    if not claims:
        return []
    if not context_path:
        msg = "context_path must not be empty"
        raise ValueError(msg)

    resolved = paths if paths is not None else resolve_data_paths()
    per_claim_limit = _resolve_conflict_search_limit(resolved, limit_per_claim)
    filters = VectorSearchFilters(
        status="active",
        project=context_path[0],
        context_path_prefix=_context_path_prefix(context_path),
    )
    search = search_claims_fn or search_claims

    candidates: list[ConflictCandidate] = []
    seen: set[str] = set()
    for claim in claims:
        hits = search(
            claim.content,
            resolved,
            filters=filters,
            limit=per_claim_limit,
            config=config,
        )
        for hit in hits:
            candidate = _candidate_from_vector_hit(hit)
            if candidate.claim_id in seen:
                continue
            seen.add(candidate.claim_id)
            candidates.append(candidate)
    return candidates


def merge_conflict_candidates(
    graph_rows: list[dict[str, Any]],
    vector_candidates: list[ConflictCandidate],
    *,
    limit: int,
) -> list[ConflictCandidate]:
    """Union graph + vector candidates; graph wins dedupe; cap at ``limit``."""
    if limit < 1:
        msg = "limit must be at least 1"
        raise ValueError(msg)

    graph_candidates = [_candidate_from_graph_row(row) for row in graph_rows]
    seen: set[str] = set()
    merged: list[ConflictCandidate] = []

    for candidate in graph_candidates:
        if candidate.claim_id in seen:
            continue
        merged.append(candidate)
        seen.add(candidate.claim_id)

    for candidate in sorted(vector_candidates, key=_vector_sort_key):
        if candidate.claim_id in seen:
            continue
        merged.append(candidate)
        seen.add(candidate.claim_id)

    return merged[:limit]


def _candidate_from_graph_row(row: dict[str, Any]) -> ConflictCandidate:
    return ConflictCandidate(
        claim_id=str(row["claim_id"]),
        content=str(row["content"]),
        source_file=str(row["source_file"]),
        status=str(row["status"]),
        source="graph",
    )


def _candidate_from_vector_hit(hit: dict[str, Any]) -> ConflictCandidate:
    claim_id = hit.get("claim_id")
    content = hit.get("content")
    source_file = hit.get("source_file")
    status = hit.get("status")
    if not all(
        isinstance(value, str)
        for value in (claim_id, content, source_file, status)
    ):
        msg = "vector hit missing required claim fields"
        raise ValueError(msg)
    return ConflictCandidate(
        claim_id=claim_id,
        content=content,
        source_file=source_file,
        status=status,
        source="vector",
        similarity=_hit_similarity(hit),
    )


def _hit_similarity(hit: dict[str, Any]) -> float | None:
    for key in ("_distance", "_score", "score"):
        value = hit.get(key)
        if isinstance(value, int | float):
            return float(value)
    return None


def _vector_sort_key(candidate: ConflictCandidate) -> tuple[float, str]:
    if candidate.similarity is None:
        return (float("inf"), candidate.claim_id)
    return (candidate.similarity, candidate.claim_id)


def _context_path_prefix(context_path: list[str]) -> str:
    return "/".join(context_path)


def _resolve_conflict_search_limit(paths: DataPaths, limit: int | None) -> int:
    if limit is not None:
        return limit
    if paths.config_path.is_file():
        return load_config(paths).extraction.conflict_search_limit
    return default_config(paths.data_dir).extraction.conflict_search_limit
