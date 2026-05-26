"""Graph retrieval queries by query type — spec §8 step 2 (graph column)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from collections.abc import Callable
from typing import Any

from whyline.graph.context import normalize_context_segment
from whyline.graph.store import GraphDb
from whyline.retrieval_enums import QueryType, StatusFilter


@dataclass
class GraphRetrieveFilters:
    """Structured filters for graph retrieval (mirrors retrieval QueryFilters)."""

    project: str | None = None
    context_keywords: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    time_range_after: date | None = None
    time_range_before: date | None = None
    status_filter: str | None = None


def retrieve_decisions_by_type(
    query_type: QueryType,
    filters: GraphRetrieveFilters,
    graph: GraphDb,
    *,
    semantic_query: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return decision rows for retrieval: file_reference, date, status, summary, context_canonical."""
    if limit < 1:
        msg = "limit must be at least 1"
        raise ValueError(msg)

    dispatch: dict[QueryType, Callable[[], list[dict[str, Any]]]] = {
        QueryType.PERSON: lambda: _retrieve_person(filters, graph, limit=limit),
        QueryType.SPECIFIC_DECISION: lambda: _retrieve_specific_decision(
            filters,
            graph,
            semantic_query=semantic_query,
            limit=limit,
        ),
        QueryType.RELATIONSHIP: lambda: _retrieve_relationship(
            filters,
            graph,
            semantic_query=semantic_query,
            limit=limit,
        ),
        QueryType.EXPLORATORY: lambda: _retrieve_exploratory(filters, graph, limit=limit),
        QueryType.HISTORICAL: lambda: _retrieve_historical(filters, graph, limit=limit),
        QueryType.CURRENT_STATE: lambda: _retrieve_current_state(filters, graph, limit=limit),
    }
    handler = dispatch.get(query_type, dispatch[QueryType.EXPLORATORY])
    return handler()


def _retrieve_current_state(
    filters: GraphRetrieveFilters,
    graph: GraphDb,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    status = _effective_status_filter(filters, active_only=True)
    return _decisions_for_context_scope(
        filters,
        graph,
        status_filter=status,
        order="DESC",
        limit=limit,
    )


def _retrieve_historical(
    filters: GraphRetrieveFilters,
    graph: GraphDb,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    in_scope = _decisions_for_context_scope(
        filters,
        graph,
        status_filter=None,
        order="ASC",
        limit=limit,
    )
    chain = _decisions_in_supersedes_chain(filters, graph, limit=limit)
    return _merge_decision_rows(in_scope, chain, limit=limit)


def _retrieve_exploratory(
    filters: GraphRetrieveFilters,
    graph: GraphDb,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    return _decisions_for_context_scope(
        filters,
        graph,
        status_filter=None,
        order="DESC",
        limit=limit,
    )


def _retrieve_specific_decision(
    filters: GraphRetrieveFilters,
    graph: GraphDb,
    *,
    semantic_query: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    keywords = _search_terms(filters, semantic_query)
    if not keywords:
        return _decisions_for_context_scope(
            filters,
            graph,
            status_filter=None,
            order="DESC",
            limit=limit,
        )

    for keyword in keywords:
        if keyword.endswith(".md"):
            ref = keyword if keyword.startswith("records/") else f"records/{keyword}"
            row = _decision_by_file_reference(ref, graph)
            if row is not None:
                return [row]

    rows = _search_decisions_by_keywords(
        filters,
        graph,
        keywords,
        status_filter=None,
        limit=limit,
    )
    if rows:
        return rows

    return _decisions_for_context_scope(
        filters,
        graph,
        status_filter=None,
        order="DESC",
        limit=limit,
    )


def _retrieve_relationship(
    filters: GraphRetrieveFilters,
    graph: GraphDb,
    *,
    semantic_query: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    keywords = _search_terms(filters, semantic_query)
    anchors = _search_decisions_by_keywords(
        filters,
        graph,
        keywords,
        status_filter=None,
        limit=min(limit, 3),
    )
    if not anchors:
        return _decisions_for_context_scope(
            filters,
            graph,
            status_filter=None,
            order="DESC",
            limit=limit,
        )

    expanded: list[dict[str, Any]] = list(anchors)
    for anchor in anchors:
        related = _related_decisions(anchor, filters, graph, limit=limit)
        expanded.extend(related)
    return _merge_decision_rows(expanded, [], limit=limit)


def _retrieve_person(
    filters: GraphRetrieveFilters,
    graph: GraphDb,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if not filters.people:
        return []

    params: dict[str, Any] = {"limit": limit}
    person_clauses: list[str] = []
    for index, person in enumerate(filters.people):
        key = f"person_{index}"
        params[key] = person
        person_clauses.append(f"p.name = ${key}")

    project_clause, project_params = _project_context_clause(filters.project)
    params.update(project_params)

    query = (
        f"MATCH (p:Person) WHERE {' OR '.join(person_clauses)} "
        "MATCH (d:Decision)-[:involves]->(p) "
        "MATCH (d)-[:about]->(c:Context) "
        f"WHERE {project_clause} "
        "RETURN DISTINCT d.file_reference, d.date, d.status, d.summary, c.canonical_name "
        "ORDER BY d.date DESC "
        "LIMIT $limit"
    )
    return _rows_from_query(graph, query, params)


def _decisions_for_context_scope(
    filters: GraphRetrieveFilters,
    graph: GraphDb,
    *,
    status_filter: str | None,
    order: str,
    limit: int,
) -> list[dict[str, Any]]:
    contexts = _matching_context_roots(filters, graph)
    if contexts == []:
        return []

    params: dict[str, Any] = {
        "limit": limit,
        "status": status_filter,
    }
    params.update(_date_params(filters))

    project_clause, project_params = _project_context_clause(filters.project)
    params.update(project_params)

    date_clause = _date_clause()
    status_clause = "AND ($status IS NULL OR d.status = $status) " if status_filter else ""

    if contexts is None:
        query = (
            "MATCH (d:Decision)-[:about]->(c:Context) "
            f"WHERE {project_clause} {status_clause}{date_clause}"
            "RETURN DISTINCT d.file_reference, d.date, d.status, d.summary, c.canonical_name "
            f"ORDER BY d.date {order} "
            "LIMIT $limit"
        )
        return _rows_from_query(graph, query, params)

    context_clause = _context_subtree_clause(contexts, params)
    query = (
        "MATCH (c:Context) "
        f"WHERE {context_clause} AND {project_clause} "
        "WITH DISTINCT c "
        "MATCH (d:Decision)-[:about]->(c) "
        f"WHERE TRUE {status_clause}{date_clause}"
        "RETURN DISTINCT d.file_reference, d.date, d.status, d.summary, c.canonical_name "
        f"ORDER BY d.date {order} "
        "LIMIT $limit"
    )
    return _rows_from_query(graph, query, params)


def _decisions_in_supersedes_chain(
    filters: GraphRetrieveFilters,
    graph: GraphDb,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    contexts = _matching_context_roots(filters, graph)
    if contexts == []:
        return []

    params: dict[str, Any] = {"limit": limit}
    project_clause, project_params = _project_context_clause(filters.project)
    params.update(project_params)
    params.update(_date_params(filters))
    date_clause = _date_clause()

    if contexts is None:
        query = (
            "MATCH (d:Decision)-[:about]->(c:Context) "
            "MATCH (d)-[:has_claim]->(cl:Claim)-[:supersedes*1..]->(:Claim) "
            f"WHERE {project_clause} {date_clause}"
            "RETURN DISTINCT d.file_reference, d.date, d.status, d.summary, c.canonical_name "
            "ORDER BY d.date ASC "
            "LIMIT $limit"
        )
        return _rows_from_query(graph, query, params)

    context_clause = _context_subtree_clause(contexts, params)
    query = (
        "MATCH (c:Context) "
        f"WHERE {context_clause} AND {project_clause} "
        "WITH DISTINCT c "
        "MATCH (d:Decision)-[:about]->(c) "
        "MATCH (d)-[:has_claim]->(cl:Claim)-[:supersedes*1..]->(:Claim) "
        f"WHERE TRUE {date_clause}"
        "RETURN DISTINCT d.file_reference, d.date, d.status, d.summary, c.canonical_name "
        "ORDER BY d.date ASC "
        "LIMIT $limit"
    )
    return _rows_from_query(graph, query, params)


def _search_decisions_by_keywords(
    filters: GraphRetrieveFilters,
    graph: GraphDb,
    keywords: list[str],
    *,
    status_filter: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if not keywords:
        return []

    params: dict[str, Any] = {"limit": limit, "status": status_filter}
    params.update(_date_params(filters))
    project_clause, project_params = _project_context_clause(filters.project)
    params.update(project_params)

    keyword_checks: list[str] = []
    for index, keyword in enumerate(keywords):
        key = f"kw_{index}"
        params[key] = keyword.lower()
        keyword_checks.append(
            f"(LOWER(d.summary) CONTAINS ${key} OR list_contains(d.tags, ${key}))"
        )

    status_clause = "AND ($status IS NULL OR d.status = $status) " if status_filter else ""
    date_clause = _date_clause()

    query = (
        "MATCH (d:Decision)-[:about]->(c:Context) "
        f"WHERE {project_clause} AND ({' OR '.join(keyword_checks)}) "
        f"{status_clause}{date_clause}"
        "RETURN DISTINCT d.file_reference, d.date, d.status, d.summary, c.canonical_name "
        "ORDER BY d.date DESC "
        "LIMIT $limit"
    )
    try:
        return _rows_from_query(graph, query, params)
    except Exception:
        return _search_decisions_by_keywords_fallback(
            filters,
            graph,
            keywords,
            status_filter=status_filter,
            limit=limit,
        )


def _search_decisions_by_keywords_fallback(
    filters: GraphRetrieveFilters,
    graph: GraphDb,
    keywords: list[str],
    *,
    status_filter: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit * 4}
    project_clause, project_params = _project_context_clause(filters.project)
    params.update(project_params)

    query = (
        "MATCH (d:Decision)-[:about]->(c:Context) "
        f"WHERE {project_clause} "
        "RETURN DISTINCT d.file_reference, d.date, d.status, d.summary, c.canonical_name, d.tags "
        "ORDER BY d.date DESC "
        "LIMIT $limit"
    )
    rows = _rows_from_query(graph, query, params, with_tags=True)
    lowered = [keyword.lower() for keyword in keywords]
    matched: list[dict[str, Any]] = []
    for row in rows:
        if status_filter is not None and row["status"] != status_filter:
            continue
        summary = row["summary"].lower()
        tags = [str(tag).lower() for tag in row.get("tags") or []]
        if any(keyword in summary or keyword in tag for keyword in lowered for tag in tags):
            matched.append(
                {
                    "file_reference": row["file_reference"],
                    "date": row["date"],
                    "status": row["status"],
                    "summary": row["summary"],
                    "context_canonical": row["context_canonical"],
                }
            )
        if len(matched) >= limit:
            break
    return matched


def _related_decisions(
    anchor: dict[str, Any],
    filters: GraphRetrieveFilters,
    graph: GraphDb,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    context = anchor["context_canonical"]
    prefix = f"{context}/"
    params: dict[str, Any] = {
        "context": context,
        "prefix": prefix,
        "limit": limit,
        "anchor_ref": anchor["file_reference"],
    }
    project_clause, project_params = _project_context_clause(filters.project)
    params.update(project_params)

    query = (
        "MATCH (c:Context) "
        "WHERE c.canonical_name = $context OR c.canonical_name STARTS WITH $prefix "
        "WITH DISTINCT c "
        "MATCH (d:Decision)-[:about]->(c) "
        f"WHERE {project_clause} AND d.file_reference <> $anchor_ref "
        "RETURN DISTINCT d.file_reference, d.date, d.status, d.summary, c.canonical_name "
        "ORDER BY d.date DESC "
        "LIMIT $limit"
    )
    return _rows_from_query(graph, query, params)


def _decision_by_file_reference(
    file_reference: str,
    graph: GraphDb,
) -> dict[str, Any] | None:
    rows = _rows_from_query(
        graph,
        "MATCH (d:Decision {file_reference: $ref})-[:about]->(c:Context) "
        "RETURN d.file_reference, d.date, d.status, d.summary, c.canonical_name "
        "LIMIT 1",
        {"ref": file_reference},
    )
    return rows[0] if rows else None


def _matching_context_roots(
    filters: GraphRetrieveFilters,
    graph: GraphDb,
) -> list[str] | None:
    """Context canonical names to search; ``None`` = no context restriction (all)."""
    rows = graph.connection.execute(
        "MATCH (c:Context) RETURN c.canonical_name, c.normalized_name, c.aliases"
    ).get_all()

    if not rows:
        return []

    keywords = [normalize_context_segment(kw) for kw in filters.context_keywords]
    matched: list[str] = []

    for canonical_name, normalized_name, aliases in rows:
        if filters.project and not (
            canonical_name == filters.project
            or canonical_name.startswith(f"{filters.project}/")
        ):
            continue

        if not keywords:
            matched.append(canonical_name)
            continue

        alias_values = aliases if isinstance(aliases, list) else []
        haystack = " ".join(
            [canonical_name.lower(), normalized_name.lower()]
            + [str(alias).lower() for alias in alias_values]
        )
        if any(keyword in haystack for keyword in keywords):
            matched.append(canonical_name)

    if filters.context_keywords:
        return sorted(set(matched))

    if filters.project:
        return [filters.project]

    return None


def _context_subtree_clause(contexts: list[str], params: dict[str, Any]) -> str:
    clauses: list[str] = []
    for index, name in enumerate(contexts):
        leaf_key = f"leaf_{index}"
        prefix_key = f"prefix_{index}"
        params[leaf_key] = name
        params[prefix_key] = f"{name}/"
        clauses.append(
            f"(c.canonical_name = ${leaf_key} OR c.canonical_name STARTS WITH ${prefix_key})"
        )
    return " OR ".join(clauses) if clauses else "TRUE"


def _project_context_clause(project: str | None) -> tuple[str, dict[str, Any]]:
    if project is None:
        return "TRUE", {}
    return (
        "(c.canonical_name = $project OR c.canonical_name STARTS WITH $project_prefix)",
        {"project": project, "project_prefix": f"{project}/"},
    )


def _date_params(filters: GraphRetrieveFilters) -> dict[str, Any]:
    return {
        "after": (
            filters.time_range_after.isoformat() if filters.time_range_after else None
        ),
        "before": (
            filters.time_range_before.isoformat() if filters.time_range_before else None
        ),
    }


def _date_clause() -> str:
    return (
        "AND ($after IS NULL OR d.date >= date($after)) "
        "AND ($before IS NULL OR d.date <= date($before)) "
    )


def _effective_status_filter(
    filters: GraphRetrieveFilters,
    *,
    active_only: bool,
) -> str | None:
    if active_only or filters.status_filter == StatusFilter.ACTIVE.value:
        return StatusFilter.ACTIVE.value
    if filters.status_filter == StatusFilter.ALL.value:
        return None
    return None


def _search_terms(filters: GraphRetrieveFilters, semantic_query: str | None) -> list[str]:
    terms: list[str] = []
    if semantic_query:
        terms.append(semantic_query.strip())
    for keyword in filters.context_keywords:
        if keyword not in terms:
            terms.append(keyword)
    return [term for term in terms if term]


def _merge_decision_rows(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in primary + secondary:
        ref = row["file_reference"]
        if ref in seen:
            continue
        seen.add(ref)
        merged.append(row)
        if len(merged) >= limit:
            break
    return merged


def _rows_from_query(
    graph: GraphDb,
    query: str,
    params: dict[str, Any],
    *,
    with_tags: bool = False,
) -> list[dict[str, Any]]:
    rows = graph.connection.execute(query, parameters=params).get_all()
    results: list[dict[str, Any]] = []
    for row in rows:
        parsed = {
            "file_reference": row[0],
            "date": _coerce_date(row[1]),
            "status": row[2],
            "summary": row[3],
            "context_canonical": row[4],
        }
        if with_tags and len(row) > 5:
            parsed["tags"] = row[5]
        results.append(parsed)
    return results


def _coerce_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    msg = f"unexpected date value: {value!r}"
    raise TypeError(msg)
