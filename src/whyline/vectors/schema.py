"""LanceDB table names and PyArrow schemas (spec §5)."""

from __future__ import annotations

import pyarrow as pa

from whyline.embeddings import EMBEDDING_DIM

RECORDS_TABLE = "records"
CLAIMS_TABLE = "claims"


def records_table_schema() -> pa.Schema:
    """Records table — spec §5."""
    return pa.schema(
        [
            pa.field("file_reference", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
            pa.field("date", pa.date32()),
            pa.field("context_path", pa.string()),
            pa.field("project", pa.string()),
            pa.field("status", pa.string()),
            pa.field("type", pa.string()),
            pa.field("tags", pa.list_(pa.string())),
            pa.field("summary", pa.string()),
        ]
    )


def claims_table_schema() -> pa.Schema:
    """Claims table — spec §5 (used in step 2.5)."""
    return pa.schema(
        [
            pa.field("claim_id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
            pa.field("content", pa.string()),
            pa.field("status", pa.string()),
            pa.field("source_file", pa.string()),
            pa.field("date", pa.date32()),
            pa.field("context_path", pa.string()),
            pa.field("project", pa.string()),
        ]
    )
