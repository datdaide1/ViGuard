"""ViVi Agent Behaviors package.

This package declares the full behavior catalog for all 47 action/UI intents
(46 executable + 1 explicit refusal) as specified in BEH-01.

Startup gate: ``assert_full_coverage`` is called at import time.  Any missing
behavior entry will raise ``BehaviorReadinessError`` immediately, preventing
a partially-configured agent from serving requests.
"""

from __future__ import annotations

from vivi_agent.behaviors.catalog import (
    ACTION_BEHAVIOR_CONFIGS,
    BEHAVIOR_CATALOG,
    REFUSAL_INTENT_IDS,
    get_behavior_config,
)
from vivi_agent.behaviors.coverage import (
    CoverageReport,
    assert_full_coverage,
    validate_behavior_coverage,
)
from vivi_agent.behaviors.refusal import (
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
