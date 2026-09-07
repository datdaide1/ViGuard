"""E2E/integration tests for HERO-04 — confirmation hero behavior (open_window)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from unittest.mock import MagicMock

import pytest

from vehicle_agent.behaviors.catalog import get_behavior_config
from vehicle_agent.behaviors.hero import CONFIRMATION_HERO_INTENT, ConfirmationHeroBehavior
from vehicle_agent.catalog import load_manifest
from vehicle_agent.confirmation import ConfirmationManager, ConfirmationState
from vehicle_agent.contracts.guardrail.v1.contract import proposal_digest
from vehicle_agent.model_providers import ModelActionProposal, ProviderMetadata, TurnBinding
from vehicle_agent.orchestrator import (
    AgentOrchestrator,
    CancellationToken,
    ExecutionResult,
    TurnRequest,
    TurnState,
    TurnStatus,
)
from vehicle_agent.tools.mapping import load_default_mapper
from vehicle_agent.tools.registry import load_registry
from vehicle_agent.vehicle.execution import VehicleToolGateway
from vehicle_agent.vehicle.execution.generic import ToggleHandler
from vehicle_agent.vehicle.state.machine import VehicleStateMachine
from vehicle_agent.vehicle.state.presets import get_preset

_NOW = datetime(2026, 8, 7, 10, 0, 0, tzinfo=timezone.utc)
META = ProviderMetadata("openai", "test-model-v1", "sha256:test", 5)
_ZERO_CHECKSUM = "sha256:" + "0" * 64


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
        cancellation: CancellationToken | None,
    ) -> ExecutionResult:
        self.execution_count += 1
        return self.gateway.execute(proposal, decision, cancellation, current_time=_NOW)


def _confirm_decision(proposal: Mapping[str, Any], mapper, *, confirmation_id: str, expires_at: str) -> dict[str, Any]:
    mapped = mapper.map_proposal(proposal)
    return {
        "contract_version": "1.0.0",
        "kind": "decision",
        "request_id": f"req-{proposal['proposal_id']}",
        "proposal_id": proposal["proposal_id"],
        "intent": mapped.canonical_action.intent,
        "outcome": "CONFIRM",
        "rule_id": "R_WINDOW_CONFIRM",
        "state_version": 1,
        "policy_checksum": _ZERO_CHECKSUM,
        "reason_code": "DRIVER_CONFIRMATION_REQUIRED",
        "relevant_state": {},
        "confirmation": {
            "confirmation_id": confirmation_id,
            "proposal_id": proposal["proposal_id"],
            "prompt": "Bạn có chắc chắn muốn mở cửa sổ không?",
            "expires_at": expires_at,
            "single_use": True,
        },
    }


def _fresh_allow_permit(action_proposal: Mapping[str, Any], *, permit_id: str) -> dict[str, Any]:
    return {
        "permit_id": permit_id,
        "proposal_digest": proposal_digest(action_proposal),
        "intent": "open_window",
        "rule_id": "R_WINDOW_CONFIRM_ALLOW",
        "state_version": 1,
        "policy_checksum": _ZERO_CHECKSUM,
        "issued_at": "2026-08-07T10:00:00Z",
        "expires_at": "2030-01-01T00:00:00Z",
        "single_use": True,
    }


def _fresh_allow_decision(permit: Mapping[str, Any]) -> dict[str, Any]:
    """A fresh ALLOW decision matching ``permit`` on every field
    ``PermitVerifier.verify()`` cross-checks (intent/rule_id/state_version/
    policy_checksum) — a decision missing any of these fails permit
    verification with INVALID_PERMIT, not a digest/replay error.
    """
    return {
        "contract_version": "1.0.0",
        "kind": "decision",
        "outcome": "ALLOW",
        "reason_code": "CONFIRMATION_REEVALUATED_ALLOW",
        "intent": permit["intent"],
        "rule_id": permit["rule_id"],
        "state_version": permit["state_version"],
        "policy_checksum": permit["policy_checksum"],
        "permit": dict(permit),
    }


class TestHero04ConfirmationE2E:
    @pytest.fixture
    def state_machine(self) -> VehicleStateMachine:
        base = get_preset("parked_ready", state_version=1, timestamp=_NOW)
        return VehicleStateMachine(base)

    @pytest.fixture
    def gateway(self, state_machine: VehicleStateMachine) -> VehicleToolGateway:
        gw = VehicleToolGateway()
        gw.registry.register(
            CONFIRMATION_HERO_INTENT,
            ToggleHandler(get_behavior_config(CONFIRMATION_HERO_INTENT), state_machine),
        )
        return gw

    @pytest.fixture
    def mapper(self):
        return load_default_mapper(load_registry(), load_manifest())

    @pytest.fixture
    def confirmation_manager(self) -> ConfirmationManager:
        return ConfirmationManager()

    def _propose_confirm_turn(
        self, mapper, confirmation_manager, gateway, *, confirmation_id: str, expires_at: str = "2030-01-01T00:00:00Z"
    ):
        """Run one real orchestrator turn where Guardrail returns CONFIRM.

        Returns (turn_result, guardrail_mock, executor) so callers can also
        assert on executor.execution_count (must stay 0 until confirm()).
        """
        guardrail_mock = MagicMock()
        guardrail_mock.evaluate.side_effect = lambda proposal: _confirm_decision(
            proposal, mapper, confirmation_id=confirmation_id, expires_at=expires_at
        )
        router = DummyModelRouter("control_cabin", {"action": "open", "target": "driver_window"})
        executor = SpyExecutor(gateway)
        orchestrator = AgentOrchestrator(
            model_router=router,
            mapper=mapper,
            guardrail=guardrail_mock,
            executor=executor,
            confirmation_manager=confirmation_manager,
        )
        request = TurnRequest(
            session_id="hero-confirm-01",
            turn_id="turn-01",
            request_id="req-01",
            message="Mở cửa sổ giúp tôi",
        )
        turn_result = orchestrator.handle_message(request)
        return turn_result, guardrail_mock, executor

    def test_e2e_confirm_decision_registers_pending_confirmation(self, mapper, confirmation_manager, gateway):
        """The wiring gap this ticket closes: before this, nothing ever called
        ConfirmationManager.register_pending() for a real CONFIRM decision, so
        a later confirm() call always failed with CONFIRMATION_NOT_FOUND."""
        turn_result, _guardrail, executor = self._propose_confirm_turn(
            mapper, confirmation_manager, gateway, confirmation_id="confirm-e2e-01"
        )

        assert turn_result.error is None, f"Turn failed: {turn_result.error}"
        assert turn_result.status == TurnStatus.NEEDS_CONFIRMATION
        assert turn_result.state == TurnState.AWAITING_CONFIRMATION
        assert turn_result.confirmation_id == "confirm-e2e-01"

        pending = confirmation_manager.get_pending("confirm-e2e-01")
        assert pending is not None
        assert pending.state == ConfirmationState.PENDING
        assert pending.proposal_id == turn_result.proposal_id

        # Acceptance criterion: "Chưa confirm không gọi handler" — the ToggleHandler
        # never ran, so windows_open must still be the untouched default.
        assert executor.execution_count == 0
        assert gateway.execute is not None  # gateway constructed but never invoked via executor

    def test_e2e_pending_facts_expose_intent_alongside_stored_fields(self, mapper, confirmation_manager, gateway):
        """'Pending event payload' work item: ConfirmationHeroBehavior.build_pending_facts
        must surface the mapped intent, which PendingConfirmation itself doesn't store."""
        turn_result, _guardrail, _executor = self._propose_confirm_turn(
            mapper, confirmation_manager, gateway, confirmation_id="confirm-e2e-02"
        )
        pending = confirmation_manager.get_pending(turn_result.confirmation_id)

        facts = ConfirmationHeroBehavior.build_pending_facts(pending, intent=CONFIRMATION_HERO_INTENT)

        assert facts["intent"] == "open_window"
        assert facts["confirmation_id"] == turn_result.confirmation_id
        assert facts["proposal_id"] == turn_result.proposal_id
        assert facts["state"] == ConfirmationState.PENDING.value

    def test_e2e_confirm_executes_via_real_gateway_and_flips_state(
        self, state_machine, mapper, confirmation_manager, gateway
    ):
        """Proves the executor.execute() call-shape fix: against a real
        VehicleToolGateway (not a loose MagicMock), confirm() must actually
        open the window."""
        turn_result, _guardrail, executor = self._propose_confirm_turn(
            mapper, confirmation_manager, gateway, confirmation_id="confirm-e2e-03"
        )
        pending = confirmation_manager.get_pending("confirm-e2e-03")

        fresh_permit = _fresh_allow_permit(pending.action_proposal, permit_id="permit-confirm-e2e-03")
        guardrail_client = MagicMock()
        guardrail_client.confirm.return_value = _fresh_allow_decision(fresh_permit)

        assert state_machine.snapshot().cabin.windows_open is False

        result = confirmation_manager.confirm(
            confirmation_id="confirm-e2e-03",
            session_id="hero-confirm-01",
            guardrail_client=guardrail_client,
            executor=executor,
        )

        assert result.status == "completed"
        assert result.state == ConfirmationState.CONSUMED
        assert state_machine.snapshot().cabin.windows_open is True  # real state actually flipped
        assert executor.execution_count == 1

    def test_e2e_pre_cancelled_token_short_circuits_before_guardrail_and_preserves_token(
        self, state_machine, mapper, confirmation_manager, gateway
    ):
        """A cancellation token that's already cancelled when confirm() is
        called must short-circuit immediately — before the fresh Guardrail
        re-evaluation and before the single-use token is consumed — not just
        get forwarded to the executor after both have already happened. The
        earlier bug (no cancellation parameter at all, permit hardcoded into
        the 3rd positional slot) meant cancellation could never be honored at
        any point; the naive fix (forward it to the executor only) would
        still burn a live Guardrail call and consume the confirmation for a
        request the caller already knew shouldn't proceed."""
        turn_result, _guardrail, executor = self._propose_confirm_turn(
            mapper, confirmation_manager, gateway, confirmation_id="confirm-e2e-04"
        )
        pending = confirmation_manager.get_pending("confirm-e2e-04")

        fresh_permit = _fresh_allow_permit(pending.action_proposal, permit_id="permit-confirm-e2e-04")
        guardrail_client = MagicMock()
        guardrail_client.confirm.return_value = _fresh_allow_decision(fresh_permit)

        token = CancellationToken()
        token.cancel()

        result = confirmation_manager.confirm(
            confirmation_id="confirm-e2e-04",
            session_id="hero-confirm-01",
            guardrail_client=guardrail_client,
            executor=executor,
            cancellation=token,
        )

        assert result.status == "failed"
        assert result.error["code"] == "EXECUTION_CANCELLED"
        assert result.state == ConfirmationState.PENDING
        guardrail_client.confirm.assert_not_called()  # no wasted re-evaluation
        assert executor.execution_count == 0  # handler never touched
        assert state_machine.snapshot().cabin.windows_open is False  # never actually opened

        # The single-use token was preserved (not burned) — a genuine retry
        # without a stale cancellation must still be able to succeed.
        pending_after = confirmation_manager.get_pending("confirm-e2e-04")
        assert pending_after.state == ConfirmationState.PENDING
        retry = confirmation_manager.confirm(
            confirmation_id="confirm-e2e-04",
            session_id="hero-confirm-01",
            guardrail_client=guardrail_client,
            executor=executor,
        )
        assert retry.status == "completed"
        assert state_machine.snapshot().cabin.windows_open is True

    def test_e2e_state_change_before_confirm_uses_fresh_decision_not_stale(
        self, mapper, confirmation_manager, gateway
    ):
        """State-change-before-confirm fixture: between the initial CONFIRM and
        the driver actually confirming, the vehicle state changes such that
        Guardrail's fresh re-evaluation now blocks — the Agent must honor
        that fresh outcome, not the original (now-stale) CONFIRM decision."""
        turn_result, _guardrail, executor = self._propose_confirm_turn(
            mapper, confirmation_manager, gateway, confirmation_id="confirm-e2e-05"
        )

        # Guardrail's fresh confirm-time re-evaluation reflects a state change
        # that happened after the original proposal (e.g. vehicle started
        # moving) — this is a BLOCK now, never an ALLOW/permit.
        guardrail_client = MagicMock()
        guardrail_client.confirm.return_value = {
            "contract_version": "1.0.0",
            "kind": "decision",
            "outcome": "BLOCK_UNSAFE",
            "reason_code": "VEHICLE_MOVING",
            "rule_id": "R_WINDOW_SPEED_CHECK",
        }

        result = confirmation_manager.confirm(
            confirmation_id="confirm-e2e-05",
            session_id="hero-confirm-01",
            guardrail_client=guardrail_client,
            executor=executor,
        )

        assert result.status == "blocked"
        assert result.state == ConfirmationState.CONSUMED  # single-use: consumed even though blocked
        assert executor.execution_count == 0  # handler never called — fresh decision wasn't ALLOW

    def test_e2e_replay_after_consumption_calls_handler_zero_additional_times(
        self, mapper, confirmation_manager, gateway
    ):
        """Acceptance criterion: 'Replay gọi handler zero lần' — a second
        confirm() for an already-consumed confirmation must not touch the
        executor at all."""
        turn_result, _guardrail, executor = self._propose_confirm_turn(
            mapper, confirmation_manager, gateway, confirmation_id="confirm-e2e-06"
        )
        pending = confirmation_manager.get_pending("confirm-e2e-06")

        fresh_permit = _fresh_allow_permit(pending.action_proposal, permit_id="permit-confirm-e2e-06")
        guardrail_client = MagicMock()
        guardrail_client.confirm.return_value = _fresh_allow_decision(fresh_permit)

        first = confirmation_manager.confirm(
            "confirm-e2e-06", "hero-confirm-01", guardrail_client, executor
        )
        assert first.status == "completed"
        assert executor.execution_count == 1

        replay = confirmation_manager.confirm(
            "confirm-e2e-06", "hero-confirm-01", guardrail_client, executor
        )
        assert replay.status == "failed"
        assert replay.error["code"] == "CONFIRMATION_ALREADY_CONSUMED"
        assert executor.execution_count == 1  # unchanged — replay called the handler zero additional times
        guardrail_client.confirm.assert_called_once()  # replay never even re-evaluates with Guardrail

    def test_e2e_expiry_rejects_before_touching_guardrail_or_executor(self, mapper, confirmation_manager, gateway):
        turn_result, _guardrail, executor = self._propose_confirm_turn(
            mapper,
            confirmation_manager,
            gateway,
            confirmation_id="confirm-e2e-07",
            expires_at="2026-08-07T10:00:01Z",
        )

        guardrail_client = MagicMock()
        past_expiry_now = datetime(2026, 8, 7, 10, 5, 0, tzinfo=timezone.utc)

        result = confirmation_manager.confirm(
            "confirm-e2e-07", "hero-confirm-01", guardrail_client, executor, now=past_expiry_now
        )

        assert result.status == "expired"
        assert result.state == ConfirmationState.EXPIRED
        guardrail_client.confirm.assert_not_called()
        assert executor.execution_count == 0

    def test_e2e_cancel_confirmation_zero_handler_calls(self, mapper, confirmation_manager, gateway):
        turn_result, _guardrail, executor = self._propose_confirm_turn(
            mapper, confirmation_manager, gateway, confirmation_id="confirm-e2e-08"
        )

        result = confirmation_manager.cancel("confirm-e2e-08", "hero-confirm-01")

        assert result.status == "cancelled"
        assert result.state == ConfirmationState.CANCELLED
        assert executor.execution_count == 0

        # A cancelled confirmation must also reject a subsequent confirm attempt.
        guardrail_client = MagicMock()
        late_confirm = confirmation_manager.confirm(
            "confirm-e2e-08", "hero-confirm-01", guardrail_client, executor
        )
        assert late_confirm.status == "failed"
        assert late_confirm.error["code"] == "CONFIRMATION_ALREADY_CONSUMED"
        guardrail_client.confirm.assert_not_called()
        assert executor.execution_count == 0

    def test_confirmation_manager_is_optional_and_backward_compatible(self, mapper, gateway):
        """AgentOrchestrator without a confirmation_manager (the pre-HERO-04
        default) must still return NEEDS_CONFIRMATION normally — the port is
        additive, not a breaking change for existing callers."""
        guardrail_mock = MagicMock()
        guardrail_mock.evaluate.side_effect = lambda proposal: _confirm_decision(
            proposal, mapper, confirmation_id="confirm-no-manager", expires_at="2030-01-01T00:00:00Z"
        )
        router = DummyModelRouter("control_cabin", {"action": "open", "target": "driver_window"})
        orchestrator = AgentOrchestrator(
            model_router=router, mapper=mapper, guardrail=guardrail_mock, executor=SpyExecutor(gateway)
        )
        turn_result = orchestrator.handle_message(
            TurnRequest(
                session_id="hero-confirm-02",
                turn_id="turn-01",
                request_id="req-01",
                message="Mở cửa sổ giúp tôi",
            )
        )

        assert turn_result.status == TurnStatus.NEEDS_CONFIRMATION
        assert turn_result.confirmation_id == "confirm-no-manager"
