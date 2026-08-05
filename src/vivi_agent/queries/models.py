"""Typed models for vehicle state and knowledge queries.

This module defines data structures representing query responses, statuses,
and sources used by all Query Responders in QRY-01.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class QueryStatus(str, Enum):
    """Execution status of a query evaluation."""

    ANSWER = "ANSWER"
    UNKNOWN = "UNKNOWN"


class QueryResultSource(str, Enum):
    """Source provenance of the query answer."""

    VEHICLE_STATE = "VEHICLE_STATE"
    KNOWLEDGE_BASE = "KNOWLEDGE_BASE"


@dataclass(frozen=True)
class QueryResult:
    """Immutable result produced by a Query Responder."""

    intent_id: str
    status: QueryStatus
    facts: dict[str, Any] = field(default_factory=dict)
    response_text: str = ""
    source: QueryResultSource = QueryResultSource.VEHICLE_STATE
    observed_at: datetime | None = None
