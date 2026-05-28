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
from yanka.ingest.duplicate_claims import (
    DuplicateClaimMatch,
    drop_duplicate_claims,
    find_duplicate_claims,
)
from yanka.ingest.entity_resolution import resolve_record_context_path_degrading
from yanka.ingest.extraction import (
    run_record_extraction_loop_detailed,
    run_record_extraction_resume_loop_detailed,
)
from yanka.ingest.pipeline_stages import (
    CONFLICT_EVALUATION_DEGRADE_WARNING,
    PipelineStage,
)
from yanka.ingest.write import WriteResult, write_ingested_record
from yanka.llm.client import LlmError
from yanka.paths import DataPaths, resolve_data_paths
from yanka.records.models import Record
from yanka.ui import confirmation_view_from_record, render_ingest_confirmation
from yanka.ui.ingest_confirm import IngestConfirmationView
from yanka.ui.pipeline_activity import IngestActivityStage, IngestOnStage

PromptUser = Callable[[str], str]
SendMessages = Callable[..., str]
FetchJson = Callable[..., Any]
PromptConfirm = Callable[..., bool]


class IngestAbortError(LlmError):
    """Ingest stopped before write; carries resume state for ``/resume``."""

    def __init__(
        self,
        message: str,
        *,
        stage: PipelineStage,
        record: Record | None = None,
        messages: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.record = record
        self.messages = messages if messages is not None else []


class IngestDuplicateRecordError(Exception):
    """All claims in the ingest restate existing active claims; nothing to save."""

    def __init__(
        self,
        message: str,
        *,
        duplicate_claims: list[DuplicateClaimMatch],
    ) -> None:
        super().__init__(message)
        self.duplicate_claims = list(duplicate_claims)

    @property
    def existing_files(self) -> list[str]:
        """Unique source files matched by the dropped claims, in first-seen order."""
        seen: set[str] = set()
        ordered: list[str] = []
        for match in self.duplicate_claims:
            if match.existing_file and match.existing_file not in seen:
                seen.add(match.existing_file)
                ordered.append(match.existing_file)
        return ordered


@dataclass
class IngestResult:
    """Outcome of a full ingest pipeline run."""

    record: Record
    write_result: WriteResult
    warnings: list[str] = field(default_factory=list)
    confirmed_conflicts: list[DetectedConflict] = field(default_factory=list)
    duplicate_claims: list[DuplicateClaimMatch] = field(default_factory=list)
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
    resume_stage: PipelineStage | None = None,
    resume_record: Record | None = None,
    on_stage: IngestOnStage | None = None,
    before_confirmation: Callable[[], None] | None = None,
    confirmation_output: Callable[[str], None] | None = None,
) -> IngestResult:
    """Run ingest steps 1–10 (spec §7) with injectable LLM and user hooks."""
    resolved = paths if paths is not None else resolve_data_paths()
    warnings: list[str] = []
    start_stage = resume_stage or PipelineStage.CLAIMS

    def emit_stage(stage: IngestActivityStage) -> None:
        if on_stage is not None:
            on_stage(stage)

    if resume_record is not None:
        record = resume_record
        clarifying_rounds = 0
    elif resume_messages is not None:
        extraction = run_record_extraction_resume_loop_detailed(
            raw_dump,
            resume_messages,
            resolved,
            prompt_user=prompt_user,
            send=send,
            config=llm_config,
            on_stage=on_stage,
        )
        record = extraction.record
        clarifying_rounds = extraction.clarifying_rounds
        start_stage = PipelineStage.CLAIMS
    else:
        extraction = run_record_extraction_loop_detailed(
            raw_dump,
            resolved,
            prompt_user=prompt_user,
            send=send,
            config=llm_config,
            on_stage=on_stage,
        )
        record = extraction.record
        clarifying_rounds = extraction.clarifying_rounds
        start_stage = PipelineStage.CLAIMS

    graph_db = graph if graph is not None else get_graph_db(resolved)
    init_graph_schema(graph_db)

    if start_stage.runs_at_or_before(PipelineStage.CLAIMS):
        emit_stage(IngestActivityStage.VALIDATING)
        claims, claim_warnings = extract_claims_validated(
            record,
            paths=resolved,
            config=llm_config,
            fetch_json=fetch_json,
        )
        record = replace(record, claims=claims)
        warnings.extend(claim_warnings)

    if start_stage.runs_at_or_before(PipelineStage.ENTITY_RESOLUTION):
        record, entity_warnings = resolve_record_context_path_degrading(
            record,
            graph_db,
            paths=resolved,
            llm_config=llm_config,
            fetch_resolution=fetch_resolution,
            ask_user=ask_user,
        )
        warnings.extend(entity_warnings)

    duplicate_matches: list[DuplicateClaimMatch] = []
    if start_stage.runs_at_or_before(PipelineStage.DUPLICATE_CLAIMS):
        emit_stage(IngestActivityStage.DEDUPING)
        duplicate_matches = find_duplicate_claims(
            record.claims,
            record.context_path,
            paths=resolved,
            config=embedding_config,
        )
        if duplicate_matches:
            survivors = drop_duplicate_claims(record.claims, duplicate_matches)
            if not survivors:
                files = ", ".join(
                    _format_duplicate_files(duplicate_matches)
                ) or "an existing record"
                msg = (
                    "Every claim in this ingest restates an existing record "
                    f"({files}); nothing new to save."
                )
                raise IngestDuplicateRecordError(
                    msg,
                    duplicate_claims=duplicate_matches,
                )
            record = replace(record, claims=survivors)

    confirmed: list[DetectedConflict] = []
    if start_stage.runs_at_or_before(PipelineStage.CONFLICT_EVALUATION):
        emit_stage(IngestActivityStage.CONFLICT_CHECK)
        candidates = find_conflict_candidates(
            record.claims,
            record.context_path,
            graph_db,
            paths=resolved,
            config=embedding_config,
        )
        try:
            detected = evaluate_conflicts(
                record.claims,
                candidates,
                context_path=record.context_path,
                paths=resolved,
                config=llm_config,
                fetch_json=fetch_json,
            )
        except LlmError:
            detected = []
            warnings.append(CONFLICT_EVALUATION_DEGRADE_WARNING)
        confirmed, claims = confirm_detected_conflicts(
            detected,
            record.claims,
            candidates,
            prompt_confirm=prompt_confirm,
        )
        record = replace(record, claims=claims)

    try:
        emit_stage(IngestActivityStage.WRITING)
        write_result = write_ingested_record(
            resolved,
            record,
            filename=filename,
            graph=graph_db,
            embedding_config=embedding_config,
        )
    except Exception as exc:
        msg = f"Record could not be written: {exc}"
        raise IngestAbortError(
            msg,
            stage=PipelineStage.WRITING,
            record=record,
        ) from exc

    record.source_path = write_result.path.resolve()

    view = confirmation_view_from_record(
        record,
        path=write_result.path,
        write_result=write_result,
        extra_warnings=warnings,
        duplicate_claims=duplicate_matches,
    )
    if show_confirmation:
        if before_confirmation is not None:
            before_confirmation()
        render_ingest_confirmation(view, output_fn=confirmation_output)

    return IngestResult(
        record=record,
        write_result=write_result,
        warnings=warnings,
        confirmed_conflicts=confirmed,
        duplicate_claims=duplicate_matches,
        clarifying_rounds=clarifying_rounds,
        confirmation_view=view,
    )


def _format_duplicate_files(matches: list[DuplicateClaimMatch]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for match in matches:
        name = match.existing_file
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered
