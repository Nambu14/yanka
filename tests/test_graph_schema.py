from __future__ import annotations

from pathlib import Path

import pytest

from whyline.graph import get_graph_db, init_graph_schema
from whyline.graph.store import clear_graph_db_cache
from whyline.paths import ensure_data_layout, resolve_data_paths

pytest.importorskip("ladybug")


@pytest.fixture(autouse=True)
def _clear_graph_cache() -> None:
    clear_graph_db_cache()
    yield
    clear_graph_db_cache()


@pytest.fixture
def graph(tmp_path: Path):
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph_db = get_graph_db(paths)
    init_graph_schema(graph_db)
    return graph_db


def test_init_graph_schema_idempotent(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph_db = get_graph_db(paths)
    init_graph_schema(graph_db)
    init_graph_schema(graph_db)


def test_insert_each_node_type(graph) -> None:
    conn = graph.connection
    conn.execute(
        "CREATE (c:Context {"
        "canonical_name: 'acme', normalized_name: 'acme', depth: 0, aliases: []"
        "})"
    )
    conn.execute(
        "CREATE (d:Decision {"
        "file_reference: 'records/2026-05-14-auth.md', "
        "date: date('2026-05-14'), type: 'decision', status: 'active', "
        "summary: 'Use JWT', tags: ['auth']"
        "})"
    )
    conn.execute(
        "CREATE (cl:Claim {"
        "claim_id: 'records/2026-05-14-auth.md:c1', "
        "content: 'Sessions use JWT', status: 'active', "
        "source_file: 'records/2026-05-14-auth.md'"
        "})"
    )
    conn.execute(
        "CREATE (p:Person {name: 'Ada', aliases: ['Adelaide']})"
    )

    assert conn.execute(
        "MATCH (c:Context {canonical_name: 'acme'}) RETURN c.depth"
    ).get_all() == [[0]]
    assert conn.execute(
        "MATCH (d:Decision {file_reference: 'records/2026-05-14-auth.md'}) "
        "RETURN d.summary"
    ).get_all() == [["Use JWT"]]
    assert conn.execute(
        "MATCH (cl:Claim {claim_id: 'records/2026-05-14-auth.md:c1'}) "
        "RETURN cl.content"
    ).get_all() == [["Sessions use JWT"]]
    assert conn.execute(
        "MATCH (p:Person {name: 'Ada'}) RETURN p.aliases"
    ).get_all() == [[["Adelaide"]]]


def test_insert_each_relationship_type(graph) -> None:
    conn = graph.connection
    conn.execute(
        "CREATE (root:Context {"
        "canonical_name: 'acme', normalized_name: 'acme', depth: 0, aliases: []"
        "})"
    )
    conn.execute(
        "CREATE (child:Context {"
        "canonical_name: 'acme/auth', normalized_name: 'auth', depth: 1, "
        "aliases: []"
        "})"
    )
    conn.execute(
        "CREATE (d:Decision {"
        "file_reference: 'records/decision.md', "
        "date: date('2026-05-14'), type: 'decision', status: 'active', "
        "summary: 'Summary', tags: []"
        "})"
    )
    conn.execute(
        "CREATE (cl:Claim {"
        "claim_id: 'records/decision.md:c1', content: 'Claim text', "
        "status: 'active', source_file: 'records/decision.md'"
        "})"
    )
    conn.execute(
        "CREATE (old:Claim {"
        "claim_id: 'records/decision.md:c0', content: 'Old claim', "
        "status: 'superseded', source_file: 'records/decision.md'"
        "})"
    )
    conn.execute("CREATE (p:Person {name: 'Bob', aliases: []})")

    conn.execute(
        "MATCH (root:Context {canonical_name: 'acme'}), "
        "(child:Context {canonical_name: 'acme/auth'}) "
        "CREATE (root)-[:contains]->(child)"
    )
    conn.execute(
        "MATCH (d:Decision {file_reference: 'records/decision.md'}), "
        "(child:Context {canonical_name: 'acme/auth'}) "
        "CREATE (d)-[:about]->(child)"
    )
    conn.execute(
        "MATCH (d:Decision {file_reference: 'records/decision.md'}), "
        "(cl:Claim {claim_id: 'records/decision.md:c1'}) "
        "CREATE (d)-[:has_claim]->(cl)"
    )
    conn.execute(
        "MATCH (new:Claim {claim_id: 'records/decision.md:c1'}), "
        "(old:Claim {claim_id: 'records/decision.md:c0'}) "
        "CREATE (new)-[:supersedes]->(old)"
    )
    conn.execute(
        "MATCH (d:Decision {file_reference: 'records/decision.md'}), "
        "(p:Person {name: 'Bob'}) "
        "CREATE (d)-[:involves]->(p)"
    )

    assert conn.execute(
        "MATCH (:Context)-[:contains]->(:Context) RETURN count(*)"
    ).get_all() == [[1]]
    assert conn.execute(
        "MATCH (:Decision)-[:about]->(:Context) RETURN count(*)"
    ).get_all() == [[1]]
    assert conn.execute(
        "MATCH (:Decision)-[:has_claim]->(:Claim) RETURN count(*)"
    ).get_all() == [[1]]
    assert conn.execute(
        "MATCH (:Claim)-[:supersedes]->(:Claim) RETURN count(*)"
    ).get_all() == [[1]]
    assert conn.execute(
        "MATCH (:Decision)-[:involves]->(:Person) RETURN count(*)"
    ).get_all() == [[1]]
