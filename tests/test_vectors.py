from __future__ import annotations

import datetime
from pathlib import Path

import numpy as np
import pytest

from yanka.embeddings import EMBEDDING_DIM
from yanka.paths import ensure_data_layout, resolve_data_paths
from yanka.vectors.claims import get_claims_table, open_claims_table
from yanka.vectors.records import get_records_table, open_records_table
from yanka.vectors.schema import (
    CLAIMS_TABLE,
    RECORDS_TABLE,
    claims_table_schema,
    records_table_schema,
)
from yanka.vectors.store import clear_vector_db_cache, get_vector_db

lancedb = pytest.importorskip("lancedb")
pyarrow = pytest.importorskip("pyarrow")


@pytest.fixture(autouse=True)
def _clear_db_cache() -> None:
    clear_vector_db_cache()
    yield
    clear_vector_db_cache()


def test_get_vector_db_creates_vectors_dir(tmp_path: Path) -> None:
    paths = resolve_data_paths(tmp_path)
    assert not paths.vectors_dir.exists()

    get_vector_db(paths)

    assert paths.vectors_dir.is_dir()


def test_get_vector_db_idempotent_same_connection(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))

    first = get_vector_db(paths)
    second = get_vector_db(paths)

    assert first is second


def test_get_vector_db_different_paths_different_connections(
    tmp_path: Path,
) -> None:
    paths_a = ensure_data_layout(resolve_data_paths(tmp_path / "a"))
    paths_b = ensure_data_layout(resolve_data_paths(tmp_path / "b"))

    db_a = get_vector_db(paths_a)
    db_b = get_vector_db(paths_b)

    assert db_a is not db_b


def test_get_vector_db_connects_under_vectors_dir(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    db = get_vector_db(paths)

    table = db.create_table(
        "test_open",
        [{"id": "1", "vector": [0.0] * 4}],
    )
    assert table.count_rows() == 1


def test_records_table_schema_matches_spec() -> None:
    schema = records_table_schema()
    assert schema.field("file_reference").type == pyarrow.string()
    assert schema.field("vector").type.list_size == EMBEDDING_DIM
    assert schema.field("tags").type.value_type == pyarrow.string()


def test_open_records_table_empty(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    db = get_vector_db(paths)

    table = open_records_table(db)
    assert table.count_rows() == 0
    assert RECORDS_TABLE in db.list_tables().tables


def test_open_records_table_idempotent(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    db = get_vector_db(paths)

    first = open_records_table(db)
    second = open_records_table(db)

    assert first.name == second.name == RECORDS_TABLE
    assert first.count_rows() == 0


def test_records_table_empty_vector_search(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    table = get_records_table(paths)

    query = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    assert table.search(query).limit(5).to_list() == []


def test_claims_table_schema_matches_spec() -> None:
    schema = claims_table_schema()
    assert schema.field("claim_id").type == pyarrow.string()
    assert schema.field("vector").type.list_size == EMBEDDING_DIM
    assert schema.field("content").type == pyarrow.string()


def test_open_claims_table_empty(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    db = get_vector_db(paths)

    table = open_claims_table(db)
    assert table.count_rows() == 0
    assert CLAIMS_TABLE in db.list_tables().tables


def test_open_claims_table_idempotent(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    db = get_vector_db(paths)

    first = open_claims_table(db)
    second = open_claims_table(db)

    assert first.name == second.name == CLAIMS_TABLE
    assert first.count_rows() == 0


def test_claims_table_manual_insert(tmp_path: Path) -> None:
    paths = ensure_data_layout(resolve_data_paths(tmp_path))
    table = get_claims_table(paths)

    vector = [1.0] + [0.0] * (EMBEDDING_DIM - 1)
    table.add(
        [
            {
                "claim_id": "2026-01-15-auth-jwt.md:c1",
                "vector": vector,
                "content": "We use JWT for API authentication.",
                "status": "active",
                "source_file": "records/2026-01-15-auth-jwt.md",
                "date": datetime.date(2026, 1, 15),
                "context_path": "acme/platform/auth",
                "project": "acme",
            }
        ]
    )

    assert table.count_rows() == 1
    row = table.search(np.array(vector, dtype=np.float32)).limit(1).to_list()[0]
    assert row["claim_id"] == "2026-01-15-auth-jwt.md:c1"
    assert row["content"] == "We use JWT for API authentication."
    assert row["project"] == "acme"
