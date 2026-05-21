"""Rebuild disposable graph and vector indexes from markdown records."""

from __future__ import annotations

import shutil

from whyline.config import EmbeddingConfig, load_config
from whyline.graph import get_graph_db, index_record_graph, init_graph_schema
from whyline.graph.store import clear_graph_db_cache
from whyline.paths import DataPaths, ensure_data_layout, resolve_data_paths
from whyline.records.io import iter_records
from whyline.vectors.indexing import index_claims, index_record
from whyline.vectors.store import clear_vector_db_cache


def reset_indexes(paths: DataPaths | None = None) -> DataPaths:
    """Wipe graph/ and vectors/ under the data dir and recreate empty layout.

    Does not touch records/ or changelog.jsonl.
    """
    resolved = paths if paths is not None else resolve_data_paths()
    clear_graph_db_cache()
    clear_vector_db_cache()

    for directory in (resolved.graph_dir, resolved.vectors_dir):
        if directory.exists():
            shutil.rmtree(directory)

    return ensure_data_layout(resolved)


def rebuild_indexes(
    paths: DataPaths | None = None,
    *,
    config: EmbeddingConfig | None = None,
) -> int:
    """Reset indexes, then rebuild graph and vectors from all records on disk."""
    resolved = reset_indexes(paths)
    embedding_config = config
    if embedding_config is None and resolved.config_path.is_file():
        embedding_config = load_config(resolved).embedding

    graph = get_graph_db(resolved)
    init_graph_schema(graph)

    count = 0
    for record_file in iter_records(resolved):
        record = record_file.record
        index_record_graph(record, graph, resolved)
        index_record(record, resolved, config=embedding_config)
        index_claims(record, resolved, config=embedding_config)
        count += 1

    return count
