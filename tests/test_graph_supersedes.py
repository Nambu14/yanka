from __future__ import annotations

from pathlib import Path

import pytest

from whyline.graph import (
    get_graph_db,
    index_record_graph,
    init_graph_schema,
    resolve_superseded_claim_id,
)
from whyline.graph.store import clear_graph_db_cache
from whyline.paths import ensure_data_layout, resolve_data_paths
from whyline.records.io import read_record
from whyline.records.models import ClaimSupersedes

pytest.importorskip("ladybug")

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "with-claims.md"
OLD_CLAIM_ID = "records/2026-02-10-redis-session-store.md:c1"


@pytest.fixture(autouse=True)
def _clear_graph_cache() -> None:
    clear_graph_db_cache()
    yield
    clear_graph_db_cache()


def test_resolve_superseded_claim_id_adds_records_prefix() -> None:
    resolved = resolve_superseded_claim_id(
        ClaimSupersedes(file="2026-02-10-redis-session-store.md", claim="c1")
    )
    assert resolved == OLD_CLAIM_ID


def test_resolve_superseded_claim_id_keeps_records_prefix() -> None:
    resolved = resolve_superseded_claim_id(
        ClaimSupersedes(file="records/decision.md", claim="c2")
    )
    assert resolved == "records/decision.md:c2"


def test_index_record_graph_creates_supersedes_edge_and_updates_status(
    tmp_path: Path,
) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    init_graph_schema(graph)
    conn = graph.connection

    conn.execute(
        "MERGE (old:Claim {claim_id: $id}) "
        "ON CREATE SET old.content = 'Redis stores sessions', "
        "old.status = 'active', "
        "old.source_file = 'records/2026-02-10-redis-session-store.md'",
        parameters={"id": OLD_CLAIM_ID},
    )

    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / "2026-05-14-redis-session.md"
    file_ref = index_record_graph(record, graph, paths)
    new_claim_id = f"{file_ref}:c2"

    assert conn.execute(
        "MATCH (new:Claim {claim_id: $new})-[:supersedes]->"
        "(old:Claim {claim_id: $old}) RETURN old.status",
        parameters={"new": new_claim_id, "old": OLD_CLAIM_ID},
    ).get_all() == [["superseded"]]

    assert conn.execute(
        "MATCH (start:Claim {claim_id: $start})-[:supersedes]->(target:Claim) "
        "RETURN target.claim_id",
        parameters={"start": new_claim_id},
    ).get_all() == [[OLD_CLAIM_ID]]


def test_supersedes_chain_two_hops(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    init_graph_schema(graph)
    conn = graph.connection

    for claim_id in (
        "records/chain.md:c0",
        "records/chain.md:c1",
        "records/chain.md:c2",
    ):
        conn.execute(
            "MERGE (cl:Claim {claim_id: $id}) ON CREATE SET cl.status = 'active'",
            parameters={"id": claim_id},
        )
    conn.execute(
        "MATCH (c2:Claim {claim_id: 'records/chain.md:c2'}), "
        "(c1:Claim {claim_id: 'records/chain.md:c1'}) "
        "CREATE (c2)-[:supersedes]->(c1)"
    )
    conn.execute(
        "MATCH (c1:Claim {claim_id: 'records/chain.md:c1'}), "
        "(c0:Claim {claim_id: 'records/chain.md:c0'}) "
        "CREATE (c1)-[:supersedes]->(c0)"
    )

    assert conn.execute(
        "MATCH (start:Claim {claim_id: 'records/chain.md:c2'})"
        "-[:supersedes]->()-[:supersedes]->(target:Claim) "
        "RETURN target.claim_id"
    ).get_all() == [["records/chain.md:c0"]]


def test_index_record_graph_reindex_clears_stale_supersedes_edges(
    tmp_path: Path,
) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    init_graph_schema(graph)
    conn = graph.connection

    conn.execute(
        "MERGE (old:Claim {claim_id: $id}) ON CREATE SET old.status = 'active'",
        parameters={"id": OLD_CLAIM_ID},
    )
    conn.execute(
        "MERGE (stale:Claim {claim_id: 'records/stale.md:c9'}) "
        "ON CREATE SET stale.status = 'active'"
    )

    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / "2026-05-14-redis-session.md"
    index_record_graph(record, graph, paths)

    record.claims[1].supersedes = None
    index_record_graph(record, graph, paths)

    assert conn.execute(
        "MATCH (:Claim {claim_id: $id})-[:supersedes]->() RETURN count(*)",
        parameters={"id": "records/2026-05-14-redis-session.md:c2"},
    ).get_all() == [[0]]
