"""ViVi Agent Queries package.

This package provides Query Responders for the baseline state queries
and 1 knowledge query) as specified in QRY-01.

Startup gate: ``assert_query_coverage`` is executed at import time to ensure
all manifest query intents have registered responders before the agent accepts traffic.
"""

from __future__ import annotations

from vivi_agent.queries.coverage import (
    QueryCoverageReport,
    assert_query_coverage,
    validate_query_coverage,
)
from vivi_agent.queries.knowledge import (
    FEATURE_KNOWLEDGE_BASE,
    ExplainFeatureResponder,
    FeatureKnowledge,
    lookup_feature_knowledge,
)
from vivi_agent.queries.models import QueryResult, QueryResultSource, QueryStatus
from vivi_agent.queries.registry import (
    QUERY_RESPONDER_REGISTRY,
    QueryResponderRegistry,
    build_default_query_registry,
)
from vivi_agent.queries.state_queries import (
    AvhQueryResponder,
    BatteryQueryResponder,
    DoorLockQueryResponder,
    GearQueryResponder,
    SpeedQueryResponder,
)

__all__ = [
    # Models
    "QueryStatus",
    "QueryResultSource",
    "QueryResult",
    # Registry
    "QueryResponderRegistry",
    "QUERY_RESPONDER_REGISTRY",
    "build_default_query_registry",
    # State Responders
    "SpeedQueryResponder",
    "BatteryQueryResponder",
    "GearQueryResponder",
    "DoorLockQueryResponder",
    "AvhQueryResponder",
    # Knowledge
    "ExplainFeatureResponder",
    "FeatureKnowledge",
    "FEATURE_KNOWLEDGE_BASE",
    "lookup_feature_knowledge",
    # Coverage
    "QueryCoverageReport",
    "validate_query_coverage",
    "assert_query_coverage",
    # Startup report
    "STARTUP_QUERY_COVERAGE_REPORT",
]

# ---------------------------------------------------------------------------
# Startup gate — runs once at import time
# ---------------------------------------------------------------------------
STARTUP_QUERY_COVERAGE_REPORT: QueryCoverageReport = assert_query_coverage(
    QUERY_RESPONDER_REGISTRY
)
