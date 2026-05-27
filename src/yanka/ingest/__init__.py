"""Ingest pipeline — spec §7."""

from yanka.ingest.claim_validation import (
    AMBER_COVERAGE_WARNING,
    ClaimValidationIssue,
    build_claim_extraction_retry_messages,
    extract_claims_validated,
    validate_claims,
)
from yanka.ingest.claims import (
    ClaimExtractionError,
    build_claim_extraction_messages,
    extract_claims,
)
from yanka.ingest.conflict_candidates import (
    ConflictCandidate,
    find_conflict_candidates,
    merge_conflict_candidates,
    vector_conflict_candidates,
)
from yanka.ingest.conflict_confirmation import (
    ConflictPromptView,
    apply_confirmed_supersedes,
    build_conflict_prompt_view,
    confirm_detected_conflicts,
    parse_existing_claim_id,
)
from yanka.ingest.conflict_evaluation import (
    ConflictEvaluationError,
    DetectedConflict,
    build_conflict_evaluation_messages,
    evaluate_conflicts,
)
from yanka.ingest.context_search import (
    ContextRecord,
    find_related_records_for_ingest,
    format_related_records_for_prompt,
    search_related_records,
)
from yanka.ingest.entity_resolution import (
    EntityResolutionError,
    build_entity_resolution_messages,
    lookup_context_by_normalized,
    make_fetch_resolution,
    resolve_context_path,
    resolve_record_context_path,
)
from yanka.ingest.extraction import (
    FINAL_CLARIFYING_ROUND_NUDGE,
    WRAP_UP_USER_MESSAGE,
    RecordExtractionError,
    RecordExtractionResult,
    build_record_extraction_conversation,
    run_record_extraction_loop,
    run_record_extraction_loop_detailed,
)
from yanka.ingest.pipeline import IngestResult, run_ingest_pipeline
from yanka.ingest.write import WriteResult, write_ingested_record

__all__ = [
    "AMBER_COVERAGE_WARNING",
    "ClaimExtractionError",
    "ClaimValidationIssue",
    "ConflictCandidate",
    "ConflictEvaluationError",
    "ConflictPromptView",
    "ContextRecord",
    "DetectedConflict",
    "EntityResolutionError",
    "FINAL_CLARIFYING_ROUND_NUDGE",
    "IngestResult",
    "RecordExtractionError",
    "RecordExtractionResult",
    "WRAP_UP_USER_MESSAGE",
    "WriteResult",
    "apply_confirmed_supersedes",
    "build_conflict_evaluation_messages",
    "build_conflict_prompt_view",
    "build_entity_resolution_messages",
    "build_record_extraction_conversation",
    "build_claim_extraction_messages",
    "build_claim_extraction_retry_messages",
    "extract_claims",
    "extract_claims_validated",
    "confirm_detected_conflicts",
    "evaluate_conflicts",
    "parse_existing_claim_id",
    "find_conflict_candidates",
    "find_related_records_for_ingest",
    "lookup_context_by_normalized",
    "make_fetch_resolution",
    "merge_conflict_candidates",
    "format_related_records_for_prompt",
    "resolve_context_path",
    "resolve_record_context_path",
    "run_ingest_pipeline",
    "run_record_extraction_loop",
    "run_record_extraction_loop_detailed",
    "search_related_records",
    "validate_claims",
    "vector_conflict_candidates",
    "write_ingested_record",
]
