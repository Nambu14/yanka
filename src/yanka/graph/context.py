"""Context hierarchy upsert — spec §4 Context + contains edges."""

from __future__ import annotations

from dataclasses import dataclass

from yanka.graph.store import GraphDb


@dataclass(frozen=True)
class ContextLevel:
    canonical_name: str
    normalized_name: str
    depth: int


_SUFFIXES = ("service", "system", "module")


def normalize_context_segment(segment: str) -> str:
    """Normalize a context segment for entity resolution (spec §9)."""
    from yanka.records.slug import slugify_text

    slug = slugify_text(segment)
    for suffix in _SUFFIXES:
        token = f"-{suffix}"
        if slug.endswith(token) and len(slug) > len(token):
            slug = slug[: -len(token)]
            break
    return slug or "context"


def build_context_levels(segments: list[str]) -> list[ContextLevel]:
    levels: list[ContextLevel] = []
    parts: list[str] = []
    for depth, segment in enumerate(segments):
        parts.append(segment)
        levels.append(
            ContextLevel(
                canonical_name="/".join(parts),
                normalized_name=normalize_context_segment(segment),
                depth=depth,
            )
        )
    return levels


def upsert_context_path(segments: list[str], graph: GraphDb) -> str:
    """Upsert Context nodes and contains edges for an ordered path.

    Returns the leaf canonical_name (same string shape as vector context_path).
    Idempotent: safe to call again with the same segments.
    """
    if not segments:
        msg = "context_path must not be empty"
        raise ValueError(msg)

    levels = build_context_levels(segments)
    conn = graph.connection

    for level in levels:
        canonical = _escape_cypher_string(level.canonical_name)
        normalized = _escape_cypher_string(level.normalized_name)
        conn.execute(
            f"MERGE (n:Context {{canonical_name: '{canonical}'}}) "
            f"ON CREATE SET n.normalized_name = '{normalized}', "
            f"n.depth = {level.depth}, n.aliases = []"
        )

    for index in range(1, len(levels)):
        parent = _escape_cypher_string(levels[index - 1].canonical_name)
        child = _escape_cypher_string(levels[index].canonical_name)
        conn.execute(
            f"MATCH (parent:Context {{canonical_name: '{parent}'}}), "
            f"(child:Context {{canonical_name: '{child}'}}) "
            f"MERGE (parent)-[:contains]->(child)"
        )

    return levels[-1].canonical_name


def _escape_cypher_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")
