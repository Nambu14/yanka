"""Graph-assisted conflict candidate search — spec §7 step 6."""

from __future__ import annotations

from typing import Any

from whyline.graph.context import build_context_levels
from whyline.graph.store import GraphDb


def graph_conflict_candidates(
    context_path: list[str],
    graph: GraphDb,
) -> list[dict[str, Any]]:
    """Active claims on decisions in the context subtree for ``context_path``.

    Subtree = leaf canonical_name (``/``-joined segments) plus any context whose
    ``canonical_name`` extends that prefix. Matches vector ``context_path_prefix``.
    """
    if not context_path:
        msg = "context_path must not be empty"
        raise ValueError(msg)

    leaf = build_context_levels(context_path)[-1].canonical_name
    prefix = f"{leaf}/"

    rows = graph.connection.execute(
        "MATCH (c:Context) "
        "WHERE c.canonical_name = $leaf OR c.canonical_name STARTS WITH $prefix "
        "WITH c "
        "MATCH (d:Decision)-[:about]->(c) "
        "MATCH (d)-[:has_claim]->(cl:Claim) "
        "WHERE cl.status = 'active' "
        "RETURN DISTINCT cl.claim_id, cl.content, cl.source_file, cl.status "
        "ORDER BY cl.claim_id",
        parameters={"leaf": leaf, "prefix": prefix},
    ).get_all()

    return [
        {
            "claim_id": row[0],
            "content": row[1],
            "source_file": row[2],
            "status": row[3],
        }
        for row in rows
    ]
