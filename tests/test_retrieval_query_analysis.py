from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from yanka.llm import PromptName, get_prompt
from yanka.llm.json_parse import JsonParseError
from yanka.retrieval import (
    EXPLORATORY_DEFAULT,
    QueryAnalysisError,
    QueryType,
    StatusFilter,
    analyze_query,
    build_query_analysis_messages,
    query_analysis_from_json,
)

FIXTURES = Path(__file__).parent / "fixtures" / "query_analysis"


@pytest.mark.parametrize(
    ("fixture_name", "expected_type", "semantic_query"),
    [
        ("current_state.json", QueryType.CURRENT_STATE, "session storage"),
        ("historical.json", QueryType.HISTORICAL, "auth approach"),
        ("specific_decision.json", QueryType.SPECIFIC_DECISION, "redis caching"),
        ("exploratory.json", QueryType.EXPLORATORY, "security decisions"),
        ("relationship.json", QueryType.RELATIONSHIP, "k8s migration impact"),
        ("person.json", QueryType.PERSON, None),
    ],
)
def test_query_analysis_from_json_per_query_type(
    fixture_name: str,
    expected_type: QueryType,
    semantic_query: str | None,
) -> None:
    raw = json.loads((FIXTURES / fixture_name).read_text())
    result = query_analysis_from_json(raw)

    assert result.query_type is expected_type
    assert result.semantic_query == semantic_query
    assert isinstance(result.graph_hint, str)
    assert len(result.graph_hint) > 0


def test_current_state_fixture_parses_filters() -> None:
    raw = json.loads((FIXTURES / "current_state.json").read_text())
    result = query_analysis_from_json(raw)

    assert result.filters.project == "main-platform"
    assert result.filters.context_keywords == ["auth", "session"]
    assert result.filters.status_filter is StatusFilter.ACTIVE


def test_historical_fixture_parses_status_all() -> None:
    raw = json.loads((FIXTURES / "historical.json").read_text())
    result = query_analysis_from_json(raw)

    assert result.filters.status_filter is StatusFilter.ALL


def test_person_fixture_parses_people() -> None:
    raw = json.loads((FIXTURES / "person.json").read_text())
    result = query_analysis_from_json(raw)

    assert result.filters.people == ["Carlos"]


def test_query_analysis_from_json_time_range() -> None:
    raw = {
        "query_type": "exploratory",
        "filters": {"time_range": {"after": "2026-04-01", "before": "2026-05-01"}},
        "semantic_query": "deployments",
        "graph_hint": "Recent deployment decisions",
    }
    result = query_analysis_from_json(raw)

    assert result.filters.time_range is not None
    assert result.filters.time_range.after == date(2026, 4, 1)
    assert result.filters.time_range.before == date(2026, 5, 1)


@pytest.mark.parametrize(
    "raw",
    [
        "not an object",
        {"query_type": "unknown_type", "graph_hint": "x"},
        {"query_type": "current_state", "graph_hint": ""},
        {"query_type": "current_state", "filters": "bad", "graph_hint": "ok"},
    ],
)
def test_query_analysis_from_json_invalid_returns_exploratory_default(
    raw: object,
) -> None:
    result = query_analysis_from_json(raw)
    assert result == EXPLORATORY_DEFAULT


def test_build_query_analysis_messages() -> None:
    messages = build_query_analysis_messages("What's our auth approach?")

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == get_prompt(PromptName.QUERY_ANALYSIS)
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "What's our auth approach?"


def test_analyze_query_mocked() -> None:
    raw = json.loads((FIXTURES / "current_state.json").read_text())

    def fetch(_messages: list, **kwargs: object) -> dict:
        return raw

    result = analyze_query(
        "What's our current approach to session storage on main-platform?",
        fetch_json=fetch,
    )

    assert result.query_type is QueryType.CURRENT_STATE
    assert result.semantic_query == "session storage"
    assert result.filters.project == "main-platform"


def test_analyze_query_drops_project_not_mentioned_in_question() -> None:
    raw = json.loads((FIXTURES / "current_state.json").read_text())

    def fetch(_messages: list, **kwargs: object) -> dict:
        return raw

    result = analyze_query(
        "What's our current approach to session storage?",
        fetch_json=fetch,
    )

    assert result.query_type is QueryType.CURRENT_STATE
    assert result.filters.project is None


def test_analyze_query_json_parse_error() -> None:
    def fetch(_messages: list, **kwargs: object) -> dict:
        raise JsonParseError("bad json")

    with pytest.raises(QueryAnalysisError, match="invalid JSON"):
        analyze_query("anything", fetch_json=fetch)


def test_exploratory_default_is_frozen_dataclass() -> None:
    assert EXPLORATORY_DEFAULT.query_type is QueryType.EXPLORATORY
    assert EXPLORATORY_DEFAULT.semantic_query is None
