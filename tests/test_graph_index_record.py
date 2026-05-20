from __future__ import annotations

from pathlib import Path

import pytest

from whyline.graph import get_graph_db, index_record_graph, init_graph_schema
from whyline.graph.store import clear_graph_db_cache
from whyline.paths import ensure_data_layout, resolve_data_paths
from whyline.records.io import read_record

pytest.importorskip("ladybug")

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "with-claims.md"


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


def _record_with_source(paths, filename: str = "2026-05-14-redis-session.md"):
    record = read_record(FIXTURE).record
    record.source_path = paths.records_dir / filename
    record.people = ["Carlos"]
    return record


def test_index_record_graph_links_decision_context_claims_people(
    tmp_path: Path,
) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    init_graph_schema(graph)
    record = _record_with_source(paths)

    file_ref = index_record_graph(record, graph, paths)

    assert file_ref == "records/2026-05-14-redis-session.md"
    conn = graph.connection
    assert conn.execute(
        "MATCH (d:Decision {file_reference: $ref})-[:about]->"
        "(c:Context {canonical_name: 'main-platform/auth-service'}) "
        "RETURN d.summary",
        parameters={"ref": file_ref},
    ).get_all() == [["Drop Redis for session storage"]]
    assert conn.execute(
        "MATCH (d:Decision {file_reference: $ref})-[:has_claim]->"
        "(cl:Claim) RETURN cl.claim_id ORDER BY cl.claim_id",
        parameters={"ref": file_ref},
    ).get_all() == [
        [f"{file_ref}:c1"],
        [f"{file_ref}:c2"],
    ]
    assert conn.execute(
        "MATCH (d:Decision {file_reference: $ref})-[:involves]->"
        "(p:Person {name: 'Carlos'}) RETURN p.name",
        parameters={"ref": file_ref},
    ).get_all() == [["Carlos"]]


def test_index_record_graph_reindex_updates_decision(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    init_graph_schema(graph)
    record = _record_with_source(paths, "decision.md")

    index_record_graph(record, graph, paths)
    record.decision = "PostgreSQL only for sessions"
    index_record_graph(record, graph, paths)

    summary = graph.connection.execute(
        "MATCH (d:Decision {file_reference: 'records/decision.md'}) "
        "RETURN d.summary"
    ).get_all()
    assert summary == [["PostgreSQL only for sessions"]]
    assert graph.connection.execute(
        "MATCH (d:Decision) RETURN count(*)"
    ).get_all() == [[1]]
