"""Persist ingested records to filesystem and indexes — spec §7 step 9."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from yanka.config import EmbeddingConfig, load_config
from yanka.graph import get_graph_db, index_record_graph, init_graph_schema
from yanka.graph.store import GraphDb
from yanka.paths import DataPaths
from yanka.records.io import write_record
from yanka.records.models import Record
from yanka.vectors.indexing import (
    file_reference_for_record,
    index_claims,
    index_record,
)


@dataclass
class WriteResult:
    """Outcome of writing a record and updating disposable indexes."""

    path: Path
    file_reference: str
    graph_ok: bool = False
    vectors_ok: bool = False
    index_errors: list[str] = field(default_factory=list)


def write_ingested_record(
    paths: DataPaths,
    record: Record,
    *,
    filename: str | None = None,
    graph: GraphDb | None = None,
    embedding_config: EmbeddingConfig | None = None,
) -> WriteResult:
    """Write markdown + changelog first, then graph and vector indexes.

    Index failures are recorded on the result; the markdown file is never removed.
    """
    path = write_record(paths, record, filename=filename)
    record.source_path = path.resolve()
    file_reference = file_reference_for_record(record, paths)

    graph_db = graph if graph is not None else get_graph_db(paths)
    init_graph_schema(graph_db)

    result = WriteResult(path=path, file_reference=file_reference)
    _index_graph(record, paths, graph_db, result)
    _index_vectors(record, paths, embedding_config, result)
    return result


def _index_graph(
    record: Record,
    paths: DataPaths,
    graph: GraphDb,
    result: WriteResult,
) -> None:
    try:
        index_record_graph(record, graph, paths)
    except Exception as exc:
        result.index_errors.append(f"[graph] {exc}")
        return
    result.graph_ok = True


def _index_vectors(
    record: Record,
    paths: DataPaths,
    embedding_config: EmbeddingConfig | None,
    result: WriteResult,
) -> None:
    config = embedding_config
    if config is None and paths.config_path.is_file():
        config = load_config(paths).embedding
    try:
        index_record(record, paths, config=config)
        index_claims(record, paths, config=config)
    except Exception as exc:
        result.index_errors.append(f"[vectors] {exc}")
        return
    result.vectors_ok = True
