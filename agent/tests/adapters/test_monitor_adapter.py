"""Unit and integration tests for GuardrailMonitorAdapter (MON-ADP-01)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from vehicle_agent.active_actions.models import ActiveActionRecord
from vehicle_agent.active_actions.registry import ActiveActionRegistry
from vehicle_agent.adapters.guardrail.client import (
    GuardrailAdapterError,
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)
from vehicle_agent.adapters.monitor.adapter import (
    MONITORED_INTENTS,
    GuardrailMonitorAdapter,
)
from vehicle_agent.contracts.guardrail.v1.contract import CONTRACT_VERSION


class TestGuardrailMonitorAdapter(unittest.TestCase):
    """Test suite for MON-ADP-01 Guardrail Monitor Integration Adapter."""

    def setUp(self) -> None:
        self.config = GuardrailClientConfig(
            base_url="http://127.0.0.1:9999",
            provider=GuardrailProvider.MOCK,
        )
        self.mock_client = MagicMock(spec=GuardrailClientAdapter)
        self.mock_client.config = self.config
        self.registry = ActiveActionRegistry()
        self.event_pipeline = MagicMock()
        self.adapter = GuardrailMonitorAdapter(
            guardrail_client=self.mock_client,
            active_action_registry=self.registry,
            event_pipeline=self.event_pipeline,
        )

    def test_monitored_intents_coverage(self) -> None:
        """Verify exact 5 monitored intents have integration paths."""
        expected = {
            "activate_campmode",
            "activate_petmode",
            "activate_autopark",
            "activate_aac",
            "activate_hda",
        }
        self.assertEqual(MONITORED_INTENTS, expected)
        for intent in expected:
            self.assertTrue(self.adapter.is_monitored_intent(intent))

    def test_evaluate_allow_keeps_action_running(self) -> None:
        """Verify ALLOW decision outcome permits active action to continue running."""
        record = self.registry.start_action(
            intent="activate_hda",
            session_id="session-1",
            turn_id="turn-1",
        )
        self.mock_client.evaluate_monitor.return_value = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": "req-mon-1",
            "proposal_id": "prop-1",
            "intent": "activate_hda",
            "outcome": "ALLOW",
            "rule_id": "RULE_ALLOW_MONITOR",
            "state_version": 1,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "MONITOR_ALLOW",
            "relevant_state": {},
        }

        results = self.adapter.tick(session_id="session-1")
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res["action_id"], record.action_id)
        self.assertEqual(res["outcome"], "ALLOW")
        self.assertFalse(res["stopped"])

        # Check action is still running in registry
        active_actions = self.registry.get_active_actions(session_id="session-1")
        self.assertEqual(len(active_actions), 1)
        self.assertEqual(active_actions[0].action_id, record.action_id)

        metrics = self.adapter.get_metrics()
        self.assertEqual(metrics["evaluations_count"], 1)
        self.assertEqual(metrics["allow_count"], 1)
        self.assertEqual(metrics["stop_count"], 0)

    def test_evaluate_block_unsafe_stops_action_via_registry(self) -> None:
        """Verify BLOCK_UNSAFE decision outcome stops action via registered handler."""
        stop_handler_called = []

        def stop_cb(rec: ActiveActionRecord, reason: str) -> None:
            stop_handler_called.append((rec.action_id, reason))

        self.registry.register_stop_handler("activate_autopark", stop_cb)

        record = self.registry.start_action(
            intent="activate_autopark",
            session_id="session-2",
            turn_id="turn-2",
        )
        self.mock_client.evaluate_monitor.return_value = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": "req-mon-2",
            "proposal_id": "prop-2",
            "intent": "activate_autopark",
            "outcome": "BLOCK_UNSAFE",
            "rule_id": "R048",
            "state_version": 2,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "OBSTACLE_DETECTED",
            "relevant_state": {},
        }

        results = self.adapter.tick(session_id="session-2")
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res["action_id"], record.action_id)
        self.assertEqual(res["outcome"], "BLOCK_UNSAFE")
        self.assertTrue(res["stopped"])
        self.assertEqual(res["reason_code"], "OBSTACLE_DETECTED")

        # Check registered stop handler was invoked
        self.assertEqual(len(stop_handler_called), 1)
        self.assertEqual(stop_handler_called[0][0], record.action_id)

        # Check action is no longer running in registry
        active_actions = self.registry.get_active_actions(session_id="session-2")
        self.assertEqual(len(active_actions), 0)

        metrics = self.adapter.get_metrics()
        self.assertEqual(metrics["evaluations_count"], 1)
        self.assertEqual(metrics["stop_count"], 1)

    def test_failsafe_stop_on_monitor_error(self) -> None:
        """Verify monitor error/timeout triggers fail-safe stop without silent continuation."""
        record = self.registry.start_action(
            intent="activate_campmode",
            session_id="session-3",
            turn_id="turn-3",
        )
        self.mock_client.evaluate_monitor.side_effect = GuardrailAdapterError(
            "GUARDRAIL_UNAVAILABLE", "Connection timed out"
        )

        results = self.adapter.on_state_changed(new_state=None, session_id="session-3")
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res["action_id"], record.action_id)
        self.assertEqual(res["outcome"], "ERROR")
        self.assertTrue(res["stopped"])
        self.assertIn("Connection timed out", res["error"])

        # Check action is failed/stopped in registry (no silent continuation)
        active_actions = self.registry.get_active_actions(session_id="session-3")
        self.assertEqual(len(active_actions), 0)

        metrics = self.adapter.get_metrics()
        self.assertEqual(metrics["evaluations_count"], 1)
        self.assertEqual(metrics["error_count"], 1)
        self.assertEqual(metrics["failsafe_stop_count"], 1)
        self.assertEqual(metrics["stop_count"], 1)

    def test_state_changed_and_tick_triggers(self) -> None:
        """Verify state change subscription and manual tick trigger evaluation for all 5 intents."""
        intents = [
            "activate_campmode",
            "activate_petmode",
            "activate_autopark",
            "activate_aac",
            "activate_hda",
        ]
        for intent in intents:
            self.registry.start_action(intent=intent, session_id="session-all")

        self.mock_client.evaluate_monitor.return_value = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": "req-all",
            "proposal_id": "prop-all",
            "intent": "activate_hda",
            "outcome": "ALLOW",
            "rule_id": "RULE_ALLOW",
            "state_version": 1,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "ALLOW",
            "relevant_state": {},
        }

        results = self.adapter.on_state_changed(new_state={"speed": 50}, session_id="session-all")
        self.assertEqual(len(results), 5)
        self.assertEqual(self.mock_client.evaluate_monitor.call_count, 5)

    def test_current_state_included_in_monitor_payload(self) -> None:
        """Verify vehicle state is actually sent to the Guardrail monitor endpoint."""
        self.registry.start_action(intent="activate_hda", session_id="session-state")
        self.mock_client.evaluate_monitor.return_value = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": "req-state",
            "intent": "activate_hda",
            "outcome": "ALLOW",
            "rule_id": "RULE_ALLOW",
            "state_version": 1,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "ALLOW",
            "relevant_state": {},
        }

        self.adapter.on_state_changed(new_state={"speed": 80}, session_id="session-state")

        sent_payload = self.mock_client.evaluate_monitor.call_args[0][0]
        self.assertEqual(sent_payload.get("vehicle_state"), {"speed": 80})

    def test_error_kind_response_treated_as_monitor_error(self) -> None:
        """Verify a typed Guardrail error envelope (returned, not raised) is not misrouted as a stop."""
        record = self.registry.start_action(intent="activate_petmode", session_id="session-err")
        self.mock_client.evaluate_monitor.return_value = {
            "contract_version": CONTRACT_VERSION,
            "kind": "error",
            "request_id": "req-err",
            "error": {"code": "RATE_LIMITED", "message": "Too many requests", "retryable": True},
        }

        results = self.adapter.tick(session_id="session-err")
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res["action_id"], record.action_id)
        self.assertEqual(res["outcome"], "ERROR")
        self.assertIn("Too many requests", res["error"])

        metrics = self.adapter.get_metrics()
        self.assertEqual(metrics["error_count"], 1)
        self.assertEqual(metrics["failsafe_stop_count"], 1)

    def test_state_version_null_does_not_crash(self) -> None:
        """Verify an explicit null state_version from Guardrail doesn't raise TypeError."""
        record = self.registry.start_action(intent="activate_aac", session_id="session-sv")
        self.mock_client.evaluate_monitor.return_value = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": "req-sv",
            "intent": "activate_aac",
            "outcome": "BLOCK_UNSAFE",
            "rule_id": "R070",
            "state_version": None,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "OBSTACLE_DETECTED",
            "relevant_state": {},
        }

        results = self.adapter.tick(session_id="session-sv")
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["stopped"])
        self.assertEqual(results[0]["action_id"], record.action_id)

    def test_already_terminal_action_does_not_abort_batch(self) -> None:
        """Verify a race (action stopped externally before evaluation) doesn't kill the whole tick."""
        rec1 = self.registry.start_action(intent="activate_hda", session_id="session-race")
        rec2 = self.registry.start_action(intent="activate_aac", session_id="session-race")

        # Simulate rec1 being stopped by another caller between the registry
        # snapshot and this evaluation running.
        self.registry.stop_action(rec1.action_id, reason="externally_stopped")

        self.mock_client.evaluate_monitor.return_value = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": "req-race",
            "intent": "activate_aac",
            "outcome": "BLOCK_UNSAFE",
            "rule_id": "R070",
            "state_version": 1,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "OBSTACLE_DETECTED",
            "relevant_state": {},
        }

        # rec1 is no longer "active" (get_active_actions excludes it), so only
        # rec2 is evaluated — but the point of this test is that _execute_stop
        # itself is idempotent against an already-terminal record, exercised
        # directly here to guard against regressions in that idempotency.
        stopped_again = self.adapter._execute_stop(rec1, reason="monitor_stop:TEST")
        self.assertEqual(stopped_again.phase.value, "stopped")

        results = self.adapter.tick(session_id="session-race")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action_id"], rec2.action_id)
        self.assertTrue(results[0]["stopped"])


if __name__ == "__main__":
    unittest.main()
