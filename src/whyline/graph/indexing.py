"""Index records into the Ladybug graph — spec §4."""

from __future__ import annotations

from whyline.graph.context import upsert_context_path
from whyline.graph.store import GraphDb
from whyline.paths import DataPaths, resolve_data_paths
from whyline.records.models import ClaimSupersedes, Record
from whyline.vectors.indexing import claim_id_for_claim, file_reference_for_record


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

    ref = _escape(file_reference)
    leaf = _escape(leaf_context)
    tags_literal = _string_list_literal(record.tags)

    conn.execute(
        f"MERGE (d:Decision {{file_reference: '{ref}'}}) "
        f"ON CREATE SET "
        f"d.date = date('{record.date.isoformat()}'), "
        f"d.type = '{_escape(record.type.value)}', "
        f"d.status = '{_escape(record.status.value)}', "
        f"d.summary = '{_escape(record.decision)}', "
        f"d.tags = {tags_literal}"
    )
    conn.execute(
        f"MATCH (d:Decision {{file_reference: '{ref}'}}) "
        f"SET d.date = date('{record.date.isoformat()}'), "
        f"d.type = '{_escape(record.type.value)}', "
        f"d.status = '{_escape(record.status.value)}', "
        f"d.summary = '{_escape(record.decision)}', "
        f"d.tags = {tags_literal}"
    )
    conn.execute(
        f"MATCH (d:Decision {{file_reference: '{ref}'}})-[r:about]->() DELETE r"
    )

    conn.execute(
        f"MATCH (d:Decision {{file_reference: '{ref}'}}), "
        f"(c:Context {{canonical_name: '{leaf}'}}) "
        f"MERGE (d)-[:about]->(c)"
    )

    conn.execute(
        f"MATCH (d:Decision {{file_reference: '{ref}'}})-[r:has_claim]->() DELETE r"
    )
    conn.execute(
        f"MATCH (d:Decision {{file_reference: '{ref}'}})-[r:involves]->() DELETE r"
    )

    for claim in record.claims:
        claim_id = claim_id_for_claim(file_reference, claim)
        cid = _escape(claim_id)
        conn.execute(
            f"MERGE (cl:Claim {{claim_id: '{cid}'}}) "
            f"ON CREATE SET "
            f"cl.content = '{_escape(claim.content)}', "
            f"cl.status = '{_escape(claim.status.value)}', "
            f"cl.source_file = '{ref}'"
        )
        conn.execute(
            f"MATCH (cl:Claim {{claim_id: '{cid}'}}) "
            f"SET cl.content = '{_escape(claim.content)}', "
            f"cl.status = '{_escape(claim.status.value)}', "
            f"cl.source_file = '{ref}'"
        )
        conn.execute(
            f"MATCH (d:Decision {{file_reference: '{ref}'}}), "
            f"(cl:Claim {{claim_id: '{cid}'}}) "
            f"MERGE (d)-[:has_claim]->(cl)"
        )

    for person in record.people:
        name = _escape(person)
        conn.execute(
            f"MERGE (p:Person {{name: '{name}'}}) ON CREATE SET p.aliases = []"
        )
        conn.execute(
            f"MATCH (d:Decision {{file_reference: '{ref}'}}), "
            f"(p:Person {{name: '{name}'}}) "
            f"MERGE (d)-[:involves]->(p)"
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
    ref = _escape(file_reference)
    conn = graph.connection

    conn.execute(
        f"MATCH (cl:Claim {{source_file: '{ref}'}})-[r:supersedes]->() DELETE r"
    )

    for claim in record.claims:
        if claim.supersedes is None:
            continue
        new_id = _escape(claim_id_for_claim(file_reference, claim))
        old_id = _escape(resolve_superseded_claim_id(claim.supersedes))
        conn.execute(f"MERGE (old:Claim {{claim_id: '{old_id}'}})")
        conn.execute(
            f"MATCH (new:Claim {{claim_id: '{new_id}'}}), "
            f"(old:Claim {{claim_id: '{old_id}'}}) "
            f"MERGE (new)-[:supersedes]->(old)"
        )
        conn.execute(
            f"MATCH (old:Claim {{claim_id: '{old_id}'}}) "
            f"SET old.status = 'superseded'"
        )


def _string_list_literal(values: list[str]) -> str:
    if not values:
        return "[]"
    parts = ", ".join(f"'{_escape(value)}'" for value in values)
    return f"[{parts}]"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")
