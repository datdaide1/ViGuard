"""Comprehensive unit tests for EVT-01 Agent/Vehicle typed event pipeline."""

from __future__ import annotations

import unittest
from typing import Any

from src.vehicle_agent.contracts.agent_ui.v1.contract import (
    AgentUIContractError,
    validate_event_stream,
    validate_public_payload,
)
from src.vehicle_agent.events import (
    OPEN_DOOR_ALLOWED_SLICE,
    OPEN_DOOR_BLOCKED_SLICE,
    AgentEventPipeline,
    AgentEventStore,
    EventPollingAdapter,
    EventReplayConsumer,
    EventStreamAdapter,
    redact_event,
    replay_events,
)


class EventPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = AgentEventStore()
        self.pipeline = AgentEventPipeline(store=self.store)

    def test_sequence_contiguous_ordering_and_correlation(self) -> None:
        session_id = "session-seq-test"
        turn_id = "turn-1"
        request_id = "req-1"

        e1 = self.pipeline.emit_proposal(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            intent="open_door",
            summary="Mở cửa xe",
        )
        self.assertEqual(e1["sequence"], 1)

        e2 = self.pipeline.emit_decision(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=e1["proposal_id"],
            outcome="ALLOW",
        )
        self.assertEqual(e2["sequence"], 2)

        e3 = self.pipeline.emit_execution(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=e1["proposal_id"],
            execution_id="exec-101",
            intent="open_door",
            phase="started",
        )
        self.assertEqual(e3["sequence"], 3)

        e4 = self.pipeline.emit_state_changed(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            state_version=1,
            changes={"door": "open"},
            source_execution_id="exec-101",
        )
        self.assertEqual(e4["sequence"], 4)

        e5 = self.pipeline.emit_execution(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=e1["proposal_id"],
            execution_id="exec-101",
            intent="open_door",
            phase="succeeded",
        )
        self.assertEqual(e5["sequence"], 5)

        events = self.store.get_events(session_id)
        self.assertEqual(len(events), 5)
        # Verify validate_event_stream passes without error
        validate_event_stream(events)

    def test_redaction_strips_private_and_forbidden_fields(self) -> None:
        unredacted_payload = {
            "contract_version": "1.1.0",
            "kind": "event",
            "event_type": "proposal",
            "event_id": "evt-test-redact",
            "sequence": 1,
            "session_id": "session-redact",
            "turn_id": "turn-1",
            "request_id": "req-1",
            "occurred_at": "2026-08-04T12:00:00Z",
            "actor": "AGENT",
            "proposal_id": "prop-redact-1",
            "intent": "open_door",
            "summary": "Sample summary",
            "permit": "SECRET_PERMIT_TOKEN",
            "permit_id": "permit-123",
            "api_key": "sk-secret-key",
            "system_prompt": "Internal system instructions",
            "hidden_reasoning": "Thought process",
            "internal_trace": {"debug": "data"},
        }

        # Passing raw payload to validate_public_payload would fail
        with self.assertRaises(AgentUIContractError):
            validate_public_payload(unredacted_payload)

        # Redact payload
        redacted = redact_event(unredacted_payload)
        self.assertNotIn("permit", redacted)
        self.assertNotIn("permit_id", redacted)
        self.assertNotIn("api_key", redacted)
        self.assertNotIn("system_prompt", redacted)
        self.assertNotIn("hidden_reasoning", redacted)
        self.assertNotIn("internal_trace", redacted)

        # Validated redacted payload passes
        validate_public_payload(redacted)

        # Emitting via pipeline automatically redacts
        stored = self.pipeline.emit_raw(unredacted_payload)
        self.assertNotIn("permit", stored)
        self.assertNotIn("internal_trace", stored)

    def test_store_queries_and_filtering(self) -> None:
        session_id = "session-query"
        self.pipeline.emit_proposal(session_id, "turn-1", "req-1", "intent-a", "Summary A")
        self.pipeline.emit_proposal(session_id, "turn-2", "req-2", "intent-b", "Summary B")

        all_events = self.store.get_events(session_id)
        self.assertEqual(len(all_events), 2)

        since_seq_1 = self.store.get_events(session_id, since_sequence=1)
        self.assertEqual(len(since_seq_1), 1)
        self.assertEqual(since_seq_1[0]["sequence"], 2)

        turn_2_events = self.store.get_turn_events(session_id, "turn-2")
        self.assertEqual(len(turn_2_events), 1)
        self.assertEqual(turn_2_events[0]["intent"], "intent-b")

    def test_polling_and_streaming_adapters(self) -> None:
        session_id = "session-adapter"
        received_stream: list[dict[str, Any]] = []

        self.pipeline.stream_adapter.subscribe_session(session_id, received_stream.append)

        e1 = self.pipeline.emit_proposal(session_id, "turn-1", "req-1", "open_door", "Mở cửa")

        self.assertEqual(len(received_stream), 1)
        self.assertEqual(received_stream[0]["event_id"], e1["event_id"])

        polled = self.pipeline.polling_adapter.poll(session_id, since_sequence=0)
        self.assertEqual(len(polled), 1)
        self.assertEqual(polled[0]["event_id"], e1["event_id"])

    def test_stream_adapter_unsubscribe(self) -> None:
        session_id = "session-unsubscribe"
        received_a: list[dict[str, Any]] = []
        received_b: list[dict[str, Any]] = []

        def callback_a(event: dict[str, Any]) -> None:
            received_a.append(event)

        def callback_b(event: dict[str, Any]) -> None:
            received_b.append(event)

        token_a = self.pipeline.stream_adapter.subscribe_session(session_id, callback_a)
        token_b = self.pipeline.stream_adapter.subscribe_session(session_id, callback_b)

        e1 = self.pipeline.emit_proposal(session_id, "turn-1", "req-1", "open_door", "Mở cửa")

        self.assertEqual(len(received_a), 1)
        self.assertEqual(len(received_b), 1)

        self.pipeline.stream_adapter.unsubscribe_session(token_b)

        e2 = self.pipeline.emit_proposal(session_id, "turn-2", "req-2", "close_door", "Đóng cửa")

        self.assertEqual(len(received_a), 2)
        self.assertEqual(len(received_b), 1)
        self.pipeline.stream_adapter.unsubscribe_session(token_a)

    def test_unsafe_global_subscription_api_is_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            self.pipeline.stream_adapter.subscribe(lambda _: None)

    def test_stream_adapter_stream_session_sequences(self) -> None:
        session_id = "session-stream"

        e1 = self.pipeline.emit_proposal(session_id, "turn-1", "req-1", "open_door", "Mở cửa")
        e2 = self.pipeline.emit_proposal(session_id, "turn-2", "req-2", "close_door", "Đóng cửa")
        e3 = self.pipeline.emit_proposal(session_id, "turn-3", "req-3", "open_door", "Mở cửa lần nữa")

        all_events = list(
            self.pipeline.stream_adapter.stream_session(session_id, since_sequence=0)
        )
        self.assertEqual([e["event_id"] for e in all_events], [e1["event_id"], e2["event_id"], e3["event_id"]])

        mid_sequence = all_events[0]["sequence"]
        later_events = list(
            self.pipeline.stream_adapter.stream_session(session_id, since_sequence=mid_sequence)
        )
        self.assertEqual([e["event_id"] for e in later_events], [e2["event_id"], e3["event_id"]])

    def test_ui_mock_reconstructs_complete_vertical_slice(self) -> None:
        validate_event_stream(OPEN_DOOR_ALLOWED_SLICE)
        consumer = EventReplayConsumer()
        replay_events(OPEN_DOOR_ALLOWED_SLICE, consumer=consumer)

        self.assertEqual(len(consumer.proposals), 1)
        self.assertEqual(len(consumer.decisions), 1)
        self.assertEqual(len(consumer.executions), 2)
        self.assertEqual(consumer.reconstructed_state.get("door_fl_state"), "open")
        self.assertIn("proposal:open_door", consumer.timeline)
        self.assertIn("decision:ALLOW", consumer.timeline)
        self.assertIn("state:AGENT", consumer.timeline)

    def test_blocked_path_has_explicit_no_execution_evidence(self) -> None:
        session_id = "session-blocked-evidence"
        turn_id = "turn-1"
        request_id = "req-1"

        prop = self.pipeline.emit_proposal(session_id, turn_id, request_id, "open_door", "Mở cửa")
        p_id = prop["proposal_id"]

        self.pipeline.emit_decision(
            session_id,
            turn_id,
            request_id,
            proposal_id=p_id,
            outcome="BLOCK_UNSAFE",
            reason_code="SPEED_TOO_HIGH",
            rule_id="RULE_DOOR_SPEED",
        )

        evidence = self.store.get_no_execution_evidence(session_id, p_id)
        self.assertIsNotNone(evidence)
        self.assertTrue(evidence["has_no_execution_evidence"])
        self.assertEqual(evidence["execution_count"], 0)
        self.assertEqual(evidence["outcome"], "BLOCK_UNSAFE")

        # Confirm validate_event_stream passes for blocked slice
        events = self.store.get_events(session_id)
        validate_event_stream(events)

    def test_event_replay_does_not_reexecute_actions(self) -> None:
        consumer = EventReplayConsumer()
        self.assertEqual(consumer.executed_action_calls_count, 0)

        replay_events(OPEN_DOOR_ALLOWED_SLICE, consumer=consumer)
        replay_events(OPEN_DOOR_BLOCKED_SLICE, consumer=consumer)

        # Zero side-effect execution during replay
        self.assertEqual(consumer.executed_action_calls_count, 0)


if __name__ == "__main__":
    unittest.main()
