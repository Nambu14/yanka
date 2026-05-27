"""Read-only graph inspection helpers for the REPL."""

from __future__ import annotations

from dataclasses import dataclass

from yanka.graph.schema import init_graph_schema
from yanka.graph.store import GraphDb


@dataclass(frozen=True)
class PersonSummary:
    name: str
    aliases: list[str]
    decision_count: int


@dataclass(frozen=True)
class ProjectSummary:
    canonical_name: str
    decision_count: int


def list_people(graph: GraphDb) -> list[PersonSummary]:
    """Return people in the graph with distinct decision counts."""
    init_graph_schema(graph)
    rows = graph.connection.execute(
        "MATCH (p:Person) "
        "OPTIONAL MATCH (d:Decision)-[:involves]->(p) "
        "RETURN p.name, p.aliases, count(DISTINCT d) "
        "ORDER BY p.name"
    ).get_all()
    return [
        PersonSummary(
            name=str(row[0]),
            aliases=_aliases_list(row[1]),
            decision_count=int(row[2]),
        )
        for row in rows
    ]


def list_projects(graph: GraphDb) -> list[ProjectSummary]:
    """Return root context nodes (depth 0) with decision counts in each subtree."""
    init_graph_schema(graph)
    root_rows = graph.connection.execute(
        "MATCH (c:Context) WHERE c.depth = 0 "
        "RETURN c.canonical_name ORDER BY c.canonical_name"
    ).get_all()
    roots = [str(row[0]) for row in root_rows]
    if not roots:
        return []

    decision_rows = graph.connection.execute(
        "MATCH (d:Decision)-[:about]->(sub:Context) "
        "RETURN DISTINCT d.file_reference, sub.canonical_name"
    ).get_all()

    counts: dict[str, set[str]] = {root: set() for root in roots}
    for file_reference, canonical in decision_rows:
        root = _project_root(str(canonical))
        if root in counts:
            counts[root].add(str(file_reference))

    return [
        ProjectSummary(canonical_name=root, decision_count=len(counts[root]))
        for root in roots
    ]


def _project_root(canonical_name: str) -> str:
    if not canonical_name:
        return ""
    return canonical_name.split("/", 1)[0]


def _aliases_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return [str(raw)]
