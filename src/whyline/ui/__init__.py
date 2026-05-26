"""Terminal UI components — spec §11."""

from whyline.ui.ingest_confirm import (
    IngestConfirmationView,
    confirmation_view_from_record,
    render_ingest_confirmation,
)
from whyline.ui.conflict_confirm import (
    default_conflict_prompt,
    render_conflict_prompt,
)
from whyline.ui.retrieval_answer import render_retrieval_answer

__all__ = [
    "IngestConfirmationView",
    "confirmation_view_from_record",
    "default_conflict_prompt",
    "render_conflict_prompt",
    "render_ingest_confirmation",
    "render_retrieval_answer",
]
