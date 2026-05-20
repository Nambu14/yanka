from __future__ import annotations

from pathlib import Path

import pytest

from whyline.graph import get_graph_db, init_graph_schema, upsert_context_path
from whyline.graph.context import build_context_levels
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


def test_build_context_levels() -> None:
    levels = build_context_levels(["main-platform", "auth-service"])
    assert [(level.canonical_name, level.depth) for level in levels] == [
        ("main-platform", 0),
        ("main-platform/auth-service", 1),
    ]


def test_upsert_context_path_creates_contains_chain(graph) -> None:
    leaf = upsert_context_path(["acme", "billing"], graph)

    assert leaf == "acme/billing"
    rows = graph.connection.execute(
        "MATCH (root:Context {canonical_name: 'acme'})"
        "-[:contains*]->(leaf:Context {canonical_name: 'acme/billing'}) "
        "RETURN leaf.canonical_name"
    ).get_all()
    assert rows == [["acme/billing"]]
    assert graph.connection.execute(
        "MATCH (n:Context) RETURN count(*)"
    ).get_all() == [[2]]


def test_upsert_context_path_idempotent(graph) -> None:
    upsert_context_path(["acme", "billing"], graph)
    upsert_context_path(["acme", "billing"], graph)

    assert graph.connection.execute(
        "MATCH (n:Context) RETURN count(*)"
    ).get_all() == [[2]]
    assert graph.connection.execute(
        "MATCH ()-[r:contains]->() RETURN count(*)"
    ).get_all() == [[1]]


def test_upsert_context_path_extends_hierarchy(graph) -> None:
    upsert_context_path(["acme", "billing"], graph)
    leaf = upsert_context_path(["acme", "billing", "invoices"], graph)

    assert leaf == "acme/billing/invoices"
    assert graph.connection.execute(
        "MATCH (n:Context) RETURN count(*)"
    ).get_all() == [[3]]


def test_upsert_context_path_empty_raises(graph) -> None:
    with pytest.raises(ValueError, match="empty"):
        upsert_context_path([], graph)
