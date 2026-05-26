from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from whyline.llm import LlmError, PromptName, get_prompt
from whyline.paths import ensure_data_layout, resolve_data_paths
from whyline.records.models import RecordStatus
from whyline.retrieval import (
    NO_RETRIEVED_RECORDS_ANSWER,
    MergedRetrievalHit,
    RetrievalConfidence,
    RetrievalSynthesisError,
    build_retrieval_synthesis_messages,
    format_retrieval_synthesis_input,
    load_retrieved_records,
    synthesize_retrieval_answer,
)
from whyline.retrieval.query_analysis import QueryAnalysis, QueryFilters
from whyline.retrieval_enums import QueryType, RetrievalSource

FIXTURE = Path(__file__).parent / "fixtures" / "records" / "valid-decision.md"


def _analysis(query_type: QueryType = QueryType.CURRENT_STATE) -> QueryAnalysis:
    return QueryAnalysis(
        query_type=query_type,
        filters=QueryFilters(project="main-platform", context_keywords=["auth"]),
        semantic_query="session storage",
        graph_hint="test",
    )


def _hit(file_reference: str = "records/valid-decision.md") -> MergedRetrievalHit:
    return MergedRetrievalHit(
        file_reference=file_reference,
        date=date(2026, 5, 14),
        status=RecordStatus.ACTIVE.value,
        summary="Drop Redis for session storage",
        context="main-platform/auth-service",
        sources=frozenset({RetrievalSource.GRAPH, RetrievalSource.VECTOR}),
        vector_score=0.03,
        confidence=RetrievalConfidence.HIGH,
    )


def _seed_record(paths, filename: str = "valid-decision.md") -> None:
    paths.records_dir.mkdir(parents=True, exist_ok=True)
    (paths.records_dir / filename).write_text(FIXTURE.read_text(encoding="utf-8"))


def test_load_retrieved_records_loads_raw_markdown(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)

    records = load_retrieved_records([_hit()], paths)

    assert len(records) == 1
    assert records[0].path == paths.records_dir / "valid-decision.md"
    assert "Drop Redis for session storage" in records[0].raw_markdown
    assert records[0].hit.file_reference == "records/valid-decision.md"


def test_load_retrieved_records_missing_file_raises(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))

    with pytest.raises(RetrievalSynthesisError, match="missing on disk"):
        load_retrieved_records([_hit("records/missing.md")], paths)


def test_format_retrieval_synthesis_input_matches_prompt_contract(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)
    records = load_retrieved_records([_hit()], paths)

    text = format_retrieval_synthesis_input(
        "What's our current approach to session storage?",
        _analysis(),
        records,
    )

    assert "QUESTION: What's our current approach to session storage?" in text
    assert "QUERY TYPE: current_state" in text
    assert "RETRIEVED RECORDS:" in text
    assert "--- record: valid-decision.md ---" in text
    assert "Drop Redis for session storage" in text


def test_build_retrieval_synthesis_messages_uses_prompt_5(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)
    records = load_retrieved_records([_hit()], paths)

    messages = build_retrieval_synthesis_messages("question?", _analysis(), records)

    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == get_prompt(PromptName.RETRIEVAL_SYNTHESIS)
    assert messages[1]["role"] == "user"
    assert "QUESTION: question?" in messages[1]["content"]


def test_synthesize_retrieval_answer_mocked_llm(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)
    calls: list[list[dict[str, str]]] = []

    def fake_fetch(messages: list[dict[str, str]], **_kwargs) -> str:
        calls.append(messages)
        return "Sessions are stored in PostgreSQL (source: valid-decision.md)."

    answer = synthesize_retrieval_answer(
        "What's our current approach to session storage?",
        _analysis(),
        [_hit()],
        paths=paths,
        fetch_text=fake_fetch,
    )

    assert answer == "Sessions are stored in PostgreSQL (source: valid-decision.md)."
    assert len(calls) == 1
    assert "RETRIEVED RECORDS:" in calls[0][1]["content"]


def test_synthesize_retrieval_answer_empty_hits_skips_llm(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))

    def fail_fetch(_messages: list[dict[str, str]], **_kwargs) -> str:
        raise AssertionError("LLM should not be called for empty retrieval results")

    answer = synthesize_retrieval_answer(
        "What did we decide?",
        _analysis(),
        [],
        paths=paths,
        fetch_text=fail_fetch,
    )

    assert answer == NO_RETRIEVED_RECORDS_ANSWER


def test_synthesize_retrieval_answer_wraps_llm_error(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    _seed_record(paths)

    def fail_fetch(_messages: list[dict[str, str]], **_kwargs) -> str:
        raise LlmError("provider down")

    with pytest.raises(RetrievalSynthesisError, match="LLM call failed"):
        synthesize_retrieval_answer(
            "What did we decide?",
            _analysis(),
            [_hit()],
            paths=paths,
            fetch_text=fail_fetch,
        )
