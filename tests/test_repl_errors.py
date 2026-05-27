from __future__ import annotations

from unittest.mock import patch

import click
import pytest

from yanka.ingest.conflict_confirmation import (
    ConflictPromptView,
    confirm_detected_conflicts,
)
from yanka.ingest.conflict_evaluation import DetectedConflict
from yanka.ingest.pipeline import IngestAbortError
from yanka.ingest.pipeline_stages import PipelineStage
from yanka.llm.client import (
    LlmAuthError,
    LlmError,
    LlmRateLimitError,
    LlmTimeoutError,
    LlmTransportError,
)
from yanka.records.models import Claim, ClaimStatus
from yanka.repl.errors import format_user_error, repl_conflict_prompt


@pytest.mark.parametrize(
    ("exc", "command", "expected_fragment"),
    [
        (
            LlmTransportError("litellm.InternalServerError: boom"),
            "log",
            "Could not reach the LLM provider",
        ),
        (
            LlmAuthError("invalid api key"),
            "log",
            "API key was rejected",
        ),
        (
            LlmRateLimitError("429"),
            "ask",
            "rate limit",
        ),
        (
            LlmTimeoutError("timed out"),
            "log",
            "did not respond in time",
        ),
        (
            LlmError("litellm.Something: opaque"),
            "ask",
            "request to the LLM provider failed",
        ),
    ],
)
def test_format_user_error_maps_llm_subclasses(
    exc: LlmError,
    command: str,
    expected_fragment: str,
) -> None:
    lines = format_user_error(exc, command=command)
    text = "\n".join(lines).lower()

    assert expected_fragment.lower() in text
    assert "litellm" not in text


def test_format_user_error_log_includes_resume_hint() -> None:
    lines = format_user_error(LlmTransportError("x"), command="log")

    assert any("/resume" in line for line in lines)


def test_format_user_error_ask_omits_resume_hint() -> None:
    lines = format_user_error(LlmTransportError("x"), command="ask")

    assert not any("/resume" in line for line in lines)


def test_format_user_error_ingest_abort() -> None:
    exc = IngestAbortError(
        "disk full",
        stage=PipelineStage.WRITING,
    )
    lines = format_user_error(exc, command="log")

    assert "could not be written" in lines[0].lower()
    assert "disk full" not in "\n".join(lines).lower()


def test_repl_conflict_prompt_treats_abort_as_no() -> None:
    view = ConflictPromptView(
        detected=DetectedConflict(
            new_claim_id="c1",
            existing_claim_id="old:c1",
            reason="overlap",
        ),
        old_content="old",
        new_content="new",
    )

    with patch(
        "yanka.ui.conflict_confirm.click.confirm",
        side_effect=click.Abort(),
    ):
        assert repl_conflict_prompt(view) is False


def test_confirm_detected_conflicts_continues_after_abort() -> None:
    detected = [
        DetectedConflict(
            new_claim_id="c1",
            existing_claim_id="records/old.md:c2",
            reason="overlap",
        )
    ]
    claims = [
        Claim(id="c1", content="new claim", status=ClaimStatus.ACTIVE),
    ]

    with patch(
        "yanka.ui.conflict_confirm.click.confirm",
        side_effect=click.Abort(),
    ):
        confirmed, updated = confirm_detected_conflicts(
            detected,
            claims,
            [],
            prompt_confirm=repl_conflict_prompt,
        )

    assert confirmed == []
    assert updated[0].supersedes is None
