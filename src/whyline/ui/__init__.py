"""Terminal UI components — spec §11."""

from whyline.ui.conflict_confirm import (
    default_conflict_prompt,
    render_conflict_prompt,
)
from whyline.ui.ingest_confirm import (
    IngestConfirmationView,
    confirmation_view_from_record,
    render_ingest_confirmation,
)

__all__ = [
    "IngestConfirmationView",
    "confirmation_view_from_record",
    "default_conflict_prompt",
    "render_conflict_prompt",
    "render_ingest_confirmation",
]
