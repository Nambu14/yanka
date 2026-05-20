"""Records vector table — spec §5."""

from __future__ import annotations

from typing import Any

from whyline.paths import DataPaths, resolve_data_paths
from whyline.vectors.schema import RECORDS_TABLE, records_table_schema
from whyline.vectors.store import get_vector_db


def open_records_table(
    db: Any | None = None,
    *,
    paths: DataPaths | None = None,
) -> Any:
    """Open the records table, creating an empty one with the spec schema if needed."""
    connection = db if db is not None else get_vector_db(paths)
    return connection.create_table(
        RECORDS_TABLE,
        schema=records_table_schema(),
        exist_ok=True,
    )


def get_records_table(paths: DataPaths | None = None) -> Any:
    """Resolve data paths and return the records table."""
    resolved = paths if paths is not None else resolve_data_paths()
    return open_records_table(paths=resolved)
