"""Index records into the Ladybug graph — spec §4."""

from __future__ import annotations

from yanka.graph.context import upsert_context_path
from yanka.graph.store import GraphDb
from yanka.paths import DataPaths, resolve_data_paths
from yanka.records.models import ClaimStatus, ClaimSupersedes, Record
from yanka.vectors.indexing import claim_id_for_claim, file_reference_for_record


def index_record_graph(
    record: Record,
    graph: GraphDb,
    paths: DataPaths | None = None,
) -> str:
    """Upsert Decision, Claims, People, context links, and claim supersede edges."""
    resolved = paths if paths is not None else resolve_data_paths()
    file_reference = file_reference_for_record(record, resolved)
    leaf_context = upsert_context_path(record.context_path, graph)
    conn = graph.connection

    conn.execute(
        "MERGE (d:Decision {file_reference: $ref}) "
        "ON CREATE SET "
        "d.date = date($date), "
        "d.type = $type, "
        "d.status = $status, "
        "d.summary = $summary, "
        "d.tags = $tags "
        "ON MATCH SET "
        "d.date = date($date), "
        "d.type = $type, "
        "d.status = $status, "
        "d.summary = $summary, "
        "d.tags = $tags",
        parameters={
            "ref": file_reference,
            "date": record.date.isoformat(),
            "type": record.type.value,
            "status": record.status.value,
            "summary": record.decision,
            "tags": record.tags,
        },
    )
    conn.execute(
        "MATCH (d:Decision {file_reference: $ref})-[r:about]->() DELETE r",
        parameters={"ref": file_reference},
    )

    conn.execute(
        "MATCH (d:Decision {file_reference: $ref}), "
        "(c:Context {canonical_name: $leaf}) "
        "MERGE (d)-[:about]->(c)",
        parameters={"ref": file_reference, "leaf": leaf_context},
    )

    conn.execute(
        "MATCH (d:Decision {file_reference: $ref})-[r:has_claim]->() DELETE r",
        parameters={"ref": file_reference},
    )
    conn.execute(
        "MATCH (d:Decision {file_reference: $ref})-[r:involves]->() DELETE r",
        parameters={"ref": file_reference},
    )

    for claim in record.claims:
        claim_id = claim_id_for_claim(file_reference, claim)
        conn.execute(
            "MERGE (cl:Claim {claim_id: $claim_id}) "
            "ON CREATE SET "
            "cl.content = $content, "
            "cl.status = $status, "
            "cl.source_file = $source_file "
            "ON MATCH SET "
            "cl.content = $content, "
            "cl.status = $status, "
            "cl.source_file = $source_file",
            parameters={
                "claim_id": claim_id,
                "content": claim.content,
                "status": claim.status.value,
                "source_file": file_reference,
            },
        )
        conn.execute(
            "MATCH (d:Decision {file_reference: $ref}), "
            "(cl:Claim {claim_id: $claim_id}) "
            "MERGE (d)-[:has_claim]->(cl)",
            parameters={"ref": file_reference, "claim_id": claim_id},
        )

    for person in record.people:
        conn.execute(
            "MERGE (p:Person {name: $name}) ON CREATE SET p.aliases = []",
            parameters={"name": person},
        )
        conn.execute(
            "MATCH (d:Decision {file_reference: $ref}), "
            "(p:Person {name: $name}) "
            "MERGE (d)-[:involves]->(p)",
            parameters={"ref": file_reference, "name": person},
        )

    _index_claim_supersedes(record, file_reference, graph)

    return file_reference


def resolve_superseded_claim_id(supersedes: ClaimSupersedes) -> str:
    """Map frontmatter ``file`` + ``claim`` to global ``claim_id``."""
    file_reference = supersedes.file
    if not file_reference.startswith("records/"):
        file_reference = f"records/{file_reference}"
    return f"{file_reference}:{supersedes.claim}"


def _index_claim_supersedes(
    record: Record,
    file_reference: str,
    graph: GraphDb,
) -> None:
    conn = graph.connection

    conn.execute(
        "MATCH (cl:Claim {source_file: $source_file})-[r:supersedes]->() DELETE r",
        parameters={"source_file": file_reference},
    )

    for claim in record.claims:
        if claim.supersedes is None:
            continue
        new_id = claim_id_for_claim(file_reference, claim)
        old_id = resolve_superseded_claim_id(claim.supersedes)
        conn.execute(
            "MERGE (old:Claim {claim_id: $old_id})",
            parameters={"old_id": old_id},
        )
        conn.execute(
            "MATCH (new:Claim {claim_id: $new_id}), "
            "(old:Claim {claim_id: $old_id}) "
            "MERGE (new)-[:supersedes]->(old)",
            parameters={"new_id": new_id, "old_id": old_id},
        )
        conn.execute(
            "MATCH (old:Claim {claim_id: $old_id}) "
            "SET old.status = $status",
            parameters={"old_id": old_id, "status": ClaimStatus.SUPERSEDED.value},
        )
