from pathlib import Path

from yanka.records.validate import (
    REQUIRED_FRONTMATTER_KEYS,
    extract_complete_record_text,
    is_complete_record,
    validate_frontmatter_keys,
)

FIXTURES = Path(__file__).parent / "fixtures" / "records"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_validate_frontmatter_keys_accepts_full_set() -> None:
    frontmatter = {key: "value" for key in REQUIRED_FRONTMATTER_KEYS}
    assert validate_frontmatter_keys(frontmatter) is True


def test_validate_frontmatter_keys_rejects_missing_key() -> None:
    frontmatter = {key: "value" for key in REQUIRED_FRONTMATTER_KEYS}
    del frontmatter["decision"]
    assert validate_frontmatter_keys(frontmatter) is False


def test_valid_decision_is_complete() -> None:
    assert is_complete_record(_read("valid-decision.md")) is True


def test_incomplete_missing_decision() -> None:
    assert is_complete_record(_read("incomplete-missing-decision.md")) is False


def test_record_complete_false() -> None:
    assert is_complete_record(_read("record-complete-false.md")) is False


def test_record_complete_missing() -> None:
    assert is_complete_record(_read("record-complete-missing.md")) is False


def test_clarifying_questions_not_complete() -> None:
    assert is_complete_record(_read("clarifying-questions.md")) is False


def test_no_fence_not_complete() -> None:
    assert is_complete_record(_read("no-fence.md")) is False


def test_record_complete_string_yes_is_complete() -> None:
    assert is_complete_record(_read("record-complete-string.md")) is True


def test_bare_fences_not_complete() -> None:
    assert is_complete_record("---\n---\n") is False


def test_extract_complete_record_with_preamble_and_trailing_prose() -> None:
    core = _read("valid-decision.md")
    wrapped = f"Great, here is the structured record:\n\n{core}\n\nLet me know if you need anything else!\n"
    extracted = extract_complete_record_text(wrapped)
    assert extracted is not None
    assert is_complete_record(wrapped) is True
    assert extracted.startswith("---")
    assert "Drop Redis for session storage" in extracted
