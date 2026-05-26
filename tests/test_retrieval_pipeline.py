from __future__ import annotations

from pathlib import Path

import pytest

from whyline.config import EmbeddingConfig
from whyline.embeddings import EMBEDDING_DIM, register_embedding_backend
from whyline.graph import get_graph_db, index_record_graph, init_graph_schema
from whyline.graph.store import clear_graph_db_cache
from whyline.paths import ensure_data_layout, resolve_data_paths
from whyline.records.io import read_record
from whyline.retrieval import NO_RETRIEVED_RECORDS_ANSWER, run_retrieval_pipeline
from whyline.retrieval_enums import QueryType, RetrievalSource
from whyline.vectors.indexing import index_record
from whyline.vectors.store import clear_vector_db_cache

pytest.importorskip("ladybug")
pytest.importorskip("lancedb")

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "with-claims.md"


def _retrieval_embed(
    texts: list[str],
    _config: EmbeddingConfig,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        lower = text.lower()
        if "postgresql" in lower or "session storage" in lower:
            vectors.append([1.0] + [0.0] * (EMBEDDING_DIM - 1))
        else:
            vectors.append([0.0] * EMBEDDING_DIM)
    return vectors


@pytest.fixture(autouse=True)
def _clear_stores() -> None:
    clear_graph_db_cache()
    clear_vector_db_cache()
    register_embedding_backend("test", _retrieval_embed)
    yield
    clear_graph_db_cache()
    clear_vector_db_cache()


def _seed_record(paths, filename: str = "with-claims.md"):
    paths.records_dir.mkdir(parents=True, exist_ok=True)
    target = paths.records_dir / filename
    target.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    record = read_record(target).record
    graph = get_graph_db(paths)
    init_graph_schema(graph)
    index_record_graph(record, graph, paths)
    index_record(record, paths, config=EmbeddingConfig(provider="test", model="fake"))
    return graph


def _analysis_json() -> dict:
    return {
        "query_type": "current_state",
        "filters": {
            "project": "main-platform",
            "context_keywords": ["auth"],
            "status_filter": "active",
        },
        "semantic_query": "session storage",
        "graph_hint": "Find active auth decisions",
    }


def test_run_retrieval_pipeline_mocked_e2e(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = _seed_record(paths)
    query_calls: list[list[dict[str, str]]] = []
    synthesis_calls: list[list[dict[str, str]]] = []

    def fake_fetch_json(messages: list[dict[str, str]], **_kwargs) -> dict:
        query_calls.append(messages)
        return _analysis_json()

    def fake_fetch_text(messages: list[dict[str, str]], **_kwargs) -> str:
        synthesis_calls.append(messages)
        return "Sessions are stored in PostgreSQL (source: with-claims.md)."

    result = run_retrieval_pipeline(
        "What's our current approach to session storage?",
        paths,
        graph=graph,
        embedding_config=EmbeddingConfig(provider="test", model="fake"),
        fetch_json=fake_fetch_json,
        fetch_text=fake_fetch_text,
    )

    assert result.question == "What's our current approach to session storage?"
    assert result.analysis.query_type is QueryType.CURRENT_STATE
    assert query_calls
    assert synthesis_calls
    assert [hit.file_reference for hit in result.graph_hits] == [
        "records/with-claims.md"
    ]
    assert [hit.file_reference for hit in result.vector_hits] == [
        "records/with-claims.md"
    ]
    assert [hit.file_reference for hit in result.merged_hits] == [
        "records/with-claims.md"
    ]
    assert result.merged_hits[0].sources == frozenset(
        {RetrievalSource.GRAPH, RetrievalSource.VECTOR}
    )
    assert result.answer == "Sessions are stored in PostgreSQL (source: with-claims.md)."
    assert result.answer_view.citations == ["with-claims.md"]
    assert result.answer_view.sources[0].file_reference == "records/with-claims.md"
    assert "RETRIEVED RECORDS:" in synthesis_calls[0][1]["content"]
    assert "Drop Redis for session storage" in synthesis_calls[0][1]["content"]


def test_run_retrieval_pipeline_empty_hits_skips_synthesis_llm(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)

    def fake_fetch_json(_messages: list[dict[str, str]], **_kwargs) -> dict:
        return {
            "query_type": "current_state",
            "filters": {
                "project": "missing-project",
                "context_keywords": ["missing"],
                "status_filter": "active",
            },
            "semantic_query": "missing topic",
            "graph_hint": "No matching graph area",
        }

    def fail_fetch_text(_messages: list[dict[str, str]], **_kwargs) -> str:
        raise AssertionError("synthesis LLM should not run with no merged hits")

    result = run_retrieval_pipeline(
        "What did we decide about missing topic?",
        paths,
        graph=graph,
        embedding_config=EmbeddingConfig(provider="test", model="fake"),
        fetch_json=fake_fetch_json,
        fetch_text=fail_fetch_text,
    )

    assert result.graph_hits == []
    assert result.vector_hits == []
    assert result.merged_hits == []
    assert result.answer == NO_RETRIEVED_RECORDS_ANSWER
    assert result.answer_view.sources == []


def test_run_retrieval_pipeline_historical_without_context_does_not_crash(
    tmp_path: Path,
) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    graph = get_graph_db(paths)

    def fake_fetch_json(_messages: list[dict[str, str]], **_kwargs) -> dict:
        return {
            "query_type": "historical",
            "filters": {
                "status_filter": "all",
            },
            "semantic_query": "spark 3.4",
            "graph_hint": "Look for historical decisions",
        }

    def fail_fetch_text(_messages: list[dict[str, str]], **_kwargs) -> str:
        raise AssertionError("synthesis LLM should not run with no merged hits")

    result = run_retrieval_pipeline(
        "Why did we migrate to Spark 3.4?",
        paths,
        graph=graph,
        embedding_config=EmbeddingConfig(provider="test", model="fake"),
        fetch_json=fake_fetch_json,
        fetch_text=fail_fetch_text,
    )

    assert result.graph_hits == []
    assert result.vector_hits == []
    assert result.merged_hits == []
    assert result.answer == NO_RETRIEVED_RECORDS_ANSWER
