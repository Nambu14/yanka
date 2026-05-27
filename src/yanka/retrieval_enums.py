"""Retrieval enums shared by graph and query_analysis (avoids import cycles)."""

from __future__ import annotations

from enum import StrEnum


class QueryType(StrEnum):
    CURRENT_STATE = "current_state"
    HISTORICAL = "historical"
    SPECIFIC_DECISION = "specific_decision"
    EXPLORATORY = "exploratory"
    RELATIONSHIP = "relationship"
    PERSON = "person"


class StatusFilter(StrEnum):
    ACTIVE = "active"
    ALL = "all"


class RetrievalSource(StrEnum):
    GRAPH = "graph"
    VECTOR = "vector"
