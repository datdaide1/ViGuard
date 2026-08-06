"""Capability Coverage Data Models for COV-01.

Provides data structures representing non-raising coverage reports and readiness
diagnostics across all four capability layers:
1. Tool Mapping (53/53)
2. Behavior / Refusal Catalog (47/47)
3. Query Responders (6/6)
4. Active Action / Monitor Integration (5/5)

Design notes
------------
* Dataclasses are immutable (frozen=True or typed properties) for safety.
* Reports provide human-readable `.summary()` and machine-readable breakdown.
* Does NOT claim Guardrail policy correctness (109-rule policy checks belong to
  Guardrail team); only validates Agent capability readiness.
"""

from __future__ import annotations

from dataclasses import dataclass

from vivi_agent.behaviors.coverage import CoverageReport as BehaviorCoverageReport
from vivi_agent.queries.coverage import QueryCoverageReport
from vivi_agent.tools.mapping.mapper import MappingCoverageReport


@dataclass(frozen=True)
class MonitorCoverageReport:
    """Coverage analysis for the 5 monitored intents."""

    total_monitored_intents: int = 5
    covered_monitored: int = 0
    missing_monitored: tuple[str, ...] = ()
    extra_monitored: tuple[str, ...] = ()
    passed: bool = False

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] Monitor integration coverage: "
            f"{self.covered_monitored}/{self.total_monitored_intents} monitored intents supported"
        )


@dataclass(frozen=True)
class SchemaConsistencyReport:
    """Consistency check across Tool Schema, Manifest, Behaviors, and Queries."""

    domain_tool_mismatches: tuple[str, ...] = ()
    kind_behavior_mismatches: tuple[str, ...] = ()
    passed: bool = True

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        issues_count = len(self.domain_tool_mismatches) + len(self.kind_behavior_mismatches)
        return (
            f"[{status}] Schema consistency: "
            f"{'no issues found' if self.passed else f'{issues_count} mismatches found'}"
        )


@dataclass(frozen=True)
class AgentCoverageReport:
    """Aggregate Agent Capability Coverage Report for COV-01."""

    manifest_version: str
    total_manifest_intents: int
    tool_mapping_coverage: MappingCoverageReport
    behavior_coverage: BehaviorCoverageReport
    query_coverage: QueryCoverageReport
    monitor_coverage: MonitorCoverageReport
    schema_consistency: SchemaConsistencyReport
    passed: bool

    def summary(self) -> str:
        """Return human and machine-readable text report detailing exact missing IDs."""
        status = "PASS" if self.passed else "FAIL"
        lines = [
            f"============================================================",
            f"AGENT CAPABILITY COVERAGE REPORT [{status}] (v{self.manifest_version})",
            f"============================================================",
            f"Total Manifest Intents: {self.total_manifest_intents}",
            f"",
            f"1. Tool Mapping (53/53):",
            f"   - Missing intents ({len(self.tool_mapping_coverage.missing_intents)}): {list(self.tool_mapping_coverage.missing_intents)}",
            f"   - Duplicate keys ({len(self.tool_mapping_coverage.duplicate_keys)}): {len(self.tool_mapping_coverage.duplicate_keys)}",
            f"   - Ambiguous keys ({len(self.tool_mapping_coverage.ambiguous_keys)}): {len(self.tool_mapping_coverage.ambiguous_keys)}",
            f"",
            f"2. Behavior Catalog (47/47):",
            f"   - Summary: {self.behavior_coverage.summary()}",
            f"   - Missing action behaviors: {self.behavior_coverage.missing_action}",
            f"   - Missing refusal behaviors: {self.behavior_coverage.missing_refusal}",
            f"   - Query with actuator behavior: {self.behavior_coverage.query_with_behavior}",
            f"",
            f"3. Query Responders (6/6):",
            f"   - Summary: {self.query_coverage.summary()}",
            f"   - Missing query responders: {self.query_coverage.missing_query}",
            f"   - Non-query in query registry: {self.query_coverage.action_in_query_registry}",
            f"",
            f"4. Monitor Integration (5/5):",
            f"   - Summary: {self.monitor_coverage.summary()}",
            f"   - Missing monitored intents: {list(self.monitor_coverage.missing_monitored)}",
            f"",
            f"5. Schema Consistency:",
            f"   - Domain tool mismatches: {list(self.schema_consistency.domain_tool_mismatches)}",
            f"   - Kind behavior mismatches: {list(self.schema_consistency.kind_behavior_mismatches)}",
            f"============================================================",
            f"RELEASE GATE STATUS: {status}",
            f"============================================================",
        ]
        return "\n".join(lines)
