"""Retrieval pipeline orchestrator — spec §8 steps 1–5."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from yanka.config import EmbeddingConfig, LlmConfig
from yanka.graph import get_graph_db, init_graph_schema
from yanka.graph.store import GraphDb
from yanka.paths import DataPaths, resolve_data_paths
from yanka.retrieval.graph_retrieve import GraphRetrievalHit, retrieve_from_graph
from yanka.retrieval.merge import MergedRetrievalHit, merge_retrieval_hits
from yanka.retrieval.output import RetrievalAnswerView, format_retrieval_answer
from yanka.retrieval.query_analysis import QueryAnalysis, analyze_query
from yanka.retrieval.synthesis import synthesize_retrieval_answer
from yanka.retrieval.vector_retrieve import VectorRetrievalHit, retrieve_from_vector

FetchJson = Callable[..., Any]
FetchText = Callable[..., str]


@dataclass
class RetrievalResult:
    """Outcome of a full retrieval pipeline run."""

    question: str
    analysis: QueryAnalysis
    graph_hits: list[GraphRetrievalHit]
    vector_hits: list[VectorRetrievalHit]
    merged_hits: list[MergedRetrievalHit]
    answer: str
    answer_view: RetrievalAnswerView


def run_retrieval_pipeline(
    question: str,
    paths: DataPaths | None = None,
    *,
    graph: GraphDb | None = None,
    llm_config: LlmConfig | None = None,
    embedding_config: EmbeddingConfig | None = None,
    fetch_json: FetchJson | None = None,
    fetch_text: FetchText | None = None,
    graph_limit: int | None = None,
    vector_limit: int | None = None,
    merge_limit: int | None = None,
    today: date | None = None,
) -> RetrievalResult:
    """Run retrieval steps 1–5 with injectable mocked LLM hooks."""
    resolved = paths if paths is not None else resolve_data_paths()

    analysis = analyze_query(
        question,
        paths=resolved,
        config=llm_config,
        fetch_json=fetch_json,
    )

    graph_db = graph if graph is not None else get_graph_db(resolved)
    init_graph_schema(graph_db)
    graph_hits = retrieve_from_graph(
        analysis,
        graph_db,
        resolved,
        limit=graph_limit,
    )
    vector_hits = retrieve_from_vector(
        analysis,
        resolved,
        limit=vector_limit,
        config=embedding_config,
    )
    merged_hits = merge_retrieval_hits(
        analysis,
        graph_hits,
        vector_hits,
        limit=merge_limit,
    )
    answer = synthesize_retrieval_answer(
        question,
        analysis,
        merged_hits,
        paths=resolved,
        config=llm_config,
        fetch_text=fetch_text,
    )
    answer_view = format_retrieval_answer(answer, merged_hits, today=today)

    return RetrievalResult(
        question=question,
        analysis=analysis,
        graph_hits=graph_hits,
        vector_hits=vector_hits,
        merged_hits=merged_hits,
        answer=answer,
        answer_view=answer_view,
    )
