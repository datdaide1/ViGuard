"""E2E/integration tests for HERO-02 — HDA/AAC active driving assist hero behaviors."""

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
    AdasMonitorHeroBehavior,
    make_monitored_hda_aac_handler,
    register_hda_aac_stop_handlers,
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
from vivi_agent.vehicle.state.model import AccState, VehicleState
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


class TestHero02HdaAacE2E:
    @pytest.fixture
    def state_machine(self) -> VehicleStateMachine:
        base = get_preset("parked_ready", state_version=1, timestamp=_NOW)
        state = replace(base, adas=replace(base.adas, acc_state=AccState.ACTIVE))
        return VehicleStateMachine(state)

    @pytest.fixture
    def event_pipeline(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def registry(self, state_machine: VehicleStateMachine, event_pipeline: MagicMock) -> ActiveActionRegistry:
        reg = ActiveActionRegistry(event_pipeline=event_pipeline)
        register_hda_aac_stop_handlers(reg, state_machine)
        return reg

    @pytest.fixture
    def gateway(self, state_machine: VehicleStateMachine, registry: ActiveActionRegistry) -> VehicleToolGateway:
        gw = VehicleToolGateway()
        gw.registry.register(
            "activate_hda",
            make_monitored_hda_aac_handler(get_behavior_config("activate_hda"), state_machine, registry),
        )
        gw.registry.register(
            "activate_aac",
            make_monitored_hda_aac_handler(get_behavior_config("activate_aac"), state_machine, registry),
        )
        return gw

    @pytest.fixture
    def mapper(self):
        return load_default_mapper(load_registry(), load_manifest())

    def _start_hda_via_turn(self, state_machine, gateway, mapper, registry, session_id="hero-hda-01"):
        def mock_evaluate(proposal: Mapping[str, Any]) -> dict[str, Any]:
            mapped = mapper.map_proposal(proposal)
            return {
                "contract_version": "1.0.0",
                "kind": "decision",
                "request_id": f"req-{proposal['proposal_id']}",
                "proposal_id": proposal["proposal_id"],
                "intent": mapped.canonical_action.intent,
                "outcome": "ALLOW",
                "rule_id": "R073_HDA_SAFE",
                "state_version": 1,
                "policy_checksum": "sha256:" + "0" * 64,
                "reason_code": "PERMITTED",
                "relevant_state": {"speed": 90.0, "gear": "D"},
                "permit": {
                    "permit_id": f"permit-{proposal['proposal_id']}",
                    "proposal_digest": mapped.proposal_digest,
                    "intent": mapped.canonical_action.intent,
                    "rule_id": "R073_HDA_SAFE",
                    "state_version": 1,
                    "policy_checksum": "sha256:" + "0" * 64,
                    "issued_at": "2026-08-06T10:00:00Z",
                    "expires_at": "2030-01-01T00:00:00Z",
                    "single_use": True,
                },
            }

        guardrail_mock = MagicMock()
        guardrail_mock.evaluate.side_effect = mock_evaluate
        router = DummyModelRouter("control_driver_assistance", {"action": "activate", "target": "highway_drive_assist"})
        executor = SpyExecutor(gateway)
        orchestrator = AgentOrchestrator(
            model_router=router, mapper=mapper, guardrail=guardrail_mock, executor=executor
        )
        request = TurnRequest(
            session_id=session_id,
            turn_id="turn-01",
            request_id="req-01",
            message="Bật hỗ trợ lái trên cao tốc giúp tôi",
        )
        turn_result = orchestrator.handle_message(request)
        assert turn_result.error is None, f"Turn failed: {turn_result.error}"
        assert turn_result.status == TurnStatus.COMPLETED
        assert turn_result.state == TurnState.COMPLETED
        return turn_result

    def test_e2e_activate_hda_creates_active_action_record(
        self, state_machine, gateway, mapper, registry, event_pipeline
    ):
        """Starting activate_hda through a real orchestrator turn must register
        an ActiveActionRecord — closing the gap where nothing ever called
        registry.start_action() — and publish a status event for the UI."""
        self._start_hda_via_turn(state_machine, gateway, mapper, registry)

        running = registry.get_active_actions(session_id="hero-hda-01")
        assert len(running) == 1
        assert running[0].intent == "activate_hda"
        assert running[0].active_action_name == "hda"

        event_pipeline.emit_active_action.assert_called_once()
        assert event_pipeline.emit_active_action.call_args.kwargs["phase"] == "started"
        assert event_pipeline.emit_active_action.call_args.kwargs["intent"] == "activate_hda"

    def test_e2e_monitor_stop_flips_real_vehicle_state(self, state_machine, gateway, mapper, registry, event_pipeline):
        """A Guardrail monitor STOP decision must reach the real VehicleState,
        not just flip the in-memory ActiveActionRecord phase (the exact gap
        documented in mon-adp-01/DEFERRED_FOLLOWUPS.md #1)."""
        self._start_hda_via_turn(state_machine, gateway, mapper, registry)

        # Simulate vehicle telemetry confirming HDA actually engaged (the
        # catalog intentionally leaves hda_active to be set by the real
        # vehicle/monitor feedback loop, not the agent's activate_hda proposal
        # itself — see behaviors/catalog.py's ADAS section comment).
        def set_hda_engaged(s: VehicleState) -> VehicleState:
            return replace(s, adas=replace(s.adas, hda_active=True))

        state_machine.apply(
            set_hda_engaged, actor_kind=ActorKind.SYSTEM, actor_id="telemetry", correlation_id="hda-engaged"
        )
        assert state_machine.snapshot().adas.hda_active is True
        event_pipeline.reset_mock()  # isolate the assertions below from the earlier "started" event

        monitor_guardrail = MagicMock()
        monitor_guardrail.evaluate_monitor.return_value = {
            "contract_version": "1.0.0",
            "kind": "decision",
            "request_id": "req-mon-1",
            "intent": "activate_hda",
            "outcome": "BLOCK_UNSAFE",
            "rule_id": "R073_HANDS_OFF",
            "state_version": state_machine.snapshot().state_version,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "HANDS_OFF_TIMEOUT",
            "relevant_state": {},
        }
        monitor = GuardrailMonitorAdapter(
            guardrail_client=monitor_guardrail,
            active_action_registry=registry,
            event_pipeline=event_pipeline,
        )

        results = monitor.tick(session_id="hero-hda-01")

        assert len(results) == 1
        assert results[0]["stopped"] is True
        assert state_machine.snapshot().adas.hda_active is False  # real state flipped, not just the record

        record = registry.list_all()[0]
        assert record.stop_reason == "monitor_stop:HANDS_OFF_TIMEOUT"

        message = AdasMonitorHeroBehavior.build_stop_message(record, results[0])
        assert "HANDS_OFF_TIMEOUT" in message
        assert "R073_HANDS_OFF" in message

        # UI must be able to tell "policy said stop" (decision) apart from
        # "execution/lifecycle transitioned" (execution + active_action) —
        # HERO-02 acceptance criteria: distinct policy vs execution status.
        event_pipeline.emit_decision.assert_called_once()
        event_pipeline.emit_execution.assert_called_once()
        event_pipeline.emit_active_action.assert_called_once()
        assert event_pipeline.emit_active_action.call_args.kwargs["phase"] == "stopped"

    def test_e2e_aac_stop_and_go_hold_is_not_stopped_by_speed_zero(self, state_machine, gateway, mapper, registry):
        """Speed=0 while ACC is ACTIVE (Stop&Go Hold) must NOT be treated as a
        violation by the Agent — only Guardrail's monitor outcome decides."""
        router = DummyModelRouter(
            "control_driver_assistance", {"action": "activate", "target": "adaptive_cruise_control"}
        )

        def mock_evaluate(proposal: Mapping[str, Any]) -> dict[str, Any]:
            mapped = mapper.map_proposal(proposal)
            return {
                "contract_version": "1.0.0",
                "kind": "decision",
                "request_id": f"req-{proposal['proposal_id']}",
                "proposal_id": proposal["proposal_id"],
                "intent": mapped.canonical_action.intent,
                "outcome": "ALLOW",
                "rule_id": "R070_AAC_SAFE",
                "state_version": 1,
                "policy_checksum": "sha256:" + "0" * 64,
                "reason_code": "PERMITTED",
                "relevant_state": {"speed": 0.0, "gear": "D"},
                "permit": {
                    "permit_id": f"permit-{proposal['proposal_id']}",
                    "proposal_digest": mapped.proposal_digest,
                    "intent": mapped.canonical_action.intent,
                    "rule_id": "R070_AAC_SAFE",
                    "state_version": 1,
                    "policy_checksum": "sha256:" + "0" * 64,
                    "issued_at": "2026-08-06T10:00:00Z",
                    "expires_at": "2030-01-01T00:00:00Z",
                    "single_use": True,
                },
            }

        guardrail_mock = MagicMock()
        guardrail_mock.evaluate.side_effect = mock_evaluate
        orchestrator = AgentOrchestrator(
            model_router=router, mapper=mapper, guardrail=guardrail_mock, executor=SpyExecutor(gateway)
        )
        turn_result = orchestrator.handle_message(
            TurnRequest(
                session_id="hero-aac-01",
                turn_id="turn-01",
                request_id="req-01",
                message="Bật điều khiển hành trình thích ứng",
            )
        )
        assert turn_result.status == TurnStatus.COMPLETED

        # Vehicle comes to a full stop (Stop&Go Hold) — ACC stays ACTIVE per
        # the vehicle manual; this is NOT a violation.
        def set_stopped(s: VehicleState) -> VehicleState:
            from vivi_agent.vehicle.state.model import MotionPhase, MotionState

            return replace(s, motion=MotionState(speed_kph=0.0, phase=MotionPhase.STOPPED))

        state_machine.apply(set_stopped, actor_kind=ActorKind.SYSTEM, actor_id="telemetry", correlation_id="stop-go")

        monitor_guardrail = MagicMock()
        monitor_guardrail.evaluate_monitor.return_value = {
            "contract_version": "1.0.0",
            "kind": "decision",
            "request_id": "req-mon-1",
            "intent": "activate_aac",
            "outcome": "ALLOW",
            "rule_id": "R070_STOP_AND_GO_HOLD",
            "state_version": state_machine.snapshot().state_version,
            "policy_checksum": "sha256:" + "0" * 64,
            "reason_code": "STOP_AND_GO_HOLD_PERMITTED",
            "relevant_state": {},
        }
        monitor = GuardrailMonitorAdapter(guardrail_client=monitor_guardrail, active_action_registry=registry)

        results = monitor.tick(session_id="hero-aac-01")

        assert results[0]["outcome"] == "ALLOW"
        assert results[0]["stopped"] is False
        assert state_machine.snapshot().adas.acc_state == AccState.ACTIVE  # untouched
        running = registry.get_active_actions(session_id="hero-aac-01")
        assert len(running) == 1  # still running — Agent never second-guessed Guardrail
