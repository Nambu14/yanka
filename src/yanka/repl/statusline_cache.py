"""Cache record counts for the REPL status line."""

from __future__ import annotations

from dataclasses import dataclass, field

from yanka.paths import DataPaths
from yanka.records.io import iter_records


@dataclass
class StatuslineCache:
    """Avoid parsing every record file on each prompt when nothing changed."""

    paths: DataPaths
    _count: int | None = field(default=None, init=False, repr=False)
    _fingerprint: tuple[float, int] | None = field(default=None, init=False, repr=False)

    def record_count(self) -> int:
        """Return cached record count, refreshing when the records dir changes."""
        fingerprint = _records_dir_fingerprint(self.paths)
        if self._count is not None and self._fingerprint == fingerprint:
            return self._count
        self._count = sum(1 for _ in iter_records(self.paths))
        self._fingerprint = fingerprint
        return self._count

    def invalidate(self) -> None:
        """Force a full recount on the next ``record_count`` call."""
        self._count = None
        self._fingerprint = None


def _records_dir_fingerprint(paths: DataPaths) -> tuple[float, int]:
    records_dir = paths.records_dir
    if not records_dir.is_dir():
        return (0.0, 0)
    mtime = records_dir.stat().st_mtime
    md_count = sum(1 for path in records_dir.glob("*.md") if path.is_file())
    return (mtime, md_count)
