"""Query analysis for retrieval — spec §8 step 1, prompt 4."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from yanka.config import LlmConfig
from yanka.llm import JsonParseError, fetch_llm_json, get_prompt
from yanka.llm.client import LlmError
from yanka.llm.prompts import PromptName
from yanka.paths import DataPaths
from yanka.retrieval_enums import QueryType, StatusFilter


@dataclass(frozen=True)
class TimeRange:
    after: date | None = None
    before: date | None = None


@dataclass
class QueryFilters:
    project: str | None = None
    context_keywords: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    time_range: TimeRange | None = None
    status_filter: StatusFilter | None = None


@dataclass(frozen=True)
class QueryAnalysis:
    query_type: QueryType
    filters: QueryFilters
    semantic_query: str | None
    graph_hint: str


EXPLORATORY_DEFAULT = QueryAnalysis(
    query_type=QueryType.EXPLORATORY,
    filters=QueryFilters(),
    semantic_query=None,
    graph_hint="List recent decisions across all projects",
)


class QueryAnalysisError(LlmError):
    """Query analysis LLM call or response validation failed."""


def build_query_analysis_messages(question: str) -> list[dict[str, str]]:
    """Build the message list for the query analysis LLM call."""
    return [
        {"role": "system", "content": get_prompt(PromptName.QUERY_ANALYSIS)},
        {"role": "user", "content": question},
    ]


def query_analysis_from_json(raw: Any) -> QueryAnalysis:
    """Parse Prompt 4 JSON into QueryAnalysis; vague/invalid → exploratory default."""
    if not isinstance(raw, dict):
        return EXPLORATORY_DEFAULT
    try:
        return _parse_query_analysis(raw)
    except ValueError:
        return EXPLORATORY_DEFAULT


def analyze_query(
    question: str,
    *,
    paths: DataPaths | None = None,
    config: LlmConfig | None = None,
    fetch_json: Callable[..., Any] | None = None,
) -> QueryAnalysis:
    """Run query analysis (Prompt 4) and return structured retrieval filters."""
    fetch = fetch_json if fetch_json is not None else fetch_llm_json
    messages = build_query_analysis_messages(question)
    try:
        data = fetch(
            messages,
            expect="object",
            paths=paths,
            config=config,
        )
    except JsonParseError as exc:
        msg = "query analysis returned invalid JSON"
        raise QueryAnalysisError(msg) from exc

    return _drop_unmentioned_project(question, query_analysis_from_json(data))


def _parse_query_analysis(raw: dict[str, Any]) -> QueryAnalysis:
    query_type = _parse_query_type(raw.get("query_type"))
    filters = _parse_filters(raw.get("filters"))
    semantic_query = _parse_semantic_query(raw.get("semantic_query"))
    graph_hint = _parse_graph_hint(raw.get("graph_hint"))
    return QueryAnalysis(
        query_type=query_type,
        filters=filters,
        semantic_query=semantic_query,
        graph_hint=graph_hint,
    )


def _drop_unmentioned_project(question: str, analysis: QueryAnalysis) -> QueryAnalysis:
    project = analysis.filters.project
    if project is None:
        return analysis
    if _contains_project_reference(question, project):
        return analysis
    filters = replace(analysis.filters, project=None)
    return replace(analysis, filters=filters)


def _contains_project_reference(question: str, project: str) -> bool:
    normalized_question = _normalize_project_reference(question)
    normalized_project = _normalize_project_reference(project)
    return normalized_project in normalized_question


def _normalize_project_reference(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").replace("_", " ").split())


def _parse_query_type(value: Any) -> QueryType:
    try:
        return QueryType(str(value))
    except ValueError as exc:
        msg = f"invalid query_type: {value!r}"
        raise ValueError(msg) from exc


def _parse_filters(value: Any) -> QueryFilters:
    if value is None:
        return QueryFilters()
    if not isinstance(value, dict):
        msg = "filters must be a mapping"
        raise ValueError(msg)

    project = _parse_optional_str(value.get("project"))
    context_keywords = _parse_optional_string_list(value.get("context_keywords"))
    people = _parse_optional_string_list(value.get("people"))
    time_range = _parse_time_range(value.get("time_range"))
    status_filter = _parse_status_filter(value.get("status_filter"))

    return QueryFilters(
        project=project,
        context_keywords=context_keywords,
        people=people,
        time_range=time_range,
        status_filter=status_filter,
    )


def _parse_time_range(value: Any) -> TimeRange | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        msg = "time_range must be a mapping"
        raise ValueError(msg)
    after = _parse_optional_date(value.get("after"), "time_range.after")
    before = _parse_optional_date(value.get("before"), "time_range.before")
    if after is None and before is None:
        return None
    return TimeRange(after=after, before=before)


def _parse_status_filter(value: Any) -> StatusFilter | None:
    if value is None:
        return None
    try:
        return StatusFilter(str(value))
    except ValueError as exc:
        msg = f"invalid status_filter: {value!r}"
        raise ValueError(msg) from exc


def _parse_semantic_query(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        msg = "semantic_query must be a string or null"
        raise ValueError(msg)
    stripped = value.strip()
    return stripped if stripped else None


def _parse_graph_hint(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        msg = "graph_hint must be a non-empty string"
        raise ValueError(msg)
    return value.strip()


def _parse_optional_date(value: Any, field_name: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        msg = f"{field_name} must be YYYY-MM-DD or null"
        raise ValueError(msg)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        msg = f"{field_name} must be YYYY-MM-DD"
        raise ValueError(msg) from exc


def _parse_optional_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = "list must be a list of strings"
        raise ValueError(msg)
    return list(value)


def _parse_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        msg = "value must be a string or null"
        raise ValueError(msg)
    stripped = value.strip()
    return stripped if stripped else None
