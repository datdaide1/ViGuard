"""Agent Capability Coverage Gate — COV-01 release gate.

Machine-checkable release gate and readiness validator for ViVi Agent.
Verifies four capability layers:
1. Tool mapping for the complete runtime manifest
2. Behavior / Refusal catalog for every executable intent
3. Query Responders for every query intent
4. Active / Monitor integration 5/5

Also checks cross-layer schema consistency.
Fails closed if any capability is missing or mismatched.
Does NOT claim 109-rule policy correctness (which belongs to Guardrail).
"""

from __future__ import annotations

import pathlib
from typing import Any, Sequence

from vivi_agent.behaviors.catalog import (
    ACTION_BEHAVIOR_CONFIGS,
    REFUSAL_INTENT_IDS,
)
from vivi_agent.behaviors.coverage import (
    CoverageReport as BehaviorCoverageReport,
    validate_behavior_coverage,
)
from vivi_agent.catalog.manifest import (
    BEHAVIORS_BY_KIND,
    MANIFEST_PATH,
    MONITORED_INTENTS,
    IntentManifest,
    load_manifest,
)
from vivi_agent.coverage.models import (
    AgentCoverageReport,
    MonitorCoverageReport,
    SchemaConsistencyReport,
)
from vivi_agent.queries.coverage import (
    QueryCoverageReport,
    validate_query_coverage,
)
from vivi_agent.queries.registry import (
    QUERY_RESPONDER_REGISTRY,
    QueryResponderRegistry,
)
from vivi_agent.tools.mapping.mapper import (
    DEFAULT_MAPPING_RULES,
    MappingCoverageReport,
    MappingRule,
    build_coverage_report as build_tool_mapping_coverage,
)


class AgentReadinessError(RuntimeError):
    """Raised when the Agent Capability Coverage release gate fails closed."""

    def __init__(self, code: str, detail: str, report: AgentCoverageReport | None = None) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.report = report
        self.readiness = False


def validate_agent_coverage(
    manifest: IntentManifest | None = None,
    tool_rules: Sequence[MappingRule] | None = None,
    behavior_configs: Sequence[Any] | None = None,
    refusal_intent_ids: frozenset[str] | None = None,
    query_registry: QueryResponderRegistry | None = None,
    manifest_path: pathlib.Path | str | None = None,
) -> AgentCoverageReport:
    """Validate Agent capability coverage across all 4 layers and schema consistency.

    Parameters
    ----------
    manifest:
        Optional pre-loaded ``IntentManifest``. Loaded from ``manifest_path`` if None.
    tool_rules:
        Sequence of ``MappingRule`` for tool mapping. Defaults to ``DEFAULT_MAPPING_RULES``.
    behavior_configs:
        Sequence of ``BehaviorConfig`` for action behavior catalog. Defaults to ``ACTION_BEHAVIOR_CONFIGS``.
    refusal_intent_ids:
        Frozen set of intent IDs for refusals. Defaults to ``REFUSAL_INTENT_IDS``.
    query_registry:
        ``QueryResponderRegistry`` instance. Defaults to ``QUERY_RESPONDER_REGISTRY``.
    manifest_path:
        Path to ``intent_manifest.v1.json``.

    Returns
    -------
    AgentCoverageReport
        Comprehensive coverage report containing exact missing IDs and overall status.
    """
    if manifest is None:
        path = pathlib.Path(manifest_path) if manifest_path else MANIFEST_PATH
        manifest_obj = load_manifest(path)
    else:
        manifest_obj = manifest
        path = pathlib.Path(manifest_path) if manifest_path else MANIFEST_PATH
    rules = tuple(tool_rules) if tool_rules is not None else DEFAULT_MAPPING_RULES
    b_configs = tuple(behavior_configs) if behavior_configs is not None else ACTION_BEHAVIOR_CONFIGS
    r_ids = refusal_intent_ids if refusal_intent_ids is not None else REFUSAL_INTENT_IDS
    q_reg = query_registry or QUERY_RESPONDER_REGISTRY

    # 1. Tool Mapping Coverage
    tool_mapping_rep: MappingCoverageReport = build_tool_mapping_coverage(rules, manifest_obj)

    # 2. Behavior Catalog Coverage
    behavior_rep: BehaviorCoverageReport = validate_behavior_coverage(
        b_configs, r_ids, manifest=manifest_obj
    )

    # 3. Query Responders Coverage
    query_rep: QueryCoverageReport = validate_query_coverage(q_reg, manifest=manifest_obj)

    # 4. Monitor Integration Coverage (5/5)
    monitored_in_manifest = {defn.intent for defn in manifest_obj.intents if defn.monitor_capable}
    covered_monitored = len(monitored_in_manifest & MONITORED_INTENTS)
    missing_monitored = tuple(sorted(monitored_in_manifest - MONITORED_INTENTS))
    extra_monitored = tuple(sorted(MONITORED_INTENTS - monitored_in_manifest))
    monitor_passed = len(missing_monitored) == 0 and covered_monitored == len(MONITORED_INTENTS)
    monitor_rep = MonitorCoverageReport(
        total_monitored_intents=len(MONITORED_INTENTS),
        covered_monitored=covered_monitored,
        missing_monitored=missing_monitored,
        extra_monitored=extra_monitored,
        passed=monitor_passed,
    )

    # 5. Schema & Consistency Checks
    domain_mismatches: list[str] = []
    kind_mismatches: list[str] = []

    for rule in rules:
        try:
            defn = manifest_obj.by_intent(rule.intent)
            if defn.domain_tool != rule.tool_name:
                domain_mismatches.append(
                    f"rule {rule.key} uses tool {rule.tool_name!r} but intent {rule.intent!r} requires {defn.domain_tool!r}"
                )
        except KeyError:
            domain_mismatches.append(f"rule intent {rule.intent!r} not in manifest")

    # A pre-loaded `manifest` object (see the `manifest` parameter above)
    # bypasses `validate_manifest`'s own kind/behavior_category check, so
    # re-verify it here rather than assuming it always holds.
    for defn in manifest_obj.intents:
        if defn.behavior_category not in BEHAVIORS_BY_KIND.get(defn.kind, frozenset()):
            kind_mismatches.append(
                f"intent {defn.intent!r} has behavior_category {defn.behavior_category!r} incompatible with kind {defn.kind!r}"
            )

    schema_consistency_rep = SchemaConsistencyReport(
        domain_tool_mismatches=tuple(domain_mismatches),
        kind_behavior_mismatches=tuple(kind_mismatches),
        passed=len(domain_mismatches) == 0 and len(kind_mismatches) == 0,
    )

    all_passed = (
        tool_mapping_rep.is_complete
        and behavior_rep.passed
        and query_rep.passed
        and monitor_rep.passed
        and schema_consistency_rep.passed
    )

    return AgentCoverageReport(
        manifest_version=manifest_obj.manifest_version,
        total_manifest_intents=len(manifest_obj.intents),
        tool_mapping_coverage=tool_mapping_rep,
        behavior_coverage=behavior_rep,
        query_coverage=query_rep,
        monitor_coverage=monitor_rep,
        schema_consistency=schema_consistency_rep,
        passed=all_passed,
    )


def assert_agent_readiness(
    manifest: IntentManifest | None = None,
    tool_rules: Sequence[MappingRule] | None = None,
    behavior_configs: Sequence[Any] | None = None,
    refusal_intent_ids: frozenset[str] | None = None,
    query_registry: QueryResponderRegistry | None = None,
    manifest_path: pathlib.Path | str | None = None,
) -> AgentCoverageReport:
    """Validate capability coverage and raise AgentReadinessError if incomplete.

    Raises
    ------
    AgentReadinessError
        If any intent mapping, behavior handler, query responder, monitor integration,
        or schema consistency check fails.
    """
    report = validate_agent_coverage(
        manifest=manifest,
        tool_rules=tool_rules,
        behavior_configs=behavior_configs,
        refusal_intent_ids=refusal_intent_ids,
        query_registry=query_registry,
        manifest_path=manifest_path,
    )

    if not report.passed:
        defects: list[str] = []
        if report.tool_mapping_coverage.missing_intents:
            defects.append(f"missing tool mappings for: {list(report.tool_mapping_coverage.missing_intents)}")
        if report.tool_mapping_coverage.duplicate_keys:
            defects.append(f"duplicate tool mapping keys: {list(report.tool_mapping_coverage.duplicate_keys)}")
        if report.tool_mapping_coverage.ambiguous_keys:
            defects.append(f"ambiguous tool mapping keys: {list(report.tool_mapping_coverage.ambiguous_keys)}")
        if report.behavior_coverage.missing_action:
            defects.append(f"missing action behaviors for: {report.behavior_coverage.missing_action}")
        if report.behavior_coverage.missing_refusal:
            defects.append(f"missing refusal behaviors for: {report.behavior_coverage.missing_refusal}")
        if report.behavior_coverage.query_with_behavior:
            defects.append(f"query intents with actuator behavior: {report.behavior_coverage.query_with_behavior}")
        if report.query_coverage.missing_query:
            defects.append(f"missing query responders for: {report.query_coverage.missing_query}")
        if report.query_coverage.action_in_query_registry:
            defects.append(f"non-query intents in query registry: {report.query_coverage.action_in_query_registry}")
        if report.monitor_coverage.missing_monitored:
            defects.append(f"missing monitor coverage for: {list(report.monitor_coverage.missing_monitored)}")
        if report.schema_consistency.domain_tool_mismatches:
            defects.append(f"schema domain mismatches: {list(report.schema_consistency.domain_tool_mismatches)}")
        if report.schema_consistency.kind_behavior_mismatches:
            defects.append(f"schema kind/behavior mismatches: {list(report.schema_consistency.kind_behavior_mismatches)}")

        detail = "; ".join(defects) or "Capability coverage validation failed"
        raise AgentReadinessError("INCOMPLETE_AGENT_COVERAGE", detail, report=report)

    return report
