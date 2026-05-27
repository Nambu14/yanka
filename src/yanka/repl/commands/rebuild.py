"""`/rebuild` command."""

from __future__ import annotations

from yanka.paths import DataPaths
from yanka.rebuild import rebuild_indexes


def run_repl_rebuild(paths: DataPaths) -> str:
    """Rebuild indexes from the REPL and return the user-facing summary."""
    count = rebuild_indexes(paths)
    return f"Rebuilt indexes from {count} record(s)."
