"""LadybugDB connection helper — disposable graph under data_dir/graph/."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from whyline.paths import DataPaths, ensure_data_layout, resolve_data_paths

_connections: dict[str, GraphDb] = {}


class GraphStoreError(Exception):
    """Graph store setup or dependency failures."""


@dataclass(frozen=True)
class GraphDb:
    """Open Ladybug database + connection for one graph directory."""

    database: Any
    connection: Any


def get_graph_db(paths: DataPaths | None = None) -> GraphDb:
    """Open (or reuse) Ladybug at ``paths.graph_dir``.

    Idempotent: repeated calls with the same resolved directory return the same
    :class:`GraphDb`. Creates ``graph/`` via :func:`whyline.paths.ensure_data_layout`.
    """
    resolved = ensure_data_layout(paths if paths is not None else resolve_data_paths())
    # Ladybug opens a database *file*; spec stores files under data_dir/graph/
    db_path = resolved.graph_dir / "db"
    key = str(db_path)
    if key in _connections:
        return _connections[key]

    try:
        import ladybug
    except ImportError as exc:
        msg = (
            "ladybug is not installed. "
            'Install with: pip install -e ".[graph]" or pip install -e ".[spike]"'
        )
        raise GraphStoreError(msg) from exc

    database = ladybug.Database(key)
    connection = ladybug.Connection(database)
    graph = GraphDb(database=database, connection=connection)
    _connections[key] = graph
    return graph


def clear_graph_db_cache() -> None:
    """Drop cached connections (tests only)."""
    _connections.clear()
