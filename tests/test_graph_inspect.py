from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from yanka.graph import get_graph_db, index_record_graph, init_graph_schema, list_people, list_projects
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


@pytest.fixture
def paths(tmp_path: Path):
    return ensure_data_layout(resolve_data_paths(tmp_path))


@pytest.fixture
def graph(paths):
    graph_db = get_graph_db(paths)
    init_graph_schema(graph_db)
    return graph_db


def _record(
    paths,
    filename: str,
    *,
    context_path: list[str],
    people: list[str],
) -> Record:
    return Record(
        date=date(2026, 5, 14),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=context_path,
        decision=f"Decision in {filename}",
        people=people,
        claims=[
            Claim(
                id="c1",
                content="claim",
                status=ClaimStatus.ACTIVE,
            )
        ],
        record_complete=True,
        source_path=paths.records_dir / filename,
    )


def test_list_people_with_decision_counts(paths, graph) -> None:
    index_record_graph(
        _record(paths, "a.md", context_path=["alpha"], people=["Carlos"]),
        graph,
        paths,
    )
    index_record_graph(
        _record(paths, "b.md", context_path=["alpha"], people=["Carlos", "Dana"]),
        graph,
        paths,
    )

    people = list_people(graph)

    assert [(person.name, person.decision_count) for person in people] == [
        ("Carlos", 2),
        ("Dana", 1),
    ]
    assert people[1].aliases == []


def test_list_projects_with_subtree_counts(paths, graph) -> None:
    index_record_graph(
        _record(paths, "main.md", context_path=["main-platform", "auth"], people=[]),
        graph,
        paths,
    )
    index_record_graph(
        _record(paths, "legacy.md", context_path=["legacy-api"], people=[]),
        graph,
        paths,
    )

    projects = list_projects(graph)

    assert [(project.canonical_name, project.decision_count) for project in projects] == [
        ("legacy-api", 1),
        ("main-platform", 1),
    ]


def test_list_people_empty_graph(paths, graph) -> None:
    assert list_people(graph) == []


def test_list_projects_empty_graph(paths, graph) -> None:
    assert list_projects(graph) == []
