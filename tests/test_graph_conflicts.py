from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from yanka.graph import (
    get_graph_db,
    graph_conflict_candidates,
    index_record_graph,
    init_graph_schema,
    upsert_context_path,
)
from yanka.graph.store import clear_graph_db_cache
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.records.models import (
    Claim,
    ClaimStatus,
    Record,
    RecordStatus,
    RecordType,
)

pytest.importorskip("ladybug")


@pytest.fixture(autouse=True)
def _clear_graph_cache() -> None:
    clear_graph_db_cache()
    yield
    clear_graph_db_cache()


def _record(
    paths,
    filename: str,
    *,
    context_path: list[str],
    claim_content: str,
    claim_status: ClaimStatus = ClaimStatus.ACTIVE,
) -> Record:
    return Record(
        date=date(2026, 5, 14),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=context_path,
        decision=f"Decision in {filename}",
        claims=[
            Claim(
                id="c1",
                content=claim_content,
                status=claim_status,
            )
        ],
        record_complete=True,
        source_path=paths.records_dir / filename,
    )


def test_graph_conflict_candidates_returns_active_claims_in_subtree(
    tmp_path: Path,
) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    init_graph_schema(graph)

    index_record_graph(
        _record(
            paths,
            "auth-a.md",
            context_path=["main-platform", "auth-service"],
            claim_content="JWT in cookies",
        ),
        graph,
        paths,
    )
    index_record_graph(
        _record(
            paths,
            "auth-b.md",
            context_path=["main-platform", "auth-service"],
            claim_content="Sessions in PostgreSQL",
        ),
        graph,
        paths,
    )
    index_record_graph(
        _record(
            paths,
            "billing.md",
            context_path=["main-platform", "billing"],
            claim_content="Stripe for invoices",
        ),
        graph,
        paths,
    )

    candidates = graph_conflict_candidates(
        ["main-platform", "auth-service"],
        graph,
    )

    assert [row["claim_id"] for row in candidates] == [
        "records/auth-a.md:c1",
        "records/auth-b.md:c1",
    ]
    assert all(row["status"] == "active" for row in candidates)


def test_graph_conflict_candidates_includes_descendant_contexts(
    tmp_path: Path,
) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    init_graph_schema(graph)

    upsert_context_path(["main-platform", "auth-service", "oauth"], graph)
    index_record_graph(
        _record(
            paths,
            "oauth.md",
            context_path=["main-platform", "auth-service", "oauth"],
            claim_content="OAuth2 authorization code flow",
        ),
        graph,
        paths,
    )

    candidates = graph_conflict_candidates(
        ["main-platform", "auth-service"],
        graph,
    )

    assert candidates == [
        {
            "claim_id": "records/oauth.md:c1",
            "content": "OAuth2 authorization code flow",
            "source_file": "records/oauth.md",
            "status": "active",
        }
    ]


def test_graph_conflict_candidates_excludes_non_active_claims(
    tmp_path: Path,
) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    init_graph_schema(graph)

    index_record_graph(
        _record(
            paths,
            "tentative.md",
            context_path=["main-platform", "auth-service"],
            claim_content="Maybe rotate keys",
            claim_status=ClaimStatus.TENTATIVE,
        ),
        graph,
        paths,
    )
    graph.connection.execute(
        "MERGE (cl:Claim {claim_id: 'records/superseded.md:c1'}) "
        "ON CREATE SET cl.content = 'Old policy', cl.status = 'active', "
        "cl.source_file = 'records/superseded.md'"
    )
    graph.connection.execute(
        "MATCH (cl:Claim {claim_id: 'records/superseded.md:c1'}) "
        "SET cl.status = 'superseded'"
    )
    graph.connection.execute(
        "MERGE (d:Decision {file_reference: 'records/superseded.md'}) "
        "ON CREATE SET d.summary = 'Old', d.type = 'decision', "
        "d.status = 'active', d.tags = []"
    )
    graph.connection.execute(
        "MATCH (d:Decision {file_reference: 'records/superseded.md'}), "
        "(c:Context {canonical_name: 'main-platform/auth-service'}) "
        "MERGE (d)-[:about]->(c)"
    )
    graph.connection.execute(
        "MATCH (d:Decision {file_reference: 'records/superseded.md'}), "
        "(cl:Claim {claim_id: 'records/superseded.md:c1'}) "
        "MERGE (d)-[:has_claim]->(cl)"
    )

    assert graph_conflict_candidates(["main-platform", "auth-service"], graph) == []
