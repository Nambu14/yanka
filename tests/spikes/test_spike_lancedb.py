"""S.2 — LanceDB: table create, vector insert, search + metadata filter."""

from __future__ import annotations

import numpy as np
import pytest

lancedb = pytest.importorskip("lancedb")

VECTOR_DIM = 384


def _row(file_reference: str, vector: list[float], project: str, status: str) -> dict:
    return {
        "file_reference": file_reference,
        "vector": vector,
        "project": project,
        "status": status,
    }


def test_lancedb_vector_search_and_filter(tmp_path) -> None:
    db = lancedb.connect(str(tmp_path / "vectors"))

    anchor = [1.0] + [0.0] * (VECTOR_DIM - 1)
    near = [0.99] + [0.01] * (VECTOR_DIM - 1)
    far = [0.0] * VECTOR_DIM

    rows = [
        _row("records/a.md", anchor, "acme", "active"),
        _row("records/b.md", near, "acme", "active"),
        _row("records/c.md", far, "other", "archived"),
    ]
    table = db.create_table("spike_records", rows)

    hits = table.search(np.array(anchor, dtype=np.float32)).limit(1).to_list()
    assert hits[0]["file_reference"] == "records/a.md"

    filtered = (
        table.search(np.array(anchor, dtype=np.float32))
        .where("status = 'active'")
        .limit(10)
        .to_list()
    )
    refs = {r["file_reference"] for r in filtered}
    assert refs == {"records/a.md", "records/b.md"}
    assert "records/c.md" not in refs
