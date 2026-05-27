"""Related-record search for ingest — spec §7 step 1."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from yanka.config import EmbeddingConfig, default_config, load_config
from yanka.paths import DataPaths, resolve_data_paths
from yanka.records.io import read_record
from yanka.records.models import Record, RecordStatus
from yanka.vectors.filters import VectorSearchFilters
from yanka.vectors.search import search_records


@dataclass(frozen=True)
class ContextRecord:
    """A related on-disk record loaded for extraction context."""

    file_reference: str
    path: Path
    record: Record
    raw_markdown: str
    score: float | None = None


def find_related_records_for_ingest(
    raw_dump: str,
    paths: DataPaths | None = None,
    *,
    limit: int | None = None,
    config: EmbeddingConfig | None = None,
) -> list[ContextRecord]:
    """Find semantically related active records for the ingest extraction prompt."""
    return search_related_records(raw_dump, paths, limit=limit, config=config)


def search_related_records(
    raw_dump: str,
    paths: DataPaths | None = None,
    *,
    limit: int | None = None,
    config: EmbeddingConfig | None = None,
) -> list[ContextRecord]:
    """Embed the raw dump, search records, and load markdown from disk."""
    resolved = paths if paths is not None else resolve_data_paths()
    max_results = _resolve_context_search_limit(resolved, limit)
    hits = search_records(
        raw_dump,
        resolved,
        filters=VectorSearchFilters(status=RecordStatus.ACTIVE.value),
        limit=max_results,
        config=config,
    )

    loaded: list[ContextRecord] = []
    seen: set[str] = set()
    for hit in hits:
        file_reference = hit.get("file_reference")
        if not isinstance(file_reference, str) or file_reference in seen:
            continue
        path = _record_path(resolved, file_reference)
        if not path.is_file():
            continue
        record_file = read_record(path)
        loaded.append(
            ContextRecord(
                file_reference=file_reference,
                path=path,
                record=record_file.record,
                raw_markdown=record_file.raw_text,
                score=_hit_score(hit),
            )
        )
        seen.add(file_reference)
    return loaded


def format_related_records_for_prompt(records: list[ContextRecord]) -> str:
    """Format related records for injection before the user's raw dump."""
    if not records:
        return ""
    parts: list[str] = []
    for item in records:
        header = f"--- related record: {item.path.name} ---"
        parts.append(f"{header}\n{item.raw_markdown.rstrip()}\n")
    return "\n".join(parts)


def _resolve_context_search_limit(paths: DataPaths, limit: int | None) -> int:
    if limit is not None:
        return limit
    if paths.config_path.is_file():
        return load_config(paths).extraction.context_search_limit
    return default_config(paths.data_dir).extraction.context_search_limit


def _record_path(paths: DataPaths, file_reference: str) -> Path:
    ref = Path(file_reference)
    if ref.parts and ref.parts[0] == "records":
        return paths.data_dir / ref
    return paths.records_dir / ref.name


def _hit_score(hit: dict) -> float | None:
    for key in ("_distance", "_score", "score"):
        value = hit.get(key)
        if isinstance(value, int | float):
            return float(value)
    return None
