"""Retrieval synthesis — spec §8 step 4, prompt 5."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from yanka.config import LlmConfig
from yanka.llm import LlmError, get_prompt, send_messages
from yanka.llm.prompts import PromptName
from yanka.paths import DataPaths, resolve_data_paths
from yanka.retrieval.merge import MergedRetrievalHit
from yanka.retrieval.query_analysis import QueryAnalysis

NO_RETRIEVED_RECORDS_ANSWER = "No relevant records found. Try different terms."
type FetchTextFn = Callable[..., str]


class RetrievalSynthesisError(LlmError):
    """Retrieval synthesis input loading or LLM generation failed."""


@dataclass(frozen=True)
class RetrievedRecordBundle:
    """A retrieved record hit paired with its raw markdown content."""

    hit: MergedRetrievalHit
    path: Path
    raw_markdown: str


@dataclass(frozen=True)
class RetrievedRecordsLoadResult:
    """Retrieved records plus stale references skipped from disk."""

    records: list[RetrievedRecordBundle]
    missing_file_references: list[str]


@dataclass(frozen=True)
class RetrievalSynthesisResult:
    """Synthesis answer plus stale references skipped before synthesis."""

    answer: str
    missing_file_references: list[str]


STALE_INDEX_WARNING = (
    "Some indexed records are missing on disk; run /rebuild to refresh indexes."
)


def load_retrieved_records(
    hits: list[MergedRetrievalHit],
    paths: DataPaths | None = None,
) -> list[RetrievedRecordBundle]:
    """Load raw markdown files referenced by merged retrieval hits."""
    return load_retrieved_records_detailed(hits, paths).records


def load_retrieved_records_detailed(
    hits: list[MergedRetrievalHit],
    paths: DataPaths | None = None,
) -> RetrievedRecordsLoadResult:
    """Load raw markdown and collect stale file references."""
    resolved = paths if paths is not None else resolve_data_paths()
    bundles: list[RetrievedRecordBundle] = []
    missing: list[str] = []
    for hit in hits:
        path = _record_path(resolved, hit.file_reference)
        if not path.is_file():
            missing.append(hit.file_reference)
            continue
        bundles.append(
            RetrievedRecordBundle(
                hit=hit,
                path=path,
                raw_markdown=path.read_text(encoding="utf-8"),
            )
        )
    return RetrievedRecordsLoadResult(
        records=bundles,
        missing_file_references=missing,
    )


def build_retrieval_synthesis_messages(
    question: str,
    analysis: QueryAnalysis,
    records: list[RetrievedRecordBundle],
) -> list[dict[str, str]]:
    """Build Prompt 5 messages for answer synthesis."""
    return [
        {"role": "system", "content": get_prompt(PromptName.RETRIEVAL_SYNTHESIS)},
        {
            "role": "user",
            "content": format_retrieval_synthesis_input(question, analysis, records),
        },
    ]


def format_retrieval_synthesis_input(
    question: str,
    analysis: QueryAnalysis,
    records: list[RetrievedRecordBundle],
) -> str:
    """Format user content according to spec §10 Prompt 5."""
    parts = [
        f"QUESTION: {question}",
        "",
        f"QUERY TYPE: {analysis.query_type.value}",
        "",
        "RETRIEVED RECORDS:",
    ]
    for bundle in records:
        parts.extend(
            [
                "",
                f"--- record: {bundle.path.name} ---",
                bundle.raw_markdown.rstrip(),
            ]
        )
    return "\n".join(parts).rstrip()


def synthesize_retrieval_answer(
    question: str,
    analysis: QueryAnalysis,
    merged_hits: list[MergedRetrievalHit],
    *,
    paths: DataPaths | None = None,
    config: LlmConfig | None = None,
    fetch_text: FetchTextFn | None = None,
) -> str:
    """Synthesize a plain-text answer from merged retrieval hits."""
    return synthesize_retrieval_answer_detailed(
        question,
        analysis,
        merged_hits,
        paths=paths,
        config=config,
        fetch_text=fetch_text,
    ).answer


def synthesize_retrieval_answer_detailed(
    question: str,
    analysis: QueryAnalysis,
    merged_hits: list[MergedRetrievalHit],
    *,
    paths: DataPaths | None = None,
    config: LlmConfig | None = None,
    fetch_text: FetchTextFn | None = None,
) -> RetrievalSynthesisResult:
    """Synthesize answer and return stale references skipped from disk."""
    if not merged_hits:
        return RetrievalSynthesisResult(
            answer=NO_RETRIEVED_RECORDS_ANSWER,
            missing_file_references=[],
        )

    resolved = paths if paths is not None else resolve_data_paths()
    loaded = load_retrieved_records_detailed(merged_hits, resolved)
    if not loaded.records:
        return RetrievalSynthesisResult(
            answer=NO_RETRIEVED_RECORDS_ANSWER,
            missing_file_references=loaded.missing_file_references,
        )
    messages = build_retrieval_synthesis_messages(
        question,
        analysis,
        loaded.records,
    )
    fetch = fetch_text if fetch_text is not None else send_messages
    try:
        answer = fetch(messages, paths=resolved, config=config)
    except LlmError as exc:
        msg = "retrieval synthesis LLM call failed"
        raise RetrievalSynthesisError(msg) from exc
    return RetrievalSynthesisResult(
        answer=answer,
        missing_file_references=loaded.missing_file_references,
    )


def _record_path(paths: DataPaths, file_reference: str) -> Path:
    ref = Path(file_reference)
    if ref.parts and ref.parts[0] == "records":
        return paths.data_dir / ref
    return paths.records_dir / ref.name
