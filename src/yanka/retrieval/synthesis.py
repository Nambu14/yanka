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


def load_retrieved_records(
    hits: list[MergedRetrievalHit],
    paths: DataPaths | None = None,
) -> list[RetrievedRecordBundle]:
    """Load raw markdown files referenced by merged retrieval hits."""
    resolved = paths if paths is not None else resolve_data_paths()
    bundles: list[RetrievedRecordBundle] = []
    for hit in hits:
        path = _record_path(resolved, hit.file_reference)
        if not path.is_file():
            msg = f"retrieved record is missing on disk: {hit.file_reference}"
            raise RetrievalSynthesisError(msg)
        bundles.append(
            RetrievedRecordBundle(
                hit=hit,
                path=path,
                raw_markdown=path.read_text(encoding="utf-8"),
            )
        )
    return bundles


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
    if not merged_hits:
        return NO_RETRIEVED_RECORDS_ANSWER

    resolved = paths if paths is not None else resolve_data_paths()
    records = load_retrieved_records(merged_hits, resolved)
    messages = build_retrieval_synthesis_messages(question, analysis, records)
    fetch = fetch_text if fetch_text is not None else send_messages
    try:
        return fetch(messages, paths=resolved, config=config)
    except LlmError as exc:
        msg = "retrieval synthesis LLM call failed"
        raise RetrievalSynthesisError(msg) from exc


def _record_path(paths: DataPaths, file_reference: str) -> Path:
    ref = Path(file_reference)
    if ref.parts and ref.parts[0] == "records":
        return paths.data_dir / ref
    return paths.records_dir / ref.name
