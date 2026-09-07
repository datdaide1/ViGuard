"""Automated unit & integration tests for COV-01 Agent Capability Coverage Gate."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from vehicle_agent.coverage.gate import (
    AgentReadinessError,
    assert_agent_readiness,
    validate_agent_coverage,
)
from vehicle_agent.coverage.models import AgentCoverageReport
from vehicle_agent.queries.registry import QueryResponderRegistry
from vehicle_agent.tools.mapping.mapper import MappingRule


class TestAgentCoverageGate(unittest.TestCase):
    """Test suite for COV-01 capability coverage gate and readiness release checks."""

    def test_full_system_coverage_pass(self) -> None:
        """Verify the live production catalog passes all 4 capability layers 100%."""
        report = validate_agent_coverage()
        self.assertIsInstance(report, AgentCoverageReport)
        self.assertTrue(report.passed, f"Capability gate failed:\n{report.summary()}")
        self.assertEqual(report.total_manifest_intents, 123)
        self.assertTrue(report.tool_mapping_coverage.is_complete)
        self.assertTrue(report.behavior_coverage.passed)
        self.assertTrue(report.query_coverage.passed)
        self.assertTrue(report.monitor_coverage.passed)
        self.assertTrue(report.schema_consistency.passed)

    def test_assert_agent_readiness_succeeds_on_valid_catalog(self) -> None:
        """assert_agent_readiness must return the passing report without raising."""
        report = assert_agent_readiness()
        self.assertTrue(report.passed)

    def test_missing_tool_mapping_fails_gate_with_exact_id(self) -> None:
        """Incomplete tool mapping must fail readiness and identify missing intent ID."""
        # Create incomplete rules by removing one intent mapping (open_door)
        from vehicle_agent.tools.mapping.mapper import DEFAULT_MAPPING_RULES
        incomplete_rules = tuple(
            rule for rule in DEFAULT_MAPPING_RULES if rule.intent != "open_door"
        )

        report = validate_agent_coverage(tool_rules=incomplete_rules)
        self.assertFalse(report.passed)
        self.assertIn("open_door", report.tool_mapping_coverage.missing_intents)

        with self.assertRaises(AgentReadinessError) as ctx:
            assert_agent_readiness(tool_rules=incomplete_rules)
        
        self.assertIn("open_door", str(ctx.exception))
        self.assertEqual(ctx.exception.code, "INCOMPLETE_AGENT_COVERAGE")

    def test_missing_behavior_fails_gate_with_exact_id(self) -> None:
        """Missing behavior handler must fail readiness and report exact intent ID."""
        from vehicle_agent.behaviors.catalog import ACTION_BEHAVIOR_CONFIGS
        incomplete_behaviors = tuple(
            cfg for cfg in ACTION_BEHAVIOR_CONFIGS if cfg.intent_id != "turnon_highbeam"
        )

        report = validate_agent_coverage(behavior_configs=incomplete_behaviors)
        self.assertFalse(report.passed)
        self.assertIn("turnon_highbeam", report.behavior_coverage.missing_action)

        with self.assertRaises(AgentReadinessError) as ctx:
            assert_agent_readiness(behavior_configs=incomplete_behaviors)
        self.assertIn("turnon_highbeam", str(ctx.exception))

    def test_missing_query_responder_fails_gate_with_exact_id(self) -> None:
        """Missing query responder must fail readiness and report exact intent ID."""
        empty_query_reg = QueryResponderRegistry()
        report = validate_agent_coverage(query_registry=empty_query_reg)
        self.assertFalse(report.passed)
        self.assertEqual(len(report.query_coverage.missing_query), 10)

        with self.assertRaises(AgentReadinessError) as ctx:
            assert_agent_readiness(query_registry=empty_query_reg)
        self.assertIn("get_current_speed", str(ctx.exception))

    def test_domain_tool_mismatch_fails_consistency(self) -> None:
        """A tool mapping rule with mismatched domain_tool must fail consistency check."""
        from vehicle_agent.tools.mapping.mapper import DEFAULT_MAPPING_RULES
        mismatched_rule = MappingRule("control_light", "open", "driver_door", "open_door")
        modified_rules = (mismatched_rule,) + DEFAULT_MAPPING_RULES[1:]

        report = validate_agent_coverage(tool_rules=modified_rules)
        self.assertFalse(report.passed)
        self.assertFalse(report.schema_consistency.passed)
        self.assertTrue(len(report.schema_consistency.domain_tool_mismatches) > 0)

    def test_summary_report_formatting(self) -> None:
        """Summary text must contain all key sections and PASS/FAIL indicators."""
        report = validate_agent_coverage()
        summary_text = report.summary()
        self.assertIn("AGENT CAPABILITY COVERAGE REPORT [PASS]", summary_text)
        self.assertIn("Tool Mapping (123/123)", summary_text)
        self.assertIn("Behavior Catalog (113/113)", summary_text)
        self.assertIn("Query Responders (10/10)", summary_text)
        self.assertIn("Monitor Integration (5/5)", summary_text)
        self.assertIn("RELEASE GATE STATUS: PASS", summary_text)

    def test_no_claim_of_guardrail_policy_correctness(self) -> None:
        """Gate must only report Agent capability readiness, not claim 109-rule policy correctness."""
        report = validate_agent_coverage()
        summary_text = report.summary()
        self.assertNotIn("109-rule", summary_text)
        self.assertNotIn("policy correctness", summary_text.lower())


if __name__ == "__main__":
    unittest.main()
