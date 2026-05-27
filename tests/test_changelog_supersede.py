import json
from datetime import date
from pathlib import Path

from yanka.paths import resolve_data_paths
from yanka.records.changelog import iter_changelog
from yanka.records.io import write_record
from yanka.records.models import (
    Claim,
    ClaimStatus,
    ClaimSupersedes,
    Record,
    RecordBody,
    RecordStatus,
    RecordType,
)


def test_write_record_supersede_changelog_for_claim_supersedes(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    record = Record(
        date=date(2026, 5, 14),
        type=RecordType.DECISION,
        status=RecordStatus.ACTIVE,
        context_path=["main-platform"],
        decision="Drop Redis",
        claims=[
            Claim(
                id="c2",
                content="Redis is not used",
                status=ClaimStatus.ACTIVE,
                supersedes=ClaimSupersedes(
                    file="2026-02-10-redis-session-store.md",
                    claim="c1",
                ),
            ),
        ],
        body=RecordBody(),
    )

    write_record(paths, record, filename="supersede-demo.md")

    entry = list(iter_changelog(paths))[0]
    assert entry.action == "supersede"
    assert entry.supersedes_claims == [
        {"new": "c2", "old": "2026-02-10-redis-session-store.md:c1"},
    ]

    raw = paths.changelog_path.read_text(encoding="utf-8").splitlines()[0]
    parsed = json.loads(raw)
    assert parsed["action"] == "supersede"
    assert "supersedes_file" not in parsed
