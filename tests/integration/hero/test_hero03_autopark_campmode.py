"""E2E/integration tests for HERO-03 — Autopark/Camp mode hero behaviors."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping
from unittest.mock import MagicMock

import pytest

from vivi_agent.active_actions.registry import ActiveActionRegistry
from vivi_agent.adapters.monitor.adapter import GuardrailMonitorAdapter
from vivi_agent.behaviors.catalog import get_behavior_config
from vivi_agent.behaviors.hero import (
    AutoparkCampmodeMonitorHeroBehavior,
    make_monitored_autopark_campmode_handler,
    register_autopark_campmode_stop_handlers,
)
from vivi_agent.catalog import load_manifest
from vivi_agent.model_providers import ModelActionProposal, ProviderMetadata, TurnBinding
from vivi_agent.orchestrator import (
    AgentOrchestrator,
    CancellationToken,
    ExecutionResult,
    TurnRequest,
    TurnState,
    TurnStatus,
)
from vivi_agent.tools.mapping import load_default_mapper
from vivi_agent.tools.registry import load_registry
from vivi_agent.vehicle.execution import VehicleToolGateway
from vivi_agent.vehicle.state.events import ActorKind
from vivi_agent.vehicle.state.machine import VehicleStateMachine
from vivi_agent.vehicle.state.model import (
    AutoparkState,
    Gear,
    MotionPhase,
    MotionState,
    TransmissionState,
    VehicleState,
)
from vivi_agent.vehicle.state.presets import get_preset

_NOW = datetime(2026, 8, 6, 10, 0, 0, tzinfo=timezone.utc)
META = ProviderMetadata("openai", "test-model-v1", "sha256:test", 5)


class DummyModelRouter:
    """Deterministic model router proposing a single fixed tool call."""

    def __init__(self, tool_name: str, arguments: dict):
        self.mock_proposal = ModelActionProposal.action(tool_name, arguments, META)

    def propose_tool(self, messages: list[dict[str, str]], binding: TurnBinding) -> ModelActionProposal:
        binding.record_proposal(self.mock_proposal)
        return self.mock_proposal

    def compose_response(self, facts: Mapping[str, Any], turn: TurnBinding) -> ModelActionProposal:
        return ModelActionProposal.response("Phản hồi.", META)


class SpyExecutor:
    """Executor proxy passing parameters through to the gateway."""

    def __init__(self, gateway: VehicleToolGateway) -> None:
        self.gateway = gateway
        self.execution_count = 0

    def execute(
        self,
        proposal: Mapping[str, Any],
        decision: Mapping[str, Any],
        cancellation: CancellationToken,
    ) -> ExecutionResult:
        self.execution_count += 1
        return self.gateway.execute(proposal, decision, cancellation, current_time=_NOW)


def _allow_decision(mapper, proposal: Mapping[str, Any], *, rule_id: str, relevant_state: dict) -> dict[str, Any]:
    mapped = mapper.map_proposal(proposal)
    return {
        "contract_version": "1.0.0",
        "kind": "decision",
        "request_id": f"req-{proposal['proposal_id']}",
        "proposal_id": proposal["proposal_id"],
        "intent": mapped.canonical_action.intent,
        "outcome": "ALLOW",
        "rule_id": rule_id,
        "state_version": 1,
        "policy_checksum": "sha256:" + "0" * 64,
        "reason_code": "PERMITTED",
        "relevant_state": relevant_state,
        "permit": {
            "permit_id": f"permit-{proposal['proposal_id']}",
            "proposal_digest": mapped.proposal_digest,
            "intent": mapped.canonical_action.intent,
            "rule_id": rule_id,
            "state_version": 1,
            "policy_checksum": "sha256:" + "0" * 64,
            "issued_at": "2026-08-06T10:00:00Z",
            "expires_at": "2030-01-01T00:00:00Z",
            "single_use": True,
        },
    }


def _block_decision(mapper, proposal: Mapping[str, Any], *, rule_id: str, reason_code: str, relevant_state: dict) -> dict[str, Any]:
    mapped = mapper.map_proposal(proposal)
    return {
        "contract_version": "1.0.0",
        "kind": "decision",
        "request_id": f"req-{proposal['proposal_id']}",
        "proposal_id": proposal["proposal_id"],
        "intent": mapped.canonical_action.intent,
        "outcome": "BLOCK_UNSAFE",
        "rule_id": rule_id,
        "state_version": 1,
        "policy_checksum": "sha256:" + "0" * 64,
        "reason_code": reason_code,
        "relevant_state": relevant_state,
    }


class TestHero03AutoparkCampmodeE2E:
    @pytest.fixture
    def state_machine(self) -> VehicleStateMachine:
        base = get_preset("parked_ready", state_version=1, timestamp=_NOW)
        return VehicleStateMachine(base)

    @pytest.fixture
    def event_pipeline(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def registry(self, state_machine: VehicleStateMachine, event_pipeline: MagicMock) -> ActiveActionRegistry:
        reg = ActiveActionRegistry(event_pipeline=event_pipeline)
        register_autopark_campmode_stop_handlers(reg, state_machine)
        return reg

    @pytest.fixture
    def gateway(self, state_machine: VehicleStateMachine, registry: ActiveActionRegistry) -> VehicleToolGateway:
        gw = VehicleToolGateway()
        gw.registry.register(
            "activate_autopark",
            make_monitored_autopark_campmode_handler(
                get_behavior_config("activate_autopark"), state_machine, registry
            ),
        )
        gw.registry.register(
            "activate_campmode",
            make_monitored_autopark_campmode_handler(
                get_behavior_config("activate_campmode"), state_machine, registry
            ),
        )
        return gw

    @pytest.fixture
    def mapper(self):
        return load_default_mapper(load_registry(), load_manifest())

    def _start_via_turn(
        self,
        gateway,
        mapper,
        *,
        tool_name: str,
        arguments: dict,
        rule_id: str,
        relevant_state: dict,
        session_id: str,
        message: str,
    ):
        guardrail_mock = MagicMock()
        guardrail_mock.evaluate.side_effect = lambda proposal: _allow_decision(
            mapper, proposal, rule_id=rule_id, relevant_state=relevant_state
        )
        router = DummyModelRouter(tool_name, arguments)
        executor = SpyExecutor(gateway)
        orchestrator = AgentOrchestrator(
            model_router=router, mapper=mapper, guardrail=guardrail_mock, executor=executor
        )
        request = TurnRequest(
            session_id=session_id,
            turn_id="turn-01",
            request_id="req-01",
            message=message,
        )
        turn_result = orchestrator.handle_message(request)
        assert turn_result.error is None, f"Turn failed: {turn_result.error}"
        assert turn_result.status == TurnStatus.COMPLETED
        assert turn_result.state == TurnState.COMPLETED
        return turn_result

    def test_e2e_activate_campmode_creates_active_action_record_and_sets_state(
        self, state_machine, gateway, mapper, registry, event_pipeline
    ):
        """Sufficient-condition preset (parked, powered on) — start must register
        a real ActiveActionRecord and flip camp_mode_active, closing the gap
        where nothing ever called registry.start_action()."""
        self._start_via_turn(
            gateway,
            mapper,
            tool_name="control_special_mode",
            arguments={"action": "activate", "target": "camp_mode"},
            rule_id="R_CAMP_SAFE",
            relevant_state={"gear": "P", "battery_pct": 90.0},
            session_id="hero-camp-01",
            message="Bật chế độ cắm trại giúp tôi",
        )

        running = registry.get_active_actions(session_id="hero-camp-01")
        assert len(running) == 1
        assert running[0].intent == "activate_campmode"
        assert state_machine.snapshot().modes.camp_mode_active is True

        event_pipeline.emit_active_action.assert_called_once()
        assert event_pipeline.emit_active_action.call_args.kwargs["phase"] == "started"

    def test_e2e_activate_autopark_creates_active_action_record(
        self, state_machine, gateway, mapper, registry
    ):
        """Sufficient-condition preset (parked, powered on) — start must register
        a real ActiveActionRecord. autopark_state stays OFF until vehicle/monitor
        telemetry confirms engagement (same pattern as HDA/AAC's enum fields)."""
        self._start_via_turn(
            gateway,
            mapper,
            tool_name="control_driver_assistance",
            arguments={"action": "activate", "target": "auto_park"},
            rule_id="R048_AUTOPARK_SAFE",
            relevant_state={"gear": "P", "speed": 0.0},
            session_id="hero-autopark-01",
            message="Tự động đỗ xe giúp tôi",
        )

        running = registry.get_active_actions(session_id="hero-autopark-01")
        assert len(running) == 1
        assert running[0].intent == "activate_autopark"
        assert state_machine.snapshot().adas.autopark_state == AutoparkState.OFF

    def test_e2e_block_decision_does_not_create_active_action_record(self, state_machine, gateway, mapper, registry):
        """Insufficient-condition preset (moving) — Guardrail BLOCKs the proposal
        itself, so the handler must never run: no ActiveActionRecord, no
        fabricated progress, real state untouched."""

        def set_moving(s: VehicleState) -> VehicleState:
            return replace(
                s,
                motion=MotionState(speed_kph=40.0, phase=MotionPhase.MOVING),
                transmission=TransmissionState(gear=Gear.DRIVE, epb_engaged=False),
            )

        state_machine.apply(set_moving, actor_kind=ActorKind.SYSTEM, actor_id="test", correlation_id="set_moving")

        guardrail_mock = MagicMock()
        guardrail_mock.evaluate.side_effect = lambda proposal: _block_decision(
            mapper,
            proposal,
            rule_id="R048_AUTOPARK_MOVING",
            reason_code="VEHICLE_MOVING",
            relevant_state={"gear": "D", "speed": 40.0},
        )
        router = DummyModelRouter("control_driver_assistance", {"action": "activate", "target": "auto_park"})
        executor = SpyExecutor(gateway)
        orchestrator = AgentOrchestrator(
            model_router=router, mapper=mapper, guardrail=guardrail_mock, executor=executor
        )
        request = TurnRequest(
            session_id="hero-autopark-blocked",
            turn_id="turn-01",
            request_id="req-01",
            message="Tự động đỗ xe khi đang chạy 40km/h",
        )

        turn_result = orchestrator.handle_message(request)

        assert turn_result.error is None
        assert turn_result.status == TurnStatus.BLOCKED
        assert turn_result.state == TurnState.BLOCKED
        assert turn_result.reason == "VEHICLE_MOVING"
        assert executor.execution_count == 0
        assert registry.get_active_actions(session_id="hero-autopark-blocked") == []
        assert state_machine.snapshot().active_actions == ()
        assert state_machine.snapshot().adas.autopark_state == AutoparkState.OFF

    def test_e2e_monitor_stop_flips_real_vehicle_state_for_campmode(
        self, state_machine, gateway, mapper, registry, event_pipeline
    ):
        """A Guardrail monitor STOP (e.g. low-battery self-cancel) must reach the
        real VehicleState, not just flip the in-memory ActiveActionRecord phase."""
        self._start_via_turn(
            gateway,
            mapper,
            tool_name="control_special_mode",
            arguments={"action": "activate", "target": "camp_mode"},
            rule_id="R_CAMP_SAFE",
            relevant_state={"gear": "P", "battery_pct": 90.0},
            session_id="hero-camp-02",
            message="Bật chế độ cắm trại",
        )
        assert state_machine.snapshot().modes.camp_mode_active is True
        event_pipeline.reset_mock()  # isolate assertions below from the earlier "started" event

        monitor_guardrail = MagicMock()
        monitor_guardrail.evaluate_monitor.return_value = {
            "contract_version": "1.0.0",
            "kind": "decision",
            "request_id": "req-mon-1",
            "intent": "activate_campmode",
            "outcome": "BLOCK_UNSAFE",
            "rule_id": "R_CAMP_BATTERY",
            "state_version": state_machine.snapshot().state_version,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "LOW_BATTERY",
            "relevant_state": {},
        }
        monitor = GuardrailMonitorAdapter(
            guardrail_client=monitor_guardrail,
            active_action_registry=registry,
            event_pipeline=event_pipeline,
        )

        results = monitor.tick(session_id="hero-camp-02")

        assert len(results) == 1
        assert results[0]["stopped"] is True
        assert state_machine.snapshot().modes.camp_mode_active is False  # real state flipped, not just the record

        record = registry.list_all()[0]
        assert record.stop_reason == "monitor_stop:LOW_BATTERY"

        message = AutoparkCampmodeMonitorHeroBehavior.build_stop_message(record, results[0])
        assert "LOW_BATTERY" in message
        assert "R_CAMP_BATTERY" in message

        event_pipeline.emit_decision.assert_called_once()
        event_pipeline.emit_execution.assert_called_once()
        event_pipeline.emit_active_action.assert_called_once()
        assert event_pipeline.emit_active_action.call_args.kwargs["phase"] == "stopped"

    def test_e2e_monitor_stop_flips_real_vehicle_state_for_autopark(
        self, state_machine, gateway, mapper, registry
    ):
        """Autopark's engaged state is set by simulated telemetry (mirroring
        HDA/AAC); a monitor STOP must still turn the real enum back OFF."""
        self._start_via_turn(
            gateway,
            mapper,
            tool_name="control_driver_assistance",
            arguments={"action": "activate", "target": "auto_park"},
            rule_id="R048_AUTOPARK_SAFE",
            relevant_state={"gear": "P", "speed": 0.0},
            session_id="hero-autopark-02",
            message="Tự động đỗ xe giúp tôi",
        )

        # Simulate vehicle telemetry confirming autopark actually engaged (the
        # catalog intentionally leaves autopark_state to be set by the real
        # vehicle/monitor feedback loop, not the agent's activate_autopark
        # proposal itself — see behaviors/catalog.py's ADAS section comment).
        def set_autopark_engaged(s: VehicleState) -> VehicleState:
            return replace(s, adas=replace(s.adas, autopark_state=AutoparkState.ACTIVE))

        state_machine.apply(
            set_autopark_engaged, actor_kind=ActorKind.SYSTEM, actor_id="telemetry", correlation_id="autopark-engaged"
        )
        assert state_machine.snapshot().adas.autopark_state == AutoparkState.ACTIVE

        monitor_guardrail = MagicMock()
        monitor_guardrail.evaluate_monitor.return_value = {
            "contract_version": "1.0.0",
            "kind": "decision",
            "request_id": "req-mon-1",
            "intent": "activate_autopark",
            "outcome": "STOP",
            "rule_id": "R048_STATE_UNSAFE",
            "state_version": state_machine.snapshot().state_version,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "PARKING_SPACE_LOST",
            "relevant_state": {},
        }
        monitor = GuardrailMonitorAdapter(guardrail_client=monitor_guardrail, active_action_registry=registry)

        results = monitor.tick(session_id="hero-autopark-02")

        assert results[0]["stopped"] is True
        assert state_machine.snapshot().adas.autopark_state == AutoparkState.OFF
        running = registry.get_active_actions(session_id="hero-autopark-02")
        assert len(running) == 0

    def test_e2e_reset_and_cleanup_leaves_no_invalid_compound_state(
        self, state_machine, gateway, mapper, registry
    ):
        """Acceptance criterion: reset must not keep an invalid compound state —
        an agent restart/session reset must not leave camp_mode_active=True in
        real VehicleState while the registry shows no running actions."""
        self._start_via_turn(
            gateway,
            mapper,
            tool_name="control_special_mode",
            arguments={"action": "activate", "target": "camp_mode"},
            rule_id="R_CAMP_SAFE",
            relevant_state={"gear": "P", "battery_pct": 90.0},
            session_id="hero-camp-03",
            message="Bật chế độ cắm trại",
        )
        assert state_machine.snapshot().modes.camp_mode_active is True

        cleaned_up = registry.reset_and_cleanup(reason="agent_restart")

        assert len(cleaned_up) == 1
        assert state_machine.snapshot().modes.camp_mode_active is False
        assert state_machine.snapshot().active_actions == ()
        assert registry.get_active_actions(session_id="hero-camp-03") == []
