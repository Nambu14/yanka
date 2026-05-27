from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from yanka.graph import get_graph_db, init_graph_schema, upsert_context_path
from yanka.graph.aliases import append_context_alias, lookup_context_by_alias
from yanka.graph.context import normalize_context_segment
from yanka.graph.store import clear_graph_db_cache
from yanka.ingest.entity_resolution import (
    lookup_context_by_normalized,
    resolve_context_path,
    resolve_record_context_path,
)
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.records.models import Record, RecordBody, RecordStatus, RecordType

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


def test_normalize_context_segment_strips_service_suffix() -> None:
    assert normalize_context_segment("auth-service") == "auth"
    assert normalize_context_segment("Auth Service") == "auth"
    assert normalize_context_segment("authentication-service") == "authentication"


def test_normalize_context_segment_leaves_unrelated_slugs() -> None:
    assert normalize_context_segment("main-platform") == "main-platform"


def test_resolve_context_path_matches_existing_node(graph) -> None:
    upsert_context_path(["main-platform", "auth-service"], graph)

    resolved = resolve_context_path(["main-platform", "auth"], graph)

    assert resolved == ["main-platform", "auth-service"]


def test_lookup_context_by_normalized_scoped_to_parent(graph) -> None:
    upsert_context_path(["main-platform", "auth-service"], graph)
    upsert_context_path(["other-project", "auth-service"], graph)

    match = lookup_context_by_normalized(
        graph,
        normalized_name="auth",
        depth=1,
        parent_canonical="main-platform",
    )

    assert match == "main-platform/auth-service"


def test_resolve_context_path_creates_slug_for_unknown_segment(graph) -> None:
    upsert_context_path(["main-platform", "auth-service"], graph)

    resolved = resolve_context_path(["main-platform", "payments"], graph)

    assert resolved == ["main-platform", "payments"]


def test_resolve_context_path_matches_stored_alias(graph) -> None:
    upsert_context_path(["main-platform", "auth-service"], graph)
    append_context_alias(graph, "main-platform/auth-service", "login service")

    resolved = resolve_context_path(["main-platform", "login service"], graph)

    assert resolved == ["main-platform", "auth-service"]


def test_resolve_context_path_llm_existing_persists_alias(graph) -> None:
    upsert_context_path(["main-platform", "auth-service"], graph)
    calls: list[list[dict[str, str]]] = []

    def fetch(messages: list[dict[str, str]]) -> dict[str, str]:
        calls.append(messages)
        return {
            "outcome": "existing",
            "canonical_name": "main-platform/auth-service",
        }

    resolved = resolve_context_path(
        ["main-platform", "login service"],
        graph,
        fetch_resolution=fetch,
    )

    assert resolved == ["main-platform", "auth-service"]
    assert len(calls) == 1
    assert (
        lookup_context_by_alias(
            graph,
            "login service",
            depth=1,
            parent_canonical="main-platform",
        )
        == "main-platform/auth-service"
    )


def test_resolve_context_path_llm_new_segment(graph) -> None:
    upsert_context_path(["main-platform", "auth-service"], graph)

    def fetch(_messages: list[dict[str, str]]) -> dict[str, str]:
        return {"outcome": "new"}

    resolved = resolve_context_path(
        ["main-platform", "payments-api"],
        graph,
        fetch_resolution=fetch,
    )

    assert resolved == ["main-platform", "payments-api"]


def test_resolve_context_path_uncertain_asks_user(graph) -> None:
    upsert_context_path(["main-platform", "auth-service"], graph)
    upsert_context_path(["main-platform", "payments-api"], graph)
    questions: list[str] = []

    def fetch(messages: list[dict[str, str]]) -> dict[str, str]:
        if len(questions) == 0:
            return {
                "outcome": "uncertain",
                "question": "Auth or payments?",
            }
        return {
            "outcome": "existing",
            "canonical_name": "main-platform/auth-service",
        }

    def ask(question: str) -> str:
        questions.append(question)
        return "auth-service"

    resolved = resolve_context_path(
        ["main-platform", "billing"],
        graph,
        fetch_resolution=fetch,
        ask_user=ask,
    )

    assert resolved == ["main-platform", "auth-service"]
    assert questions == ["Auth or payments?"]


def test_resolve_record_context_path_returns_copy(graph) -> None:
    upsert_context_path(["main-platform", "auth-service"], graph)
    record = Record(
        date=date(2026, 5, 14),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=["main-platform", "auth"],
        decision="Drop Redis",
        body=RecordBody(),
    )

    resolved = resolve_record_context_path(record, graph)

    assert record.context_path == ["main-platform", "auth"]
    assert resolved.context_path == ["main-platform", "auth-service"]
