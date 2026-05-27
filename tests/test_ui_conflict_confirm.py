from __future__ import annotations

from io import StringIO

from rich.console import Console

from yanka.ingest.conflict_confirmation import ConflictPromptView
from yanka.ingest.conflict_evaluation import DetectedConflict
from yanka.ui.conflict_confirm import render_conflict_prompt


def _capture(view: ConflictPromptView) -> str:
    buffer = StringIO()
    console = Console(file=buffer, width=100, force_terminal=True, legacy_windows=False)
    console.print(render_conflict_prompt(view))
    return buffer.getvalue()


def test_render_conflict_prompt_shows_old_and_new() -> None:
    view = ConflictPromptView(
        detected=DetectedConflict(
            new_claim_id="c1",
            existing_claim_id="records/old.md:c2",
            reason="Different lifetimes",
        ),
        old_content="Token lifetime is 15 minutes",
        new_content="Token lifetime is 30 minutes",
    )

    output = _capture(view)

    assert "Possible conflict" in output
    assert "Token lifetime is 15 minutes" in output
    assert "Token lifetime is 30 minutes" in output
    assert "Different lifetimes" in output
