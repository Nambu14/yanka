from pathlib import Path

from yanka.records.markdown import record_to_markdown
from yanka.records.models import parse_record

FIXTURES = Path(__file__).parent / "fixtures" / "records"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_round_trip_valid_decision() -> None:
    original = parse_record(_read("valid-decision.md"))
    restored = parse_record(record_to_markdown(original))

    assert restored.date == original.date
    assert restored.type == original.type
    assert restored.status == original.status
    assert restored.context_path == original.context_path
    assert restored.people == original.people
    assert restored.tags == original.tags
    assert restored.decision == original.decision
    assert restored.record_complete == original.record_complete
    assert restored.body.rationale == original.body.rationale
    assert restored.body.raw_input == original.body.raw_input
    assert restored.body.clarifying_exchange == original.body.clarifying_exchange


def test_round_trip_clarifying_exchange() -> None:
    original = parse_record(_read("valid-decision.md"))
    original.body.clarifying_exchange = (
        "### Round 1\n\n**Assistant:**\nTimeline?\n\n**User:**\nOne sprint"
    )
    restored = parse_record(record_to_markdown(original))

    assert restored.body.clarifying_exchange == original.body.clarifying_exchange


def test_round_trip_with_claims() -> None:
    original = parse_record(_read("with-claims.md"))
    restored = parse_record(record_to_markdown(original))

    assert len(restored.claims) == len(original.claims)
    assert restored.claims[1].supersedes is not None
    assert restored.claims[1].supersedes.file == original.claims[1].supersedes.file


def test_omits_empty_body_sections() -> None:
    record = parse_record(_read("valid-decision.md"))
    record.body.alternatives = None
    markdown = record_to_markdown(record)

    assert "## Rationale" in markdown
    assert "## Alternatives considered" not in markdown


def test_top_fence_only_body_may_contain_horizontal_rules() -> None:
    from yanka.records.frontmatter import split_markdown

    record = parse_record(_read("valid-decision.md"))
    record.body.raw_input = "> line with --- inside\n> ---"
    markdown = record_to_markdown(record)

    frontmatter, body = split_markdown(markdown)
    assert frontmatter is not None
    assert "---" in body
    assert "line with --- inside" in body
