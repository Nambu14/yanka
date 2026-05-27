"""Claims vector table — spec §5."""

from __future__ import annotations

from typing import Any

from yanka.paths import DataPaths, resolve_data_paths
from yanka.vectors.schema import CLAIMS_TABLE, claims_table_schema
from yanka.vectors.store import get_vector_db


def open_claims_table(
    db: Any | None = None,
    *,
    paths: DataPaths | None = None,
) -> Any:
    """Open the claims table, creating an empty one with the spec schema if needed."""
    connection = db if db is not None else get_vector_db(paths)
    return connection.create_table(
        CLAIMS_TABLE,
        schema=claims_table_schema(),
        exist_ok=True,
    )


def get_claims_table(paths: DataPaths | None = None) -> Any:
    """Resolve data paths and return the claims table."""
    resolved = paths if paths is not None else resolve_data_paths()
    return open_claims_table(paths=resolved)
