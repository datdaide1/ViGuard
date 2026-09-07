"""Aegis Agent Behaviors package.

This package declares the complete runtime behavior catalog: executable actions
plus one explicit refusal. Exact counts are validated against the manifest.

Startup gate: ``assert_full_coverage`` is called at import time.  Any missing
behavior entry will raise ``BehaviorReadinessError`` immediately, preventing
a partially-configured agent from serving requests.
"""

from __future__ import annotations

from vehicle_agent.behaviors.catalog import (
    ACTION_BEHAVIOR_CONFIGS,
    BEHAVIOR_CATALOG,
    REFUSAL_INTENT_IDS,
    get_behavior_config,
)
from vehicle_agent.behaviors.coverage import (
    CoverageReport,
    assert_full_coverage,
    validate_behavior_coverage,
)
from vehicle_agent.behaviors.refusal import (
    REFUSAL_CATALOG,
    RefusalEntry,
    get_refusal,
    is_refusal,
)

__all__ = [
    # Catalog
    "ACTION_BEHAVIOR_CONFIGS",
    "BEHAVIOR_CATALOG",
    "REFUSAL_INTENT_IDS",
    "get_behavior_config",
    # Refusal
    "REFUSAL_CATALOG",
    "RefusalEntry",
    "get_refusal",
    "is_refusal",
    # Coverage
    "CoverageReport",
    "validate_behavior_coverage",
    "assert_full_coverage",
    # Runtime coverage report (populated at import time)
    "STARTUP_COVERAGE_REPORT",
]

# ---------------------------------------------------------------------------
# Startup gate — runs once at import time
# ---------------------------------------------------------------------------
STARTUP_COVERAGE_REPORT: CoverageReport = assert_full_coverage(
    ACTION_BEHAVIOR_CONFIGS,
    REFUSAL_INTENT_IDS,
)
