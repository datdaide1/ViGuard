"""Agent Capability Coverage package (COV-01).

Provides machine-checkable release gate and report for Agent capabilities across:
1. Tool Mapping (53/53)
2. Behavior / Refusal Catalog (47/47)
3. Query Responders (6/6)
4. Active / Monitor Integration (5/5)
"""

from vivi_agent.coverage.gate import (
    AgentReadinessError,
    assert_agent_readiness,
    validate_agent_coverage,
)
from vivi_agent.coverage.models import (
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
