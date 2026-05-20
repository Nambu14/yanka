"""Metadata filters for LanceDB vector search (spec §5)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VectorSearchFilters:
    """Optional metadata filters applied with AND semantics."""

    status: str | None = None
    project: str | None = None
    context_path_prefix: str | None = None


def build_where_clause(filters: VectorSearchFilters | None) -> str | None:
    """Build a LanceDB SQL ``where`` clause, or ``None`` if no filters."""
    if filters is None:
        return None

    parts: list[str] = []
    if filters.status is not None:
        parts.append(predicate_equals("status", filters.status))
    if filters.project is not None:
        parts.append(predicate_equals("project", filters.project))
    if filters.context_path_prefix is not None:
        prefix = _escape_like_literal(filters.context_path_prefix)
        parts.append(f"context_path LIKE '{prefix}%'")

    if not parts:
        return None
    return " AND ".join(parts)


def predicate_equals(column: str, value: str) -> str:
    escaped = value.replace("'", "''")
    return f"{column} = '{escaped}'"


def _escape_like_literal(value: str) -> str:
    return value.replace("'", "''").replace("%", "\\%").replace("_", "\\_")
