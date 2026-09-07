"""Agent Capability Coverage package (COV-01).

Provides machine-checkable release gate and report for Agent capabilities across:
1. Tool Mapping for the complete runtime manifest
2. Behavior / Refusal Catalog for every executable intent
3. Query Responders for every query intent
4. Active / Monitor Integration (5/5)
"""

from vehicle_agent.coverage.gate import (
    AgentReadinessError,
    assert_agent_readiness,
    validate_agent_coverage,
)
from vehicle_agent.coverage.models import (
    AgentCoverageReport,
    MonitorCoverageReport,
    SchemaConsistencyReport,
)

__all__ = [
    "AgentCoverageReport",
    "AgentReadinessError",
    "MonitorCoverageReport",
    "SchemaConsistencyReport",
    "assert_agent_readiness",
    "validate_agent_coverage",
]
