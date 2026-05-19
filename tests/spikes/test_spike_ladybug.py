"""S.1 — LadybugDB: create graph, insert nodes/edge, Cypher readback."""

from __future__ import annotations

import pytest

ladybug = pytest.importorskip("ladybug")


def test_ladybug_context_contains_graph(tmp_path) -> None:
    db_path = str(tmp_path / "graph")
    db = ladybug.Database(db_path)
    conn = ladybug.Connection(db)

    conn.execute(
        "CREATE NODE TABLE Context("
        "canonical_name STRING PRIMARY KEY, "
        "normalized_name STRING, "
        "depth INT64)"
    )
    conn.execute("CREATE REL TABLE contains(FROM Context TO Context)")

    conn.execute(
        "CREATE (p:Context {canonical_name: 'acme', normalized_name: 'acme', depth: 0})"
    )
    conn.execute(
        "CREATE (c:Context {canonical_name: 'acme/billing', "
        "normalized_name: 'billing', depth: 1})"
    )
    conn.execute(
        "MATCH (p:Context {canonical_name: 'acme'}), "
        "(c:Context {canonical_name: 'acme/billing'}) "
        "CREATE (p)-[:contains]->(c)"
    )

    result = conn.execute(
        "MATCH (parent:Context)-[:contains]->(child:Context) "
        "RETURN parent.canonical_name, child.canonical_name"
    )
    rows = result.get_all()
    assert rows == [["acme", "acme/billing"]]
