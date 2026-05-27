"""Ingest pipeline orchestrator — spec §7 steps 1–10."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from yanka.config import EmbeddingConfig, LlmConfig
from yanka.graph import get_graph_db, init_graph_schema
from yanka.graph.store import GraphDb
from yanka.ingest.claim_validation import extract_claims_validated
from yanka.ingest.conflict_candidates import find_conflict_candidates
from yanka.ingest.conflict_confirmation import confirm_detected_conflicts
from yanka.ingest.conflict_evaluation import DetectedConflict, evaluate_conflicts
from yanka.ingest.entity_resolution import resolve_record_context_path
from yanka.ingest.extraction import (
    run_record_extraction_loop_detailed,
    run_record_extraction_resume_loop_detailed,
)
from yanka.ingest.write import WriteResult, write_ingested_record
from yanka.paths import DataPaths, resolve_data_paths
from yanka.records.models import Record
from yanka.ui import confirmation_view_from_record, render_ingest_confirmation
from yanka.ui.ingest_confirm import IngestConfirmationView

PromptUser = Callable[[str], str]
SendMessages = Callable[..., str]
FetchJson = Callable[..., Any]
PromptConfirm = Callable[..., bool]


@dataclass
class IngestResult:
    """Outcome of a full ingest pipeline run."""

    record: Record
    write_result: WriteResult
    warnings: list[str] = field(default_factory=list)
    confirmed_conflicts: list[DetectedConflict] = field(default_factory=list)
    clarifying_rounds: int = 0
    confirmation_view: IngestConfirmationView | None = None


def run_ingest_pipeline(
    raw_dump: str,
    paths: DataPaths | None = None,
    *,
    prompt_user: PromptUser,
    send: SendMessages | None = None,
    fetch_json: FetchJson | None = None,
    fetch_resolution: Callable[..., Any] | None = None,
    ask_user: Callable[[str], str] | None = None,
    prompt_confirm: PromptConfirm | None = None,
    show_confirmation: bool = False,
    graph: GraphDb | None = None,
    filename: str | None = None,
    llm_config: LlmConfig | None = None,
    embedding_config: EmbeddingConfig | None = None,
    resume_messages: list[dict[str, str]] | None = None,
) -> IngestResult:
    """Run ingest steps 1–10 (spec §7) with injectable LLM and user hooks."""
    resolved = paths if paths is not None else resolve_data_paths()

    if resume_messages is None:
        extraction = run_record_extraction_loop_detailed(
            raw_dump,
            resolved,
            prompt_user=prompt_user,
            send=send,
            config=llm_config,
        )
    else:
        extraction = run_record_extraction_resume_loop_detailed(
            raw_dump,
            resume_messages,
            resolved,
            prompt_user=prompt_user,
            send=send,
            config=llm_config,
        )
    record = extraction.record

    claims, warnings = extract_claims_validated(
        record,
        paths=resolved,
        config=llm_config,
        fetch_json=fetch_json,
    )
    record = replace(record, claims=claims)

    graph_db = graph if graph is not None else get_graph_db(resolved)
    init_graph_schema(graph_db)
    record = resolve_record_context_path(
        record,
        graph_db,
        paths=resolved,
        llm_config=llm_config,
        fetch_resolution=fetch_resolution,
        ask_user=ask_user,
    )

    candidates = find_conflict_candidates(
        record.claims,
        record.context_path,
        graph_db,
        paths=resolved,
        config=embedding_config,
    )
    detected = evaluate_conflicts(
        record.claims,
        candidates,
        context_path=record.context_path,
        paths=resolved,
        config=llm_config,
        fetch_json=fetch_json,
    )
    confirmed, claims = confirm_detected_conflicts(
        detected,
        record.claims,
        candidates,
        prompt_confirm=prompt_confirm,
    )
    record = replace(record, claims=claims)

    write_result = write_ingested_record(
        resolved,
        record,
        filename=filename,
        graph=graph_db,
        embedding_config=embedding_config,
    )
    record.source_path = write_result.path.resolve()

    view = confirmation_view_from_record(
        record,
        path=write_result.path,
        write_result=write_result,
        extra_warnings=warnings,
    )
    if show_confirmation:
        render_ingest_confirmation(view)

    return IngestResult(
        record=record,
        write_result=write_result,
        warnings=warnings,
        confirmed_conflicts=confirmed,
        clarifying_rounds=extraction.clarifying_rounds,
        confirmation_view=view,
    )
