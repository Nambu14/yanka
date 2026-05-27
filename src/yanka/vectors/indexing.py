"""Index records and claims into LanceDB."""

from __future__ import annotations

from typing import Any

from yanka.config import EmbeddingConfig
from yanka.embeddings import embed
from yanka.paths import DataPaths, resolve_data_paths
from yanka.records.markdown import record_to_markdown
from yanka.records.models import Claim, Record
from yanka.vectors.claims import get_claims_table
from yanka.vectors.filters import predicate_equals
from yanka.vectors.records import get_records_table


def record_embedding_text(record: Record) -> str:
    """Text embedded for full-record vector search (spec §5)."""
    return record_to_markdown(record)


def file_reference_for_record(record: Record, paths: DataPaths) -> str:
    """Stable LanceDB key relative to data_dir (e.g. records/2026-05-14-slug.md)."""
    if record.source_path is None:
        msg = "record.source_path is required for indexing"
        raise ValueError(msg)
    try:
        root = paths.data_dir.resolve()
        return record.source_path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        msg = "record.source_path must be under data_dir"
        raise ValueError(msg) from exc


def record_to_vector_row(
    record: Record,
    vector: list[float],
    file_reference: str,
) -> dict[str, Any]:
    context_path = "/".join(record.context_path)
    project = record.context_path[0] if record.context_path else ""
    return {
        "file_reference": file_reference,
        "vector": vector,
        "date": record.date,
        "context_path": context_path,
        "project": project,
        "status": record.status.value,
        "type": record.type.value,
        "tags": list(record.tags),
        "summary": record.decision,
    }


def index_record(
    record: Record,
    paths: DataPaths | None = None,
    *,
    config: EmbeddingConfig | None = None,
) -> str:
    """Embed a record and upsert into the records vector table.

    Returns file_reference.
    """
    resolved = paths if paths is not None else resolve_data_paths()
    file_reference = file_reference_for_record(record, resolved)
    text = record_embedding_text(record)
    vector = embed([text], config=config)[0]
    row = record_to_vector_row(record, vector, file_reference)

    table = get_records_table(resolved)
    table.delete(predicate_equals("file_reference", file_reference))
    table.add([row])
    return file_reference


def claim_id_for_claim(file_reference: str, claim: Claim) -> str:
    """Composite primary key: ``{file_reference}:{claim.id}`` (spec §5)."""
    return f"{file_reference}:{claim.id}"


def claim_to_vector_row(
    claim: Claim,
    record: Record,
    vector: list[float],
    *,
    file_reference: str,
    claim_id: str,
) -> dict[str, Any]:
    context_path = "/".join(record.context_path)
    project = record.context_path[0] if record.context_path else ""
    return {
        "claim_id": claim_id,
        "vector": vector,
        "content": claim.content,
        "status": claim.status.value,
        "source_file": file_reference,
        "date": record.date,
        "context_path": context_path,
        "project": project,
    }


def index_claims(
    record: Record,
    paths: DataPaths | None = None,
    *,
    config: EmbeddingConfig | None = None,
) -> list[str]:
    """Embed each claim and upsert into the claims vector table.

    Replaces all claim rows for this record's source_file (drops removed claims).
    Returns claim_id for each indexed claim.
    """
    resolved = paths if paths is not None else resolve_data_paths()
    file_reference = file_reference_for_record(record, resolved)
    table = get_claims_table(resolved)
    table.delete(predicate_equals("source_file", file_reference))

    if not record.claims:
        return []

    texts = [claim.content for claim in record.claims]
    vectors = embed(texts, config=config)
    rows: list[dict[str, Any]] = []
    claim_ids: list[str] = []
    for claim, vector in zip(record.claims, vectors, strict=True):
        claim_id = claim_id_for_claim(file_reference, claim)
        rows.append(
            claim_to_vector_row(
                claim,
                record,
                vector,
                file_reference=file_reference,
                claim_id=claim_id,
            )
        )
        claim_ids.append(claim_id)

    table.add(rows)
    return claim_ids
