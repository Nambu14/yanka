from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from whyline.graph import get_graph_db, index_record_graph, init_graph_schema, upsert_context_path
from whyline.graph.store import clear_graph_db_cache
from whyline.paths import ensure_data_layout, resolve_data_paths
from whyline.records.models import (
    Claim,
    ClaimStatus,
    Record,
    RecordStatus,
    RecordType,
)
from whyline.retrieval.graph_retrieve import GraphRetrievalHit, retrieve_from_graph
from whyline.retrieval.query_analysis import (
    QueryAnalysis,
    QueryFilters,
    QueryType,
    StatusFilter,
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
    decision: str,
    status: RecordStatus = RecordStatus.ACTIVE,
    tags: list[str] | None = None,
    people: list[str] | None = None,
    claim_status: ClaimStatus = ClaimStatus.ACTIVE,
) -> Record:
    return Record(
        date=date(2026, 5, 14),
        type=RecordType.DECISION,
        status=status,
        context_path=context_path,
        decision=decision,
        tags=tags or [],
        people=people or [],
        claims=[
            Claim(
                id="c1",
                content=f"Claim for {filename}",
                status=claim_status,
            )
        ],
        record_complete=True,
        source_path=paths.records_dir / filename,
    )


def _seed_graph(paths, graph) -> None:
    init_graph_schema(graph)
    index_record_graph(
        _record(
            paths,
            "auth-active.md",
            context_path=["main-platform", "auth-service"],
            decision="Use JWT for sessions",
        ),
        graph,
        paths,
    )
    index_record_graph(
        _record(
            paths,
            "auth-old.md",
            context_path=["main-platform", "auth-service"],
            decision="Legacy cookie sessions",
            status=RecordStatus.SUPERSEDED,
        ),
        graph,
        paths,
    )
    index_record_graph(
        _record(
            paths,
            "billing.md",
            context_path=["main-platform", "billing"],
            decision="Stripe billing integration",
            tags=["payments"],
        ),
        graph,
        paths,
    )
    index_record_graph(
        _record(
            paths,
            "k8s.md",
            context_path=["main-platform", "infra"],
            decision="Kubernetes migration completed",
            tags=["kubernetes", "migration"],
        ),
        graph,
        paths,
    )
    index_record_graph(
        _record(
            paths,
            "carlos-auth.md",
            context_path=["main-platform", "auth-service"],
            decision="Carlos led auth hardening",
            people=["Carlos"],
        ),
        graph,
        paths,
    )


def _analysis(
    query_type: QueryType,
    *,
    project: str | None = "main-platform",
    context_keywords: list[str] | None = None,
    people: list[str] | None = None,
    status_filter: StatusFilter | None = None,
    semantic_query: str | None = None,
) -> QueryAnalysis:
    return QueryAnalysis(
        query_type=query_type,
        filters=QueryFilters(
            project=project,
            context_keywords=context_keywords or [],
            people=people or [],
            status_filter=status_filter,
        ),
        semantic_query=semantic_query,
        graph_hint="test",
    )


def test_current_state_returns_only_active_auth_decisions(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    _seed_graph(paths, graph)

    hits = retrieve_from_graph(
        _analysis(QueryType.CURRENT_STATE, context_keywords=["auth"]),
        graph,
        paths,
        limit=10,
    )

    refs = {hit.file_reference for hit in hits}
    assert "records/auth-active.md" in refs
    assert "records/auth-old.md" not in refs
    assert "records/billing.md" not in refs
    assert all(hit.status == "active" for hit in hits)
    assert all(isinstance(hit, GraphRetrievalHit) for hit in hits)


def test_historical_includes_superseded_in_subtree(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    _seed_graph(paths, graph)

    hits = retrieve_from_graph(
        _analysis(
            QueryType.HISTORICAL,
            context_keywords=["auth"],
            status_filter=StatusFilter.ALL,
        ),
        graph,
        paths,
        limit=10,
    )

    refs = {hit.file_reference for hit in hits}
    assert "records/auth-active.md" in refs
    assert "records/auth-old.md" in refs


def test_historical_without_context_filters_searches_all_contexts(
    tmp_path: Path,
) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    _seed_graph(paths, graph)

    hits = retrieve_from_graph(
        _analysis(
            QueryType.HISTORICAL,
            project=None,
            context_keywords=[],
            status_filter=StatusFilter.ALL,
        ),
        graph,
        paths,
        limit=10,
    )

    refs = {hit.file_reference for hit in hits}
    assert "records/auth-active.md" in refs
    assert "records/k8s.md" in refs


def test_exploratory_scoped_to_project(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    _seed_graph(paths, graph)

    hits = retrieve_from_graph(
        _analysis(QueryType.EXPLORATORY, context_keywords=[]),
        graph,
        paths,
        limit=10,
    )

    refs = {hit.file_reference for hit in hits}
    assert "records/auth-active.md" in refs
    assert "records/k8s.md" in refs
    assert all(hit.context_canonical.startswith("main-platform") for hit in hits)


def test_specific_decision_matches_summary_keyword(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    _seed_graph(paths, graph)

    hits = retrieve_from_graph(
        _analysis(
            QueryType.SPECIFIC_DECISION,
            context_keywords=[],
            semantic_query="kubernetes migration",
        ),
        graph,
        paths,
        limit=5,
    )

    assert [hit.file_reference for hit in hits] == ["records/k8s.md"]


def test_specific_decision_matches_file_reference(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    _seed_graph(paths, graph)

    hits = retrieve_from_graph(
        _analysis(
            QueryType.SPECIFIC_DECISION,
            context_keywords=["billing.md"],
            semantic_query=None,
        ),
        graph,
        paths,
        limit=5,
    )

    assert [hit.file_reference for hit in hits] == ["records/billing.md"]


def test_relationship_expands_from_anchor_context(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    _seed_graph(paths, graph)

    hits = retrieve_from_graph(
        _analysis(
            QueryType.RELATIONSHIP,
            context_keywords=["kubernetes"],
            semantic_query="kubernetes migration",
        ),
        graph,
        paths,
        limit=10,
    )

    refs = {hit.file_reference for hit in hits}
    assert "records/k8s.md" in refs
    assert all(ref.endswith(".md") for ref in refs)


def test_person_returns_involves_decisions(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    _seed_graph(paths, graph)

    hits = retrieve_from_graph(
        _analysis(QueryType.PERSON, people=["Carlos"]),
        graph,
        paths,
        limit=10,
    )

    assert [hit.file_reference for hit in hits] == ["records/carlos-auth.md"]


def test_person_without_people_returns_empty(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    _seed_graph(paths, graph)

    hits = retrieve_from_graph(
        _analysis(QueryType.PERSON, people=[]),
        graph,
        paths,
    )

    assert hits == []


def test_empty_graph_returns_empty(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    init_graph_schema(graph)

    hits = retrieve_from_graph(
        _analysis(QueryType.CURRENT_STATE, context_keywords=["auth"]),
        graph,
        paths,
    )

    assert hits == []


def test_descendant_context_included_for_current_state(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)
    init_graph_schema(graph)
    upsert_context_path(["main-platform", "auth-service", "oauth"], graph)
    index_record_graph(
        _record(
            paths,
            "oauth.md",
            context_path=["main-platform", "auth-service", "oauth"],
            decision="OAuth2 authorization code flow",
        ),
        graph,
        paths,
    )

    hits = retrieve_from_graph(
        _analysis(QueryType.CURRENT_STATE, context_keywords=["auth"]),
        graph,
        paths,
        limit=10,
    )

    assert any(hit.file_reference == "records/oauth.md" for hit in hits)
