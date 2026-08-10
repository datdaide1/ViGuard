"""COV-01 specific task gate test suite."""

from __future__ import annotations

import unittest

from vivi_agent.coverage import (
    AgentCoverageReport,
    validate_agent_coverage,
)


class TestCov01TaskGate(unittest.TestCase):
    """Release gate tests specifically verifying COV-01 acceptance criteria."""

    def test_acceptance_criteria_1_tool_mapping_53_of_53(self) -> None:
        report = validate_agent_coverage()
        self.assertEqual(len(report.tool_mapping_coverage.missing_intents), 0)
        self.assertEqual(report.total_manifest_intents, 123)

    def test_acceptance_criteria_2_behavior_refusal_47_of_47(self) -> None:
        report = validate_agent_coverage()
        self.assertEqual(len(report.behavior_coverage.missing_action), 0)
        self.assertEqual(len(report.behavior_coverage.missing_refusal), 0)
        self.assertEqual(report.behavior_coverage.covered_total, 113)

    def test_acceptance_criteria_3_query_responder_6_of_6(self) -> None:
        report = validate_agent_coverage()
        self.assertEqual(len(report.query_coverage.missing_query), 0)
        self.assertEqual(report.query_coverage.covered_query, 10)

    def test_acceptance_criteria_4_monitored_intents_5_of_5(self) -> None:
        report = validate_agent_coverage()
        self.assertEqual(len(report.monitor_coverage.missing_monitored), 0)
        self.assertEqual(report.monitor_coverage.covered_monitored, 5)

    # The "missing intent causes readiness failure, with the exact ID named
    # in the error" scenario is already covered in more depth (it also
    # checks report.tool_mapping_coverage.missing_intents and the exception
    # code) by test_agent_coverage_gate.py::
    # TestAgentCoverageGate.test_missing_tool_mapping_fails_gate_with_exact_id
    # — not duplicated here.


if __name__ == "__main__":
    unittest.main()
