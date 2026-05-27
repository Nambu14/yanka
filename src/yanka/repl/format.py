"""REPL text formatting for status and record listings."""

from __future__ import annotations

from yanka.paths import DataPaths
from yanka.records.io import iter_records
from yanka.repl.statusline_cache import StatuslineCache


def format_status(paths: DataPaths) -> str:
    """Return a concise local knowledge-base status summary."""
    records = list(iter_records(paths))
    lines = [
        f"Data dir: {paths.data_dir}",
        f"Records: {len(records)}",
    ]
    if not records:
        return "\n".join(lines)

    projects = sorted(
        {
            record_file.record.context_path[0]
            for record_file in records
            if record_file.record.context_path
        }
    )
    if projects:
        lines.append(f"Projects: {', '.join(projects)}")
    latest = max(record_file.record.date for record_file in records)
    lines.append(f"Latest record: {latest.isoformat()}")
    return "\n".join(lines)


def format_history(paths: DataPaths, *, limit: int = 5) -> str:
    """Return recent records with date, status, filename, and summary."""
    records = sorted(
        iter_records(paths),
        key=lambda record_file: (record_file.record.date, record_file.path.name),
        reverse=True,
    )
    if not records:
        return "No records yet."

    lines: list[str] = []
    for record_file in records[:limit]:
        record = record_file.record
        lines.append(
            f"{record.date.isoformat()}  {record.status.value}  "
            f"{record_file.path.name}  {record.decision}"
        )
    return "\n".join(lines)


def format_last(paths: DataPaths) -> str:
    """Return the most recent record summary with file path."""
    records = sorted(
        iter_records(paths),
        key=lambda record_file: (record_file.record.date, record_file.path.name),
        reverse=True,
    )
    if not records:
        return "No records yet."
    latest = records[0]
    record = latest.record
    return (
        f"{record.date.isoformat()}  {record.status.value}  {latest.path.name}  "
        f"{record.decision}\nPath: {latest.path}"
    )


def format_statusline(
    paths: DataPaths,
    *,
    cache: StatuslineCache | None = None,
) -> str:
    """One-line prompt context summary."""
    if cache is not None:
        record_count = cache.record_count()
    else:
        record_count = sum(1 for _ in iter_records(paths))
    llm_label = "llm: default"
    if paths.config_path.is_file():
        from yanka.config import load_config

        config = load_config(paths)
        llm_label = f"llm: {config.llm.provider}/{config.llm.model}"
    return f"dir: {paths.data_dir.name} | records: {record_count} | {llm_label}"
