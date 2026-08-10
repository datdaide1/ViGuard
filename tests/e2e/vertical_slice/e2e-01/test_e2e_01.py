"""End-to-End Vertical Slice Test Suite for open_door (E2E-01).

Validates complete vertical slice: User Message -> Model Proposal -> ToolMapper ->
Guardrail Authorization -> Vehicle Execution Gateway -> State Machine Mutation ->
Agent Event Pipeline -> UI Consumer Verification.
"""

from __future__ import annotations

import unittest
from typing import Any

from vivi_agent.contracts.agent_ui.v1.contract import (
    validate_event_stream,
    validate_public_payload,
)
from vivi_agent.contracts.guardrail.v1.contract import CONTRACT_VERSION, proposal_digest
from vivi_agent.contracts.agent_ui.v1.contract import CONTRACT_VERSION as AGENT_UI_CONTRACT_VERSION
from vivi_agent.orchestrator import (
    AgentOrchestrator,
    MessageEndpoint,
    TurnRequest,
    TurnStatus,
    TurnState,
)
from vivi_agent.catalog import load_manifest
from vivi_agent.tools.registry import load_registry
from vivi_agent.tools.mapping import load_default_mapper
from vivi_agent.vehicle.execution import (
    VehicleToolGateway,
    PermitVerificationError,
    make_open_door_handler,
)
from vivi_agent.vehicle.state import (
    DoorPosition,
    Gear,
    LockState,
    VehicleStateMachine,
)
from vivi_agent.events import AgentEventPipeline, AgentEventStore

from .fixtures import (
    ActuatorSpy,
    E2EMockGuardrailClient,
    E2EMockModelRouter,
    SpyExecutor,
    create_e2e_environment,
)


class MockUIConsumer:
    """Mock UI client consuming public event stream without access to private runtime state."""

    def __init__(self) -> None:
        self.timeline: list[str] = []
        self.vehicle_state: dict[str, Any] = {}
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


class E2EOpenDoorVerticalSliceTests(unittest.TestCase):

    def setUp(self) -> None:
        self.mapper = load_default_mapper(load_registry(), load_manifest())

    def test_allow_path_executes_and_mutates_state_exactly_once(self) -> None:
        """Allow path must execute open_door, mutate vehicle state exactly once, and emit event stream."""
        env = create_e2e_environment(speed=0.0, gear=Gear.PARK, guardrail_outcome="ALLOW")
        orchestrator = AgentOrchestrator(
            model_router=env.model_router,
            mapper=self.mapper,
            guardrail=env.guardrail,
            executor=env.spy_executor,
        )
        endpoint = MessageEndpoint(orchestrator)

        # 1. Verify initial vehicle state (driver_door is CLOSED & LOCKED)
        init_snapshot = env.state_machine.snapshot()
        driver_door = next(d for d in init_snapshot.access.doors if d.door_id == "driver_door")
        self.assertEqual(driver_door.position, DoorPosition.CLOSED)
        self.assertEqual(driver_door.lock, LockState.LOCKED)
        self.assertEqual(init_snapshot.state_version, 0)

        # 2. Execute user message turn through public endpoint
        request_payload = {
            "contract_version": AGENT_UI_CONTRACT_VERSION,
            "kind": "request",
            "request_type": "message",
            "session_id": "sess-e2e-01",
            "turn_id": "turn-allow-1",
            "request_id": "req-allow-1",
            "occurred_at": "2026-08-04T00:00:00Z",
            "message": "Mở cửa ghế lái",
        }
        response = endpoint.post_message(request_payload)

        # 3. Assert Turn Result via endpoint
        self.assertEqual(response["status"], "completed")
        self.assertIn("execution_id", response)
        self.assertEqual(response["state_version"], 1)

        # 4. Actuator-spy assertion: Actuator called EXACTLY ONCE
        self.assertEqual(env.spy_actuator.call_count, 1)
        self.assertEqual(env.spy_executor.call_count, 1)

        # 5. Verify vehicle state mutation
        new_snapshot = env.state_machine.snapshot()
        self.assertEqual(new_snapshot.state_version, 1)
        driver_door_after = next(d for d in new_snapshot.access.doors if d.door_id == "driver_door")
        self.assertEqual(driver_door_after.position, DoorPosition.OPEN)
        self.assertEqual(driver_door_after.lock, LockState.UNLOCKED)

    def test_moving_state_block_fixture_calls_actuator_zero_times(self) -> None:
        """Moving vehicle state fixture must result in BLOCK decision and 0 actuator calls."""
        # Speed = 30 km/h, Gear = D
        env = create_e2e_environment(
            speed=30.0,
            gear=Gear.DRIVE,
            guardrail_outcome="BLOCK_UNSAFE",
            guardrail_rule_id="R_SAFETY_DOOR_MOVING",
            guardrail_reason_code="VEHICLE_IN_MOTION",
        )
        orchestrator = AgentOrchestrator(
            model_router=env.model_router,
            mapper=self.mapper,
            guardrail=env.guardrail,
            executor=env.spy_executor,
        )
        endpoint = MessageEndpoint(orchestrator)

        request_payload = {
            "contract_version": AGENT_UI_CONTRACT_VERSION,
            "kind": "request",
            "request_type": "message",
            "session_id": "sess-e2e-block",
            "turn_id": "turn-block-1",
            "request_id": "req-block-1",
            "occurred_at": "2026-08-04T00:00:00Z",
            "message": "Mở cửa xe khi đang chạy",
        }
        response = endpoint.post_message(request_payload)

        # Turn should be blocked
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["rule_id"], "R_SAFETY_DOOR_MOVING")
        self.assertEqual(response["reason"], "VEHICLE_IN_MOTION")

        # Actuator spy assertion: Actuator called ZERO times
        self.assertEqual(env.spy_actuator.call_count, 0)
        self.assertEqual(env.spy_executor.call_count, 0)

        # Vehicle door position must remain CLOSED
        snapshot = env.state_machine.snapshot()
        driver_door = next(d for d in snapshot.access.doors if d.door_id == "driver_door")
        self.assertEqual(driver_door.position, DoorPosition.CLOSED)

    def test_malformed_guardrail_response_fails_closed_with_zero_actuator_calls(self) -> None:
        """Malformed Guardrail responses must cause turn failure without invoking actuator."""
        malformed_response = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": "req-malformed",
            "proposal_id": "wrong-proposal-id",  # Proposal mismatch
            "intent": "open_door",
            "outcome": "ALLOW",
            "rule_id": "R_OPEN_DOOR",
            "state_version": 1,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "SAFE_OPERATION",
            "relevant_state": {},
        }
        env = create_e2e_environment(guardrail_custom_response=malformed_response)
        orchestrator = AgentOrchestrator(
            model_router=env.model_router,
            mapper=self.mapper,
            guardrail=env.guardrail,
            executor=env.spy_executor,
        )
        endpoint = MessageEndpoint(orchestrator)

        request_payload = {
            "contract_version": AGENT_UI_CONTRACT_VERSION,
            "kind": "request",
            "request_type": "message",
            "session_id": "sess-malformed",
            "turn_id": "turn-malformed-1",
            "request_id": "req-malformed-1",
            "occurred_at": "2026-08-04T00:00:00Z",
            "message": "Mở cửa ghế lái",
        }
        response = endpoint.post_message(request_payload)

        self.assertEqual(response["status"], "failed")
        self.assertEqual(env.spy_actuator.call_count, 0)
        self.assertEqual(env.spy_executor.call_count, 0)

    def test_invalid_expired_replayed_permit_fixtures(self) -> None:
        """Permit fixtures: Invalid digest, expired permit, or replayed permit must be rejected."""
        env = create_e2e_environment(speed=0.0, gear=Gear.PARK)

        proposal = {
            "contract_version": CONTRACT_VERSION,
            "proposal_id": "prop-permit-test",
            "session_id": "sess-permit",
            "source_turn_id": "turn-permit",
            "tool": "open_door",
            "arguments": {"door": "driver_door"},
            "model_provider": "openai",
            "model_id": "gpt-4o",
        }
        digest = proposal_digest(proposal)

        # 1. Invalid permit (digest mismatch)
        invalid_decision = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": "req-inv",
            "proposal_id": "prop-permit-test",
            "intent": "open_door",
            "outcome": "ALLOW",
            "rule_id": "R_OPEN_DOOR",
            "state_version": 0,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "SAFE_OPERATION",
            "relevant_state": {},
            "permit": {
                "permit_id": "permit-invalid-digest",
                "proposal_digest": "sha256:" + "f" * 64,  # Invalid digest
                "intent": "open_door",
                "rule_id": "R_OPEN_DOOR",
                "state_version": 0,
                "policy_checksum": "sha256:" + "0" * 64,
                "issued_at": "2020-01-01T00:00:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
                "single_use": True,
            },
        }
        res_inv = env.gateway.execute(proposal, invalid_decision)
        self.assertFalse(res_inv.success)
        self.assertEqual(res_inv.error.code, "PROPOSAL_MISMATCH")
        self.assertEqual(env.spy_actuator.call_count, 0)

        # 2. Expired permit
        expired_decision = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": "req-exp",
            "proposal_id": "prop-permit-test",
            "intent": "open_door",
            "outcome": "ALLOW",
            "rule_id": "R_OPEN_DOOR",
            "state_version": 0,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "SAFE_OPERATION",
            "relevant_state": {},
            "permit": {
                "permit_id": "permit-expired",
                "proposal_digest": digest,
                "intent": "open_door",
                "rule_id": "R_OPEN_DOOR",
                "state_version": 0,
                "policy_checksum": "sha256:" + "0" * 64,
                "issued_at": "2020-01-01T00:00:00Z",
                "expires_at": "2020-01-01T00:00:01Z",  # Expired
                "single_use": True,
            },
        }
        res_exp = env.gateway.execute(proposal, expired_decision)
        self.assertFalse(res_exp.success)
        self.assertEqual(res_exp.error.code, "PERMIT_EXPIRED")
        self.assertEqual(env.spy_actuator.call_count, 0)

        # 3. Replayed permit
        valid_decision = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": "req-valid",
            "proposal_id": "prop-permit-test",
            "intent": "open_door",
            "outcome": "ALLOW",
            "rule_id": "R_OPEN_DOOR",
            "state_version": 0,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "SAFE_OPERATION",
            "relevant_state": {},
            "permit": {
                "permit_id": "permit-single-use-replay",
                "proposal_digest": digest,
                "intent": "open_door",
                "rule_id": "R_OPEN_DOOR",
                "state_version": 0,
                "policy_checksum": "sha256:" + "0" * 64,
                "issued_at": "2020-01-01T00:00:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
                "single_use": True,
            },
        }

        # First execution succeeds
        result1 = env.gateway.execute(proposal, valid_decision)
        self.assertTrue(result1.success)
        self.assertEqual(env.spy_actuator.call_count, 1)

        # Second execution with exact same permit fails with PERMIT_REPLAYED
        result2 = env.gateway.execute(proposal, valid_decision)
        self.assertFalse(result2.success)
        self.assertEqual(result2.error.code, "PERMIT_REPLAYED")
        # Actuator remains called ONCE, not twice
        self.assertEqual(env.spy_actuator.call_count, 1)

    def test_ui_mock_consumer_verification_and_event_sequence(self) -> None:
        """UI mock consumer must receive valid event sequence matching Agent-UI contract."""
        env = create_e2e_environment(speed=0.0, gear=Gear.PARK, guardrail_outcome="ALLOW")
        pipeline = env.event_pipeline
        ui_consumer = MockUIConsumer()

        session_id = "sess-ui-contract"
        turn_id = "turn-ui-1"
        request_id = "req-ui-1"

        # Emit standard open_door vertical slice event sequence
        e1 = pipeline.emit_proposal(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            intent="open_door",
            summary="Mở cửa ghế lái",
        )

        e2 = pipeline.emit_decision(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=e1["proposal_id"],
            outcome="ALLOW",
        )

        e3 = pipeline.emit_execution(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=e1["proposal_id"],
            execution_id="exec-ui-101",
            intent="open_door",
            phase="started",
        )

        e4 = pipeline.emit_state_changed(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            state_version=1,
            changes={"driver_door": "open"},
            source_execution_id="exec-ui-101",
        )

        e5 = pipeline.emit_execution(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=e1["proposal_id"],
            execution_id="exec-ui-101",
            intent="open_door",
            phase="succeeded",
        )

        events = env.event_store.get_events(session_id)
        self.assertEqual(len(events), 5)

        # Validate event stream schema
        validate_event_stream(events)

        # Feed to Mock UI Consumer
        for ev in events:
            ui_consumer.consume(ev)

        self.assertEqual(
            ui_consumer.timeline,
            ["proposal:open_door", "decision:ALLOW", "execution:started", "state:AGENT", "execution:succeeded"],
        )
        self.assertEqual(ui_consumer.vehicle_state, {"driver_door": "open"})

    def test_deterministic_state_reset(self) -> None:
        """Resetting state machine and event store restores baseline state deterministically."""
        env = create_e2e_environment(speed=0.0, gear=Gear.PARK, guardrail_outcome="ALLOW")
        orchestrator = AgentOrchestrator(
            model_router=env.model_router,
            mapper=self.mapper,
            guardrail=env.guardrail,
            executor=env.spy_executor,
        )
        endpoint = MessageEndpoint(orchestrator)

        # Perform turn
        endpoint.post_message({
            "contract_version": AGENT_UI_CONTRACT_VERSION,
            "kind": "request",
            "request_type": "message",
            "session_id": "sess-reset",
            "turn_id": "turn-reset-1",
            "request_id": "req-reset-1",
            "occurred_at": "2026-08-04T00:00:00Z",
            "message": "Mở cửa ghế lái",
        })

        self.assertEqual(env.spy_actuator.call_count, 1)
        self.assertEqual(env.state_machine.snapshot().state_version, 1)

        # Reset environment
        env.reset()

        # Assert baseline restoration
        self.assertEqual(env.spy_actuator.call_count, 0)
        self.assertEqual(env.spy_executor.call_count, 0)
        self.assertEqual(env.state_machine.snapshot().state_version, 2)
        driver_door = next(d for d in env.state_machine.snapshot().access.doors if d.door_id == "driver_door")
        self.assertEqual(driver_door.position, DoorPosition.CLOSED)
        self.assertEqual(driver_door.lock, LockState.LOCKED)
        self.assertEqual(len(env.event_store.get_events("sess-reset")), 0)


if __name__ == "__main__":
    unittest.main()
