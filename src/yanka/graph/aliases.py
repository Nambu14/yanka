"""Context alias registry helpers — spec §9."""

from __future__ import annotations

from dataclasses import dataclass

from yanka.graph.context import normalize_context_segment
from yanka.graph.store import GraphDb


@dataclass(frozen=True)
class ContextCandidate:
    canonical_name: str
    normalized_name: str
    aliases: list[str]


def lookup_context_by_alias(
    graph: GraphDb,
    raw_segment: str,
    *,
    depth: int,
    parent_canonical: str | None = None,
) -> str | None:
    """Return canonical_name when raw_segment matches a stored alias."""
    segment_keys = _alias_match_keys(raw_segment)
    for candidate in list_context_candidates(
        graph, depth=depth, parent_canonical=parent_canonical
    ):
        for alias in candidate.aliases:
            if segment_keys & _alias_match_keys(alias):
                return candidate.canonical_name
    return None


def list_context_candidates(
    graph: GraphDb,
    *,
    depth: int,
    parent_canonical: str | None = None,
) -> list[ContextCandidate]:
    """Return Context nodes at the given depth (optionally under a parent)."""
    if depth == 0:
        query = (
            "MATCH (c:Context) WHERE c.depth = 0 "
            "RETURN c.canonical_name, c.normalized_name, c.aliases "
            "ORDER BY c.canonical_name"
        )
        rows = graph.connection.execute(query).get_all()
    else:
        if parent_canonical is None:
            return []
        query = (
            "MATCH (parent:Context {canonical_name: $parent})"
            "-[:contains]->(c:Context) "
            "WHERE c.depth = $depth "
            "RETURN c.canonical_name, c.normalized_name, c.aliases "
            "ORDER BY c.canonical_name"
        )
        rows = graph.connection.execute(
            query,
            parameters={"parent": parent_canonical, "depth": depth},
        ).get_all()

    return [_row_to_candidate(row) for row in rows]


def append_context_alias(
    graph: GraphDb,
    canonical_name: str,
    alias: str,
) -> None:
    """Persist a new alias phrase on a Context node (idempotent)."""
    phrase = alias.strip()
    if not phrase:
        return

    rows = graph.connection.execute(
        "MATCH (c:Context {canonical_name: $canonical_name}) RETURN c.aliases",
        parameters={"canonical_name": canonical_name},
    ).get_all()
    if not rows:
        msg = f"Context node not found: {canonical_name!r}"
        raise ValueError(msg)

    existing = _coerce_alias_list(rows[0][0])
    if _alias_already_stored(existing, phrase):
        return

    updated = existing + [phrase]
    graph.connection.execute(
        "MATCH (c:Context {canonical_name: $canonical_name}) "
        "SET c.aliases = $aliases",
        parameters={"canonical_name": canonical_name, "aliases": updated},
    )


def _row_to_candidate(row: list) -> ContextCandidate:
    aliases = _coerce_alias_list(row[2])
    return ContextCandidate(
        canonical_name=str(row[0]),
        normalized_name=str(row[1]),
        aliases=aliases,
    )


def _coerce_alias_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _alias_match_keys(phrase: str) -> set[str]:
    stripped = phrase.strip().lower()
    keys = {stripped} if stripped else set()
    normalized = normalize_context_segment(phrase)
    if normalized:
        keys.add(normalized)
    return keys


def _alias_already_stored(aliases: list[str], phrase: str) -> bool:
    new_keys = _alias_match_keys(phrase)
    for existing in aliases:
        if new_keys & _alias_match_keys(existing):
            return True
    return False
