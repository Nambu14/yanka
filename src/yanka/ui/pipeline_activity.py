"""Pipeline activity stage IDs and user-facing labels (spec §11)."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum


class IngestActivityStage(StrEnum):
    """Ingest pipeline progress stages shown in the REPL activity spinner."""

    SEARCHING = "searching"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    CONFLICT_CHECK = "conflict-check"
    WRITING = "writing"


class RetrievalActivityStage(StrEnum):
    """Retrieval pipeline progress stages shown in the REPL activity spinner."""

    ANALYZING = "analyzing"
    GRAPH = "graph"
    VECTORS = "vectors"
    SYNTHESIZING = "synthesizing"


IngestOnStage = Callable[[IngestActivityStage], None]
RetrievalOnStage = Callable[[RetrievalActivityStage], None]

INGEST_STAGE_LABELS: dict[IngestActivityStage, str] = {
    IngestActivityStage.SEARCHING: "searching for related records...",
    IngestActivityStage.EXTRACTING: "extracting claims...",
    IngestActivityStage.VALIDATING: "validating claims...",
    IngestActivityStage.CONFLICT_CHECK: "checking for conflicts...",
    IngestActivityStage.WRITING: "writing record...",
}

RETRIEVAL_STAGE_LABELS: dict[RetrievalActivityStage, str] = {
    RetrievalActivityStage.ANALYZING: "analyzing query...",
    RetrievalActivityStage.GRAPH: "retrieving from graph...",
    RetrievalActivityStage.VECTORS: "retrieving from vectors...",
    RetrievalActivityStage.SYNTHESIZING: "synthesizing answer...",
}


def ingest_stage_label(stage: IngestActivityStage) -> str:
    try:
        return INGEST_STAGE_LABELS[stage]
    except KeyError as exc:
        msg = f"unknown ingest stage: {stage!r}"
        raise ValueError(msg) from exc


def retrieval_stage_label(stage: RetrievalActivityStage) -> str:
    try:
        return RETRIEVAL_STAGE_LABELS[stage]
    except KeyError as exc:
        msg = f"unknown retrieval stage: {stage!r}"
        raise ValueError(msg) from exc
