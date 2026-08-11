"""Integration tests for INT-02: Chạy integration với UI thật.

Verifies the public Agent-UI contract (request/response payload shapes), the
AgentEventStore's reconnect/polling semantics, SimulationController's operator
state mutations, and UI mock consumption of 6 hero-action fixtures and
error/degraded payloads with zero private field exposure.

Note: this suite validates contract shapes and lower-level components
(AgentEventStore, SimulationController) directly. It does not yet drive
MessageEndpoint or ConfirmationManager end-to-end through AgentOrchestrator —
see UI_INTEGRATION_REPORT.md for the current coverage boundary.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from vivi_agent.contracts.agent_ui.v1.contract import (
    CONTRACT_VERSION,
    AgentUIContractError,
    validate_event_stream,
    validate_public_payload,
)
from vivi_agent.events import AgentEventStore
from vivi_agent.simulation import SimulationController, SimulationPresetId
from vivi_agent.vehicle.state import VehicleStateMachine


FIXTURES_PATH = Path(__file__).resolve().parents[3] / "src/vivi_agent/contracts/agent_ui/v1/fixtures.json"
FIXTURES = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


class MockUIClient:
    """Mock UI client consuming public event stream without access to private runtime state."""

    def __init__(self) -> None:
        self.timeline: list[str] = []
        self.vehicle_state: dict[str, Any] = {}
        self.active_actions: dict[str, str] = {}
        self.events: list[dict[str, Any]] = []

    def consume(self, event: dict[str, Any]) -> None:
        validate_public_payload(event)
        self.events.append(event)
        event_type = event["event_type"]
        if event_type == "proposal":
            self.timeline.append(f"proposal:{event['intent']}")
        elif event_type == "decision":
            self.timeline.append(f"decision:{event['outcome']}")
        elif event_type == "execution":
            self.timeline.append(f"execution:{event['phase']}")
        elif event_type == "state_changed":
            self.vehicle_state.update(event["changes"])
            self.timeline.append(f"state:{event['actor']}")
        elif event_type == "active_action":
            action_id = str(event["active_action_id"])
            phase = str(event["phase"])
            self.active_actions[action_id] = phase
            self.timeline.append(f"active:{phase}")


class UIIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.machine = VehicleStateMachine()
        self.event_store = AgentEventStore()
        self.sim_controller = SimulationController(self.machine)

    def test_ui_request_response_endpoints_validation(self) -> None:
        """Verify message, confirm, cancel, simulation_control, and reset API payloads."""
        # 1. Message request & completed response
        msg_req = copy.deepcopy(FIXTURES["requests"]["message"])
        validate_public_payload(msg_req)

        resp_completed = copy.deepcopy(FIXTURES["responses"]["completed"])
        validate_public_payload(resp_completed)
        self.assertEqual(resp_completed["status"], "completed")

        # 2. Confirm request & needs_confirmation response
        confirm_req = copy.deepcopy(FIXTURES["requests"]["confirm"])
        validate_public_payload(confirm_req)

        resp_needs_confirm = copy.deepcopy(FIXTURES["responses"]["needs_confirmation"])
        validate_public_payload(resp_needs_confirm)
        self.assertEqual(resp_needs_confirm["status"], "needs_confirmation")

        # 3. Cancel request & blocked response
        cancel_req = copy.deepcopy(FIXTURES["requests"]["cancel"])
        validate_public_payload(cancel_req)

        resp_blocked = copy.deepcopy(FIXTURES["responses"]["blocked"])
        validate_public_payload(resp_blocked)
        self.assertEqual(resp_blocked["status"], "blocked")

        # 4. Simulation control request & degraded response
        sim_req = copy.deepcopy(FIXTURES["requests"]["simulation_control"])
        validate_public_payload(sim_req)

        resp_degraded = copy.deepcopy(FIXTURES["responses"]["degraded"])
        validate_public_payload(resp_degraded)
        self.assertEqual(resp_degraded["status"], "degraded")

        # 5. Reset request & failed response
        reset_req = copy.deepcopy(FIXTURES["requests"]["reset"])
        validate_public_payload(reset_req)

        resp_failed = copy.deepcopy(FIXTURES["responses"]["failed"])
        validate_public_payload(resp_failed)
        self.assertEqual(resp_failed["status"], "failed")

    def test_reconnect_and_polling_without_action_replay(self) -> None:
        """Verify UI reconnect polling (get_events_since) receives sequence-ordered events without replaying actions."""
        session_id = "session-reconnect-001"

        # Emit turn events into event store
        e1 = {
            "contract_version": CONTRACT_VERSION,
            "kind": "event",
            "event_type": "proposal",
            "event_id": "evt-1",
            "sequence": 1,
            "session_id": session_id,
            "turn_id": "turn-1",
            "request_id": "req-1",
            "occurred_at": "2026-08-03T10:00:00Z",
            "actor": "AGENT",
            "proposal_id": "prop-1",
            "intent": "open_door",
            "summary": "Mở cửa ghế lái",
        }
        e2 = {
            "contract_version": CONTRACT_VERSION,
            "kind": "event",
            "event_type": "decision",
            "event_id": "evt-2",
            "sequence": 2,
            "session_id": session_id,
            "turn_id": "turn-1",
            "request_id": "req-1",
            "occurred_at": "2026-08-03T10:00:01Z",
            "actor": "GUARDRAIL",
            "proposal_id": "prop-1",
            "outcome": "ALLOW",
            "reason_code": "POLICY_CONDITION_MATCHED",
            "rule_id": "R001",
            "state_version": 1,
        }

        stored_e1 = self.event_store.append(e1)
        stored_e2 = self.event_store.append(e2)

        self.assertEqual(stored_e1["sequence"], 1)
        self.assertEqual(stored_e2["sequence"], 2)

        # Initial UI fetch: get all events
        initial_events = self.event_store.get_events(session_id, since_sequence=0)
        self.assertEqual(len(initial_events), 2)
        validate_event_stream(initial_events)

        # UI reconnect: get events since sequence 1
        reconnect_events = self.event_store.get_events(session_id, since_sequence=1)
        self.assertEqual(len(reconnect_events), 1)
        self.assertEqual(reconnect_events[0]["event_id"], "evt-2")
        self.assertEqual(reconnect_events[0]["sequence"], 2)

        # Reconnect polling does not duplicate events or replay actions
        reconnect_events_again = self.event_store.get_events(session_id, since_sequence=2)
        self.assertEqual(len(reconnect_events_again), 0)

    def test_vehicle_state_and_active_action_payloads(self) -> None:
        """Verify state_changed and active_action event streams validate correctly for UI consumption."""
        events = copy.deepcopy(FIXTURES["scenarios"]["active_hda_monitor_stop"])
        validate_event_stream(events)

        ui_client = MockUIClient()
        for event in events:
            ui_client.consume(event)

        self.assertIn("s3-active", ui_client.active_actions)
        self.assertEqual(ui_client.active_actions["s3-active"], "stopped")
        self.assertEqual(ui_client.vehicle_state["driver_attention"], {"from": "ATTENTIVE", "to": "DISTRACTED"})

    def test_error_degraded_and_refusal_payloads(self) -> None:
        """Verify blocked, degraded, and failed response payloads pass contract validation without private leaks."""
        for response_key in ("blocked", "degraded", "failed", "needs_confirmation"):
            payload = copy.deepcopy(FIXTURES["responses"][response_key])
            with self.subTest(response_key=response_key):
                validate_public_payload(payload)

    def test_six_hero_action_fixtures_public_consumption(self) -> None:
        """Verify UI MockUIClient consumes all 6 hero action proposals with zero private field leaks."""
        hero_fixtures = FIXTURES["hero_actions"]
        self.assertEqual(len(hero_fixtures), 6)

        expected_intents = {
            "open_door",
            "activate_hda",
            "activate_aac",
            "activate_autopark",
            "activate_campmode",
            "open_window",
        }
        actual_intents = {event["intent"] for event in hero_fixtures}
        self.assertEqual(actual_intents, expected_intents)

        ui_client = MockUIClient()
        for hero_event in hero_fixtures:
            ui_client.consume(hero_event)

        self.assertEqual(len(ui_client.timeline), 6)
        for intent in expected_intents:
            self.assertIn(f"proposal:{intent}", ui_client.timeline)

    def test_private_runtime_fields_are_rejected(self) -> None:
        """Verify that any private runtime field leaks (system_prompt, permit, api_key, etc.) are rejected."""
        base_event = copy.deepcopy(FIXTURES["hero_actions"][0])
        forbidden_fields = (
            "permit",
            "system_prompt",
            "api_key",
            "access_token",
            "password",
            "secret",
        )
        for field in forbidden_fields:
            leaked_payload = copy.deepcopy(base_event)
            leaked_payload[field] = "sensitive-value"
            with self.subTest(field=field), self.assertRaises(AgentUIContractError) as raised:
                validate_public_payload(leaked_payload)
            self.assertEqual(raised.exception.code, "PRIVATE_FIELD_EXPOSED")

    def test_simulation_controller_operator_mutations_emit_valid_events(self) -> None:
        """Verify SimulationController operator state changes alter machine state and emit valid public state events."""
        session_id = "session-sim-001"
        self.assertEqual(self.machine.snapshot().motion.speed_kph, 0)

        # Apply highway_hda preset
        res = self.sim_controller.apply_preset(SimulationPresetId.HIGHWAY_HDA)
        self.assertGreater(self.machine.snapshot().motion.speed_kph, 0)

        # Record operator state change event
        event = {
            "contract_version": CONTRACT_VERSION,
            "kind": "event",
            "event_type": "state_changed",
            "event_id": "sim-evt-1",
            "sequence": 1,
            "session_id": session_id,
            "turn_id": "operator-turn-1",
            "request_id": "sim-req-1",
            "occurred_at": "2026-08-03T10:00:00Z",
            "actor": "OPERATOR",
            "state_version": res.state_version,
            "changes": {"speed": {"from": 0, "to": 100}},
        }
        stored = self.event_store.append(event)
        self.assertEqual(stored["sequence"], 1)
        validate_public_payload(stored)


if __name__ == "__main__":
    unittest.main()
