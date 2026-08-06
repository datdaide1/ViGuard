"""Query Coverage Validator — startup gate for QRY-01.

Validates that every query intent in the manifest (6/6) has a registered
Query Responder in QueryResponderRegistry, and that no action/refusal intent
has been accidentally registered as a query.

Called at module import time by ``vivi_agent.queries.__init__`` to fail-fast
if query coverage is incomplete.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

from vivi_agent.catalog.manifest import IntentManifest, MANIFEST_PATH, load_manifest
from vivi_agent.queries.registry import QueryResponderRegistry
from vivi_agent.vehicle.execution.errors import BehaviorReadinessError


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
    *,
    manifest: IntentManifest | None = None,
) -> QueryCoverageReport:
    """Compare registered query responders against the intent manifest.

    Parameters
    ----------
    registry:
        QueryResponderRegistry instance.
    manifest_path:
        Path to ``intent_manifest.v1.json``.  Ignored when ``manifest`` is
        given.
    manifest:
        Optional pre-loaded ``IntentManifest``.  When provided, this is used
        directly instead of re-reading ``manifest_path`` off disk.

    Returns
    -------
    QueryCoverageReport
        Detailed coverage result.
    """
    if manifest is None:
        path = pathlib.Path(manifest_path) if manifest_path else MANIFEST_PATH
        manifest = load_manifest(path)

    query_intents: set[str] = set()
    non_query_intents: set[str] = set()

    for definition in manifest.intents:
        if definition.is_query:
            query_intents.add(definition.intent)
        else:
            non_query_intents.add(definition.intent)

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
