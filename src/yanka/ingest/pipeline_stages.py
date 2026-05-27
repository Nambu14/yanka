"""Ingest pipeline stage identifiers for resume state."""

from __future__ import annotations

from enum import StrEnum


class PipelineStage(StrEnum):
    """Stages of the ingest pipeline (persisted in pending /log state)."""

    EXTRACTION = "extraction"
    CLAIMS = "claims"
    ENTITY_RESOLUTION = "entity_resolution"
    CONFLICT_EVALUATION = "conflict_evaluation"
    WRITING = "writing"

    def runs_at_or_before(self, other: PipelineStage) -> bool:
        """True when ``other`` is the same stage or later in the post-extraction pipeline."""
        if self is PipelineStage.EXTRACTION or other is PipelineStage.EXTRACTION:
            msg = "extraction stage ordering is not defined for post-extraction resume"
            raise ValueError(msg)
        order = _POST_EXTRACTION_STAGES
        return order.index(self) <= order.index(other)


# Stages run in order after extraction completes (EXTRACTION is separate).
_POST_EXTRACTION_STAGES = (
    PipelineStage.CLAIMS,
    PipelineStage.ENTITY_RESOLUTION,
    PipelineStage.CONFLICT_EVALUATION,
    PipelineStage.WRITING,
)


ENTITY_RESOLUTION_DEGRADE_WARNING = (
    "Context resolution skipped (provider error); using new context nodes."
)
CONFLICT_EVALUATION_DEGRADE_WARNING = (
    "Conflict check skipped (provider error); no conflicts assumed."
)
