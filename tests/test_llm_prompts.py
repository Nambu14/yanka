from __future__ import annotations

import pytest

from yanka.llm import PromptName, UnknownPromptError, get_prompt, prompt_names


@pytest.mark.parametrize(
    "name",
    [
        PromptName.RECORD_EXTRACTION,
        PromptName.CLAIM_EXTRACTION,
        PromptName.CONFLICT_EVALUATION,
        PromptName.QUERY_ANALYSIS,
        PromptName.RETRIEVAL_SYNTHESIS,
        PromptName.ENTITY_CONTEXT_RESOLUTION,
    ],
)
def test_get_prompt_returns_non_empty_for_all_registered(name: PromptName) -> None:
    text = get_prompt(name)
    assert isinstance(text, str)
    assert len(text) > 200


def test_get_prompt_accepts_string_name() -> None:
    assert get_prompt("record_extraction") == get_prompt(PromptName.RECORD_EXTRACTION)


def test_prompt_names_lists_all_six() -> None:
    names = prompt_names()
    assert len(names) == 6
    assert set(names) == {n.value for n in PromptName}


def test_unknown_prompt_raises() -> None:
    with pytest.raises(UnknownPromptError, match="Unknown prompt name 'extraction'"):
        get_prompt("extraction")


def test_record_extraction_marker() -> None:
    text = get_prompt(PromptName.RECORD_EXTRACTION)
    assert '"record_complete": true' in text
    assert "technical decision recorder" in text
    assert "at most 3" in text
    assert "at most 2" in text
    assert "No third clarifying round" in text
    assert "CONVERSATION ENDED" in text or "conversation is OVER" in text


def test_claim_extraction_marker() -> None:
    text = get_prompt(PromptName.CLAIM_EXTRACTION)
    assert "ONLY a JSON array" in text
    assert "claim extractor" in text


def test_conflict_evaluation_marker() -> None:
    text = get_prompt(PromptName.CONFLICT_EVALUATION)
    assert "conflict evaluator" in text
    assert '"conflicts": []' in text


def test_query_analysis_marker() -> None:
    text = get_prompt(PromptName.QUERY_ANALYSIS)
    assert "query analyzer" in text
    assert "query_type" in text


def test_retrieval_synthesis_marker() -> None:
    text = get_prompt(PromptName.RETRIEVAL_SYNTHESIS)
    assert "knowledge retrieval assistant" in text
    assert "(source: filename.md)" in text


def test_entity_context_resolution_marker() -> None:
    text = get_prompt(PromptName.ENTITY_CONTEXT_RESOLUTION)
    assert "context phrase" in text
    assert '"outcome": "existing"' in text
