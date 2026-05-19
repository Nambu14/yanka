from datetime import date
from pathlib import Path

import pytest

from whyline.records.frontmatter import parse_frontmatter
from whyline.records.models import (
    ClaimStatus,
    RecordStatus,
    RecordType,
    parse_record,
    record_from_frontmatter,
)

FIXTURES = Path(__file__).parent / "fixtures" / "records"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parse_record_from_valid_fixture() -> None:
    record = parse_record(_read("valid-decision.md"))

    assert record.date == date(2026, 5, 14)
    assert record.type is RecordType.DECISION
    assert record.status is RecordStatus.ACTIVE
    assert record.context_path == ["main-platform", "auth-service"]
    assert record.people == ["Carlos"]
    assert record.tags == ["infrastructure"]
    assert record.decision == "Drop Redis for session storage"
    assert record.supersedes is None
    assert record.record_complete is True
    assert record.claims == []
    assert record.body.rationale == "We chose PostgreSQL."
    assert "user pasted --- here" in (record.body.raw_input or "")
    assert record.raw_markdown is not None


def test_parse_record_with_claims() -> None:
    record = parse_record(_read("with-claims.md"))

    assert len(record.claims) == 2
    assert record.claims[0].id == "c1"
    assert record.claims[0].status is ClaimStatus.ACTIVE
    assert record.claims[1].supersedes is not None
    assert record.claims[1].supersedes.file == "2026-02-10-redis-session-store.md"
    assert record.claims[1].supersedes.claim == "c1"


def test_parse_record_invalid_frontmatter_raises() -> None:
    with pytest.raises(ValueError, match="No valid frontmatter"):
        parse_record(_read("no-fence.md"))


def test_record_from_frontmatter_rejects_invalid_type() -> None:
    frontmatter = parse_frontmatter(_read("valid-decision.md"))
    assert frontmatter is not None
    frontmatter["type"] = "not-a-type"

    with pytest.raises(ValueError, match="invalid record type"):
        record_from_frontmatter(frontmatter, "")


def test_record_from_frontmatter_rejects_bad_context_path() -> None:
    frontmatter = parse_frontmatter(_read("valid-decision.md"))
    assert frontmatter is not None
    frontmatter["context_path"] = "not-a-list"

    with pytest.raises(ValueError, match="context_path"):
        record_from_frontmatter(frontmatter, "")
