"""Terminal UI components — spec §11."""

from yanka.ui.conflict_confirm import (
    default_conflict_prompt,
    render_conflict_prompt,
)
from yanka.ui.ingest_confirm import (
    IngestConfirmationView,
    confirmation_view_from_record,
    render_ingest_confirmation,
)
from yanka.ui.pipeline_activity import (
    IngestActivityStage,
    IngestOnStage,
    RetrievalActivityStage,
    RetrievalOnStage,
    ingest_stage_label,
    retrieval_stage_label,
)
from yanka.ui.retrieval_answer import render_retrieval_answer
from yanka.ui.system import (
    print_clarifying_panel,
    print_hint,
    print_status_panel,
    print_statusline,
    print_system,
    print_welcome_panel,
    start_activity,
    yanka_badge,
)

__all__ = [
    "IngestConfirmationView",
    "confirmation_view_from_record",
    "default_conflict_prompt",
    "render_conflict_prompt",
    "render_ingest_confirmation",
    "render_retrieval_answer",
    "print_statusline",
    "print_clarifying_panel",
    "print_hint",
    "print_status_panel",
    "print_system",
    "print_welcome_panel",
    "IngestActivityStage",
    "IngestOnStage",
    "RetrievalActivityStage",
    "RetrievalOnStage",
    "ingest_stage_label",
    "retrieval_stage_label",
    "start_activity",
    "yanka_badge",
]
