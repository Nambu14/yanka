"""Context path entity resolution — spec §9."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from yanka.config import LlmConfig
from yanka.graph.aliases import (
    ContextCandidate,
    append_context_alias,
    list_context_candidates,
    lookup_context_by_alias,
)
from yanka.graph.context import normalize_context_segment
from yanka.graph.store import GraphDb
from yanka.ingest.pipeline_stages import ENTITY_RESOLUTION_DEGRADE_WARNING
from yanka.llm import fetch_llm_json, get_prompt
from yanka.llm.client import LlmError
from yanka.llm.prompts import PromptName
from yanka.paths import DataPaths
from yanka.records.models import Record
from yanka.records.slug import slugify_text

FetchResolution = Callable[[list[dict[str, str]]], dict[str, Any]]
AskUser = Callable[[str], str]


class EntityResolutionError(LlmError):
    """Entity resolution could not map a context segment."""


@dataclass(frozen=True)
class EntityResolutionOutcome:
    outcome: str
    canonical_name: str | None = None
    question: str | None = None


def resolve_record_context_path(
    record: Record,
    graph: GraphDb,
    **kwargs: Any,
) -> Record:
    """Return a copy of the record with a resolved context_path."""
    resolved = resolve_context_path(record.context_path, graph, **kwargs)
    return replace(record, context_path=resolved)


def resolve_record_context_path_degrading(
    record: Record,
    graph: GraphDb,
    **kwargs: Any,
) -> tuple[Record, list[str]]:
    """Resolve context path; on ``LlmError``, fall back to slugified new nodes."""
    try:
        return resolve_record_context_path(record, graph, **kwargs), []
    except LlmError:
        fallback_kwargs = dict(kwargs)
        fallback_kwargs["fetch_resolution"] = None
        fallback_kwargs.pop("ask_user", None)
        resolved = resolve_context_path(record.context_path, graph, **fallback_kwargs)
        warning = ENTITY_RESOLUTION_DEGRADE_WARNING
        return replace(record, context_path=resolved), [warning]


def resolve_context_path(
    segments: list[str],
    graph: GraphDb,
    *,
    paths: DataPaths | None = None,
    llm_config: LlmConfig | None = None,
    fetch_resolution: FetchResolution | None = None,
    ask_user: AskUser | None = None,
) -> list[str]:
    """Map context segments onto graph nodes (§9).

    Without ``fetch_resolution``, only normalized exact match (v1).
    With ``fetch_resolution``, also checks aliases, LLM fallback, and user ask.
    """
    if not segments:
        msg = "context_path must not be empty"
        raise ValueError(msg)

    resolved: list[str] = []
    parent_canonical: str | None = None

    for depth, raw_segment in enumerate(segments):
        slug, parent_canonical = _resolve_segment(
            raw_segment,
            depth=depth,
            parent_canonical=parent_canonical,
            graph=graph,
            paths=paths,
            llm_config=llm_config,
            fetch_resolution=fetch_resolution,
            ask_user=ask_user,
        )
        resolved.append(slug)

    return resolved


def lookup_context_by_normalized(
    graph: GraphDb,
    *,
    normalized_name: str,
    depth: int,
    parent_canonical: str | None = None,
) -> str | None:
    """Return matching Context canonical_name, or None if no exact match."""
    escaped_norm = _escape_cypher_string(normalized_name)

    if depth == 0:
        query = (
            f"MATCH (c:Context) "
            f"WHERE c.normalized_name = '{escaped_norm}' AND c.depth = 0 "
            f"RETURN c.canonical_name ORDER BY c.canonical_name"
        )
    else:
        if parent_canonical is None:
            return None
        escaped_parent = _escape_cypher_string(parent_canonical)
        query = (
            f"MATCH (parent:Context {{canonical_name: '{escaped_parent}'}})"
            f"-[:contains]->(c:Context) "
            f"WHERE c.normalized_name = '{escaped_norm}' AND c.depth = {depth} "
            f"RETURN c.canonical_name ORDER BY c.canonical_name"
        )

    rows = graph.connection.execute(query).get_all()
    if not rows:
        return None
    return str(rows[0][0])


def build_entity_resolution_messages(
    raw_segment: str,
    *,
    depth: int,
    parent_canonical: str | None,
    candidates: list[ContextCandidate],
    user_clarification: str | None = None,
) -> list[dict[str, str]]:
    """Build LLM messages for one context segment resolution attempt."""
    parent_line = parent_canonical if parent_canonical else "(root level)"
    candidate_lines = [
        {
            "canonical_name": c.canonical_name,
            "normalized_name": c.normalized_name,
            "aliases": c.aliases,
        }
        for c in candidates
    ]
    payload: dict[str, Any] = {
        "phrase": raw_segment,
        "depth": depth,
        "parent_canonical": parent_canonical,
        "parent_context": parent_line,
        "candidates": candidate_lines,
    }
    if user_clarification is not None:
        payload["user_clarification"] = user_clarification

    return [
        {"role": "system", "content": get_prompt(PromptName.ENTITY_CONTEXT_RESOLUTION)},
        {
            "role": "user",
            "content": json.dumps(payload, indent=2),
        },
    ]


def _resolve_segment(
    raw_segment: str,
    *,
    depth: int,
    parent_canonical: str | None,
    graph: GraphDb,
    paths: DataPaths | None,
    llm_config: LlmConfig | None,
    fetch_resolution: FetchResolution | None,
    ask_user: AskUser | None,
) -> tuple[str, str]:
    """Return (segment slug, canonical_name for next parent scope)."""
    normalized = normalize_context_segment(raw_segment)

    match = lookup_context_by_normalized(
        graph,
        normalized_name=normalized,
        depth=depth,
        parent_canonical=parent_canonical,
    )
    if match is not None:
        return _segment_slug_from_canonical(match), match

    match = lookup_context_by_alias(
        graph,
        raw_segment,
        depth=depth,
        parent_canonical=parent_canonical,
    )
    if match is not None:
        return _segment_slug_from_canonical(match), match

    if fetch_resolution is not None:
        candidates = list_context_candidates(
            graph, depth=depth, parent_canonical=parent_canonical
        )
        if candidates:
            fetch = fetch_resolution
            resolved = _resolve_with_llm(
                raw_segment,
                depth=depth,
                parent_canonical=parent_canonical,
                candidates=candidates,
                graph=graph,
                paths=paths,
                llm_config=llm_config,
                fetch=fetch,
                ask_user=ask_user,
            )
            return (
                _segment_slug_from_canonical(resolved),
                resolved,
            )

    slug = slugify_text(raw_segment)
    canonical = slug if parent_canonical is None else f"{parent_canonical}/{slug}"
    return slug, canonical


def _resolve_with_llm(
    raw_segment: str,
    *,
    depth: int,
    parent_canonical: str | None,
    candidates: list[ContextCandidate],
    graph: GraphDb,
    paths: DataPaths | None,
    llm_config: LlmConfig | None,
    fetch: FetchResolution,
    ask_user: AskUser | None,
) -> str:
    messages = build_entity_resolution_messages(
        raw_segment,
        depth=depth,
        parent_canonical=parent_canonical,
        candidates=candidates,
    )
    data = fetch(messages)
    outcome = _parse_resolution_payload(data)

    if outcome.outcome == "uncertain":
        if ask_user is None:
            msg = "Entity resolution is uncertain but no ask_user callback was provided"
            raise EntityResolutionError(msg)
        if not outcome.question:
            msg = "Entity resolution returned uncertain without a question"
            raise EntityResolutionError(msg)
        answer = ask_user(outcome.question)
        messages = build_entity_resolution_messages(
            raw_segment,
            depth=depth,
            parent_canonical=parent_canonical,
            candidates=candidates,
            user_clarification=answer,
        )
        data = fetch(messages)
        outcome = _parse_resolution_payload(data)

    if outcome.outcome == "existing":
        if outcome.canonical_name is None:
            msg = "Entity resolution returned existing without canonical_name"
            raise EntityResolutionError(msg)
        _validate_canonical_choice(outcome.canonical_name, candidates)
        append_context_alias(graph, outcome.canonical_name, raw_segment)
        return outcome.canonical_name

    if outcome.outcome == "new":
        slug = slugify_text(raw_segment)
        if parent_canonical is None:
            return slug
        return f"{parent_canonical}/{slug}"

    msg = f"Unexpected entity resolution outcome: {outcome.outcome!r}"
    raise EntityResolutionError(msg)


def _parse_resolution_payload(data: Any) -> EntityResolutionOutcome:
    if not isinstance(data, dict):
        msg = "Entity resolution JSON must be an object"
        raise EntityResolutionError(msg)

    outcome = data.get("outcome")
    if outcome not in ("existing", "new", "uncertain"):
        msg = f"Invalid entity resolution outcome: {outcome!r}"
        raise EntityResolutionError(msg)

    canonical_name = data.get("canonical_name")
    if canonical_name is not None and not isinstance(canonical_name, str):
        msg = "canonical_name must be a string when present"
        raise EntityResolutionError(msg)

    question = data.get("question")
    if question is not None and not isinstance(question, str):
        msg = "question must be a string when present"
        raise EntityResolutionError(msg)

    return EntityResolutionOutcome(
        outcome=outcome,
        canonical_name=canonical_name,
        question=question,
    )


def _validate_canonical_choice(
    canonical_name: str,
    candidates: list[ContextCandidate],
) -> None:
    known = {c.canonical_name for c in candidates}
    if canonical_name not in known:
        msg = f"canonical_name {canonical_name!r} is not among candidates"
        raise EntityResolutionError(msg)


def make_fetch_resolution(
    *,
    paths: DataPaths | None = None,
    llm_config: LlmConfig | None = None,
) -> FetchResolution:
    """Return a fetch_resolution callable backed by fetch_llm_json."""

    def fetch(messages: list[dict[str, str]]) -> dict[str, Any]:
        value = fetch_llm_json(
            messages,
            expect="object",
            paths=paths,
            config=llm_config,
        )
        if not isinstance(value, dict):
            msg = "Entity resolution JSON must be an object"
            raise EntityResolutionError(msg)
        return value

    return fetch


def _segment_slug_from_canonical(canonical_name: str) -> str:
    return canonical_name.split("/")[-1]


def _escape_cypher_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")
