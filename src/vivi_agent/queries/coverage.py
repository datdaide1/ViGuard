"""Query Coverage Validator — startup gate for QRY-01.

Validates that every query intent in the manifest (6/6) has a registered
Query Responder in QueryResponderRegistry, and that no action/refusal intent
has been accidentally registered as a query.

Called at module import time by ``vivi_agent.queries.__init__`` to fail-fast
if query coverage is incomplete.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

from vivi_agent.queries.registry import QueryResponderRegistry
from vivi_agent.vehicle.execution.errors import BehaviorReadinessError

# Default manifest path relative to project root
_MANIFEST_DEFAULT = (
    pathlib.Path(__file__).parents[3] / "src" / "vivi_agent" / "catalog" / "intent_manifest.v1.json"
)


@dataclass
class QueryCoverageReport:
    """Result of a query coverage validation check."""

    total_query_intents: int = 0
    covered_query: int = 0
    missing_query: list[str] = field(default_factory=list)
    action_in_query_registry: list[str] = field(default_factory=list)
    passed: bool = False

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] Query coverage: "
            f"{self.covered_query}/{self.total_query_intents} query intents registered"
        )


def validate_query_coverage(
    registry: QueryResponderRegistry,
    manifest_path: pathlib.Path | str | None = None,
) -> QueryCoverageReport:
    """Compare registered query responders against the intent manifest.

    Parameters
    ----------
    registry:
        QueryResponderRegistry instance.
    manifest_path:
        Path to ``intent_manifest.v1.json``.

    Returns
    -------
    QueryCoverageReport
        Detailed coverage result.
    """
    path = pathlib.Path(manifest_path) if manifest_path else _MANIFEST_DEFAULT
    with path.open(encoding="utf-8") as fh:
        manifest = json.load(fh)

    intents: list[dict] = manifest["intents"]

    query_intents: set[str] = set()
    non_query_intents: set[str] = set()

    for entry in intents:
        iid = entry["intent"]
        kind = entry.get("kind", "action")
        if kind == "query":
            query_intents.add(iid)
        else:
            non_query_intents.add(iid)

    report = QueryCoverageReport(total_query_intents=len(query_intents))

    registered = registry.registered_intents()

    report.missing_query = sorted(query_intents - registered)
    report.covered_query = len(query_intents - set(report.missing_query))

    # Zero actuator in query registry check
    report.action_in_query_registry = sorted(non_query_intents & registered)

    report.passed = (
        len(report.missing_query) == 0
        and len(report.action_in_query_registry) == 0
    )
    return report


def assert_query_coverage(
    registry: QueryResponderRegistry,
    manifest_path: pathlib.Path | str | None = None,
) -> QueryCoverageReport:
    """Run query coverage check and raise ``BehaviorReadinessError`` on failure.

    Raises
    ------
    BehaviorReadinessError
        If any manifest query intent lacks a Query Responder, or if any
        action/refusal intent is registered in the query registry.
    """
    report = validate_query_coverage(registry, manifest_path)
    if not report.passed:
        problems: list[str] = []
        if report.missing_query:
            problems.append(f"missing query responders for: {report.missing_query}")
        if report.action_in_query_registry:
            problems.append(f"non-query intents in query registry: {report.action_in_query_registry}")
        raise BehaviorReadinessError(
            f"Query responder coverage is incomplete — {'; '.join(problems)}"
        )
    return report
