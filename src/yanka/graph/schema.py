"""LadybugDB graph schema — spec §4."""

from __future__ import annotations

from yanka.graph.store import GraphDb

# Node tables
CONTEXT_DDL = """
CREATE NODE TABLE IF NOT EXISTS Context(
    canonical_name STRING PRIMARY KEY,
    normalized_name STRING,
    depth INT64,
    aliases STRING[]
)
"""

DECISION_DDL = """
CREATE NODE TABLE IF NOT EXISTS Decision(
    file_reference STRING PRIMARY KEY,
    date DATE,
    type STRING,
    status STRING,
    summary STRING,
    tags STRING[]
)
"""

# claim_id is global: "{source_file}:{local_id}" (aligned with LanceDB claims table)
CLAIM_DDL = """
CREATE NODE TABLE IF NOT EXISTS Claim(
    claim_id STRING PRIMARY KEY,
    content STRING,
    status STRING,
    source_file STRING
)
"""

PERSON_DDL = """
CREATE NODE TABLE IF NOT EXISTS Person(
    name STRING PRIMARY KEY,
    aliases STRING[]
)
"""

# Relationship tables
CONTAINS_REL_DDL = """
CREATE REL TABLE IF NOT EXISTS contains(FROM Context TO Context)
"""

ABOUT_REL_DDL = """
CREATE REL TABLE IF NOT EXISTS about(FROM Decision TO Context)
"""

HAS_CLAIM_REL_DDL = """
CREATE REL TABLE IF NOT EXISTS has_claim(FROM Decision TO Claim)
"""

SUPERSEDES_REL_DDL = """
CREATE REL TABLE IF NOT EXISTS supersedes(FROM Claim TO Claim)
"""

INVOLVES_REL_DDL = """
CREATE REL TABLE IF NOT EXISTS involves(FROM Decision TO Person)
"""

_NODE_DDLS = (
    CONTEXT_DDL,
    DECISION_DDL,
    CLAIM_DDL,
    PERSON_DDL,
)

_REL_DDLS = (
    CONTAINS_REL_DDL,
    ABOUT_REL_DDL,
    HAS_CLAIM_REL_DDL,
    SUPERSEDES_REL_DDL,
    INVOLVES_REL_DDL,
)


def init_graph_schema(graph: GraphDb) -> None:
    """Create all node and relationship tables (idempotent)."""
    conn = graph.connection
    for ddl in _NODE_DDLS:
        conn.execute(ddl.strip())
    for ddl in _REL_DDLS:
        conn.execute(ddl.strip())
