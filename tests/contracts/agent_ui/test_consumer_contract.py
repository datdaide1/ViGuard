from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

try:
    import jsonschema
except ImportError:  # The runtime validator remains dependency-free.
    jsonschema = None

from src.vivi_agent.contracts.agent_ui.v1.contract import (
    AgentUIContractError,
    validate_event_stream,
    validate_public_payload,
)

CONTRACT_DIR = Path("src/vivi_agent/contracts/agent_ui/v1")


class MockUIClient:
    """Minimal consumer proving that no private runtime state is required."""

    def __init__(self) -> None:
        self.timeline: list[str] = []
        self.vehicle_state: dict[str, object] = {}
        self.active_actions: dict[str, str] = {}

    def consume(self, event: dict[str, object]) -> None:
        validate_public_payload(event)
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


class AgentUIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = json.loads((CONTRACT_DIR / "fixtures.json").read_text(encoding="utf-8"))
        cls.schema = json.loads((CONTRACT_DIR / "agent-ui.schema.json").read_text(encoding="utf-8"))

    def test_schema_exposes_all_public_variants(self) -> None:
        self.assertEqual(len(self.schema["oneOf"]), 15)
        self.assertEqual(
            set(self.fixtures["requests"]),
            {"message", "confirm", "cancel", "simulation_control", "reset"},
        )

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_schema_and_semantic_validator_accept_the_same_fixtures(self) -> None:
        validator = jsonschema.Draft202012Validator(
            self.schema,
            format_checker=jsonschema.FormatChecker(),
        )
        payloads = [
            *self.fixtures["requests"].values(),
            *self.fixtures["responses"].values(),
            *self.fixtures["hero_actions"],
            *(event for events in self.fixtures["scenarios"].values() for event in events),
        ]
        for payload in payloads:
            with self.subTest(kind=payload.get("request_type", payload.get("status", payload.get("event_type")))):
                validator.validate(payload)
                validate_public_payload(payload)

        invalid = copy.deepcopy(self.fixtures["responses"]["completed"])
        invalid["reason"] = "completed does not expose a policy reason"
        self.assertFalse(validator.is_valid(invalid))
        with self.assertRaises(AgentUIContractError):
            validate_public_payload(invalid)
        self.assertEqual(
            set(self.fixtures["responses"]),
            {"completed", "blocked", "needs_confirmation", "failed", "degraded"},
        )

    def test_all_request_response_and_hero_fixtures_are_public(self) -> None:
        payloads = [
            *self.fixtures["requests"].values(),
            *self.fixtures["responses"].values(),
            *self.fixtures["hero_actions"],
        ]
        for payload in payloads:
            with self.subTest(kind=payload.get("request_type", payload.get("status", payload.get("intent")))):
                validate_public_payload(payload)
        self.assertEqual(
            {event["intent"] for event in self.fixtures["hero_actions"]},
            {"open_door", "activate_hda", "activate_aac", "activate_autopark", "activate_campmode", "open_window"},
        )

    def test_ui_renders_all_three_scenarios_from_public_events(self) -> None:
        self.assertEqual(len(self.fixtures["scenarios"]), 3)
        for name, events in self.fixtures["scenarios"].items():
            with self.subTest(name=name):
                validate_event_stream(events)
                client = MockUIClient()
                for event in events:
                    client.consume(event)
                self.assertTrue(client.timeline)
        monitor_client = MockUIClient()
        for event in self.fixtures["scenarios"]["active_hda_monitor_stop"]:
            monitor_client.consume(event)
        self.assertEqual(monitor_client.active_actions["s3-active"], "stopped")
        self.assertEqual(monitor_client.timeline[-1], "execution:stopped")

    def test_private_fields_are_rejected_recursively(self) -> None:
        base = self.fixtures["requests"]["message"]
        for private_field in (
            "system_prompt",
            "systemPrompt",
            "hidden-reasoning",
            "providerThought",
            "permit",
            "api_key",
            "apiKey",
            "x-api-key",
            "access-token",
            "clientSecret",
        ):
            payload = copy.deepcopy(base)
            payload["debug"] = {private_field: "must-not-leak"}
            with self.subTest(field=private_field), self.assertRaises(AgentUIContractError) as raised:
                validate_public_payload(payload)
            self.assertEqual(raised.exception.code, "PRIVATE_FIELD_EXPOSED")

    def test_unknown_public_fields_are_rejected(self) -> None:
        payload = copy.deepcopy(self.fixtures["responses"]["completed"])
        payload["internal_trace"] = "opaque"
        with self.assertRaises(AgentUIContractError) as raised:
            validate_public_payload(payload)
        self.assertEqual(raised.exception.code, "UNEXPECTED_FIELD")

    def test_sequence_gaps_and_mixed_sessions_are_rejected(self) -> None:
        source = self.fixtures["scenarios"]["fake_state_attack_blocked"]
        gap = copy.deepcopy(source)
        gap[1]["sequence"] = 3
        mixed = copy.deepcopy(source)
        mixed[1]["session_id"] = "different-session"
        for events, code in ((gap, "EVENT_ORDER_GAP"), (mixed, "SESSION_MISMATCH")):
            with self.subTest(code=code), self.assertRaises(AgentUIContractError) as raised:
                validate_event_stream(events)
            self.assertEqual(raised.exception.code, code)

    def test_decision_and_execution_require_full_request_correlation(self) -> None:
        decision_mismatch = copy.deepcopy(
            self.fixtures["scenarios"]["fake_state_attack_blocked"]
        )
        decision_mismatch[1]["request_id"] = "different-request"
        with self.assertRaises(AgentUIContractError) as raised:
            validate_event_stream(decision_mismatch)
        self.assertEqual(raised.exception.code, "DECISION_BEFORE_PROPOSAL")

        execution_mismatch = copy.deepcopy(
            self.fixtures["scenarios"]["active_hda_monitor_stop"][:3]
        )
        execution_mismatch[2]["request_id"] = "different-request"
        with self.assertRaises(AgentUIContractError) as raised:
            validate_event_stream(execution_mismatch)
        self.assertEqual(raised.exception.code, "EXECUTION_CORRELATION_MISMATCH")

    def test_execution_has_exactly_one_terminal_transition(self) -> None:
        events = copy.deepcopy(
            self.fixtures["scenarios"]["active_hda_monitor_stop"][:3]
        )
        terminal = copy.deepcopy(events[-1])
        terminal.update({"event_id": "terminal-1", "sequence": 4, "phase": "succeeded"})
        repeated = copy.deepcopy(terminal)
        repeated.update({"event_id": "terminal-2", "sequence": 5})
        events.extend((terminal, repeated))
        with self.assertRaises(AgentUIContractError) as raised:
            validate_event_stream(events)
        self.assertEqual(raised.exception.code, "EXECUTION_ALREADY_TERMINAL")

    def test_effect_after_execution_terminal_is_rejected(self) -> None:
        events = copy.deepcopy(
            self.fixtures["scenarios"]["active_hda_monitor_stop"][:3]
        )
        terminal = copy.deepcopy(events[-1])
        terminal.update({"event_id": "terminal", "sequence": 4, "phase": "stopped"})
        active = copy.deepcopy(self.fixtures["scenarios"]["active_hda_monitor_stop"][3])
        active.update({"event_id": "late-active", "sequence": 5})
        events.extend((terminal, active))
        with self.assertRaises(AgentUIContractError) as raised:
            validate_event_stream(events)
        self.assertEqual(raised.exception.code, "ACTIVE_ACTION_BEFORE_EXECUTION")

    def test_block_and_confirmation_cannot_progress_to_execution(self) -> None:
        for outcome in ("BLOCK_UNSAFE", "CONFIRM"):
            events = copy.deepcopy(self.fixtures["scenarios"]["fake_state_attack_blocked"])
            events[1]["outcome"] = outcome
            events.append(
                {
                    "contract_version": "1.0.0", "kind": "event", "event_type": "execution",
                    "event_id": "illegal-execution", "sequence": 3, "session_id": "scenario-1",
                    "turn_id": "turn-1", "request_id": "req-1", "occurred_at": "2026-08-03T11:00:02Z",
                    "actor": "AGENT", "proposal_id": "s1-prop", "execution_id": "exec-illegal",
                    "intent": "open_door", "phase": "started"
                }
            )
            with self.subTest(outcome=outcome), self.assertRaises(AgentUIContractError) as raised:
                validate_event_stream(events)
            self.assertEqual(raised.exception.code, "EXECUTION_WITHOUT_ALLOW")

    def test_agent_effect_requires_correlated_execution(self) -> None:
        events = copy.deepcopy(self.fixtures["scenarios"]["active_hda_monitor_stop"][:3])
        events.append(
            {
                "contract_version": "1.0.0", "kind": "event", "event_type": "state_changed",
                "event_id": "bad-state", "sequence": 4, "session_id": "scenario-3", "turn_id": "turn-1",
                "request_id": "req-1", "occurred_at": "2026-08-03T11:20:03Z", "actor": "AGENT",
                "state_version": 21, "changes": {"hda": {"from": False, "to": True}},
                "source_execution_id": "another-execution"
            }
        )
        with self.assertRaises(AgentUIContractError) as raised:
            validate_event_stream(events)
        self.assertEqual(raised.exception.code, "STATE_CHANGE_WITHOUT_EXECUTION")


if __name__ == "__main__":
    unittest.main()
