"""Per-claim duplicate detection — spec §7 step 5.5.

Embeds each new claim and finds the closest active claim in the same project
context. A new claim whose nearest neighbor has distance ≤
``extraction.duplicate_claim_max_distance`` is treated as a restatement of that
existing claim and should be dropped from the record before write.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from yanka.config import EmbeddingConfig, default_config, load_config
from yanka.paths import DataPaths, resolve_data_paths
from yanka.records.models import Claim, ClaimStatus
from yanka.vectors.filters import VectorSearchFilters
from yanka.vectors.search import search_claims

type SearchClaimsFn = Callable[..., list[dict[str, Any]]]

# How many existing claims to retrieve per new claim. We only use the best hit
# but ask for a few in case the very top match lacks a distance score.
_DUPLICATE_SEARCH_LIMIT = 3


@dataclass(frozen=True)
class DuplicateClaimMatch:
    """A new claim that restates an existing active claim in the same context."""

    new_claim_id: str
    new_content: str
    existing_claim_id: str
    existing_content: str
    existing_file: str
    distance: float


def find_duplicate_claims(
    new_claims: list[Claim],
    context_path: list[str],
    paths: DataPaths | None = None,
    *,
    config: EmbeddingConfig | None = None,
    max_distance: float | None = None,
    search_claims_fn: SearchClaimsFn | None = None,
) -> list[DuplicateClaimMatch]:
    """Return one match per new claim that has an existing duplicate, in input order."""
    if not new_claims:
        return []
    if not context_path:
        msg = "context_path must not be empty"
        raise ValueError(msg)

    resolved = paths if paths is not None else resolve_data_paths()
    threshold = _resolve_max_distance(resolved, max_distance)
    filters = VectorSearchFilters(
        status=ClaimStatus.ACTIVE.value,
        project=context_path[0],
        context_path_prefix="/".join(context_path),
    )
    search = search_claims_fn or search_claims

    matches: list[DuplicateClaimMatch] = []
    for claim in new_claims:
        hits = search(
            claim.content,
            resolved,
            filters=filters,
            limit=_DUPLICATE_SEARCH_LIMIT,
            config=config,
        )
        best = _best_hit_with_distance(hits)
        if best is None:
            continue
        hit, distance = best
        if distance > threshold:
            continue
        matches.append(
            DuplicateClaimMatch(
                new_claim_id=claim.id,
                new_content=claim.content,
                existing_claim_id=str(hit.get("claim_id", "")),
                existing_content=str(hit.get("content", "")),
                existing_file=str(hit.get("source_file", "")),
                distance=distance,
            )
        )
    return matches


def drop_duplicate_claims(
    new_claims: list[Claim],
    matches: list[DuplicateClaimMatch],
) -> list[Claim]:
    """Drop duplicates and renumber survivors as ``c1..cN``.

    Renumbering keeps written claim ids contiguous; the original ids only ever
    appear in the pre-write pipeline, never in the saved markdown.
    """
    duplicate_ids = {match.new_claim_id for match in matches}
    kept = [claim for claim in new_claims if claim.id not in duplicate_ids]
    survivors: list[Claim] = []
    for index, claim in enumerate(kept, start=1):
        survivors.append(
            Claim(
                id=f"c{index}",
                content=claim.content,
                status=claim.status,
                supersedes=claim.supersedes,
            )
        )
    return survivors


def _best_hit_with_distance(
    hits: list[dict[str, Any]],
) -> tuple[dict[str, Any], float] | None:
    best: tuple[dict[str, Any], float] | None = None
    for hit in hits:
        distance = _hit_distance(hit)
        if distance is None:
            continue
        if best is None or distance < best[1]:
            best = (hit, distance)
    return best


def _hit_distance(hit: dict[str, Any]) -> float | None:
    for key in ("_distance", "distance"):
        value = hit.get(key)
        if isinstance(value, int | float):
            return float(value)
    return None


def _resolve_max_distance(paths: DataPaths, override: float | None) -> float:
    if override is not None:
        return override
    if paths.config_path.is_file():
        return load_config(paths).extraction.duplicate_claim_max_distance
    return default_config(paths.data_dir).extraction.duplicate_claim_max_distance
