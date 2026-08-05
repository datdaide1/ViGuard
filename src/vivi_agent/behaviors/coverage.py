"""Behavior Coverage Validator — startup gate for BEH-01.

Validates that every action/UI intent in the manifest has a registered
``BehaviorConfig`` (or explicit refusal), and that no query intent has
accidentally received an actuator behavior.

Called at module import time by ``vivi_agent.behaviors.__init__`` to fail
fast if the catalog is incomplete.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

from vivi_agent.vehicle.execution.errors import BehaviorReadinessError
from vivi_agent.vehicle.execution.generic import (
    BehaviorConfig,
    validate_behavior_catalog_readiness,
)

# Default manifest path relative to project root
_MANIFEST_DEFAULT = (
    pathlib.Path(__file__).parents[3] / "src" / "vivi_agent" / "catalog" / "intent_manifest.v1.json"
)


@dataclass
class CoverageReport:
    """Result of a single behavior coverage check."""

    total_intents: int = 0
    covered_action: int = 0
    covered_refusal: int = 0
    covered_query: int = 0
    missing_action: list[str] = field(default_factory=list)
    missing_refusal: list[str] = field(default_factory=list)
    extra_action: list[str] = field(default_factory=list)
    query_with_behavior: list[str] = field(default_factory=list)
    passed: bool = False

    @property
    def covered_total(self) -> int:
        return self.covered_action + self.covered_refusal

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        expected_non_query = self.total_intents - self.covered_query
        return (
            f"[{status}] Behavior coverage: "
            f"{self.covered_total}/{expected_non_query} "
            f"(action={self.covered_action}, refusal={self.covered_refusal}, "
            f"query={self.covered_query} — excluded from actuator catalog)"
        )


def validate_behavior_coverage(
    configs: tuple[BehaviorConfig, ...],
    refusal_intent_ids: frozenset[str],
    manifest_path: pathlib.Path | str | None = None,
) -> CoverageReport:
    """Compare *configs* + *refusal_intent_ids* against the intent manifest.

    Parameters
    ----------
    configs:
        Tuple of ``BehaviorConfig`` from the action behavior catalog.
    refusal_intent_ids:
        Frozen set of intent IDs registered as explicit refusals.
    manifest_path:
        Path to ``intent_manifest.v1.json``.  Defaults to the canonical
        project-relative location.

    Returns
    -------
    CoverageReport
        Detailed coverage result.  ``report.passed`` is ``True`` iff every
        action/refusal intent has coverage and no query intent has an actuator
        behavior.
    """
    path = pathlib.Path(manifest_path) if manifest_path else _MANIFEST_DEFAULT
    with path.open(encoding="utf-8") as fh:
        manifest = json.load(fh)

    intents: list[dict] = manifest["intents"]
    report = CoverageReport(total_intents=len(intents))

    action_ids: set[str] = set()
    refusal_ids: set[str] = set()
    query_ids: set[str] = set()

    for entry in intents:
        iid = entry["intent"]
        kind = entry.get("kind", "action")
        if kind == "query":
            query_ids.add(iid)
            report.covered_query += 1
        elif kind == "refusal":
            refusal_ids.add(iid)
        else:
            action_ids.add(iid)

    # Catalog sets
    catalog_action_ids = {cfg.intent_id for cfg in configs}

    # 1. Every action intent must have a BehaviorConfig
    report.missing_action = sorted(action_ids - catalog_action_ids)
    report.covered_action = len(action_ids - set(report.missing_action))

    # 2. Every refusal intent must be in refusal catalog
    report.missing_refusal = sorted(refusal_ids - refusal_intent_ids)
    report.covered_refusal = len(refusal_ids - set(report.missing_refusal))

    # 3. No query intent should appear in the action catalog
    report.query_with_behavior = sorted(query_ids & catalog_action_ids)

    # 4. Extra configs not in manifest (informational only, not a failure)
    report.extra_action = sorted(catalog_action_ids - action_ids - refusal_ids - query_ids)

    report.passed = (
        len(report.missing_action) == 0
        and len(report.missing_refusal) == 0
        and len(report.query_with_behavior) == 0
    )
    return report


def assert_full_coverage(
    configs: tuple[BehaviorConfig, ...],
    refusal_intent_ids: frozenset[str],
    manifest_path: pathlib.Path | str | None = None,
) -> CoverageReport:
    """Run coverage check and raise ``BehaviorReadinessError`` on failure.

    Intended to be called at module import time (startup gate).

    Raises
    ------
    BehaviorReadinessError
        If any action/refusal intent lacks a behavior entry, or if any query
        intent has an actuator behavior registered.
    """
    # First run the per-config structural validation
    validate_behavior_catalog_readiness(configs)

    # Then check manifest coverage
    report = validate_behavior_coverage(configs, refusal_intent_ids, manifest_path)
    if not report.passed:
        problems: list[str] = []
        if report.missing_action:
            problems.append(f"missing action behaviors: {report.missing_action}")
        if report.missing_refusal:
            problems.append(f"missing refusal behaviors: {report.missing_refusal}")
        if report.query_with_behavior:
            problems.append(f"query intents with actuator behavior: {report.query_with_behavior}")
        raise BehaviorReadinessError(
            f"Behavior catalog is incomplete — {'; '.join(problems)}"
        )
    return report
