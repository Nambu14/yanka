"""LanceDB connection helper — disposable vector index under data_dir/vectors/."""

from __future__ import annotations

from typing import Any

from yanka.paths import DataPaths, ensure_data_layout, resolve_data_paths

_connections: dict[str, Any] = {}


class VectorStoreError(Exception):
    """Vector store setup or dependency failures."""


def get_vector_db(paths: DataPaths | None = None) -> Any:
    """Open (or reuse) a LanceDB connection at ``paths.vectors_dir``.

    Idempotent: repeated calls with the same resolved directory return the same
    connection object. Creates ``vectors/`` via
    :func:`yanka.paths.ensure_data_layout`.
    """
    resolved = ensure_data_layout(paths if paths is not None else resolve_data_paths())
    key = str(resolved.vectors_dir)
    if key in _connections:
        return _connections[key]

    try:
        import lancedb
    except ImportError as exc:
        msg = 'lancedb is not installed. Install with: pip install -e ".[vectors]" or pip install -e ".[spike]"'
        raise VectorStoreError(msg) from exc

    db = lancedb.connect(key)
    _connections[key] = db
    return db


def clear_vector_db_cache() -> None:
    """Drop cached connections (tests only)."""
    _connections.clear()
