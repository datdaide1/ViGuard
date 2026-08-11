from __future__ import annotations

import pytest

from vivi_agent.catalog import load_manifest
from vivi_agent.model_providers import ModelActionProposal, ProviderMetadata
from vivi_agent.orchestrator import (
    ApprovedTextAgent,
    GuardedAgentCoordinator,
    GuardedTurnRequest,
    TurnStatus,
    UpstreamGuardrailDecision,
)
from vivi_agent.tools.mapping import load_default_mapper
from vivi_agent.tools.registry import load_registry
from vivi_agent.vehicle.execution import ApprovedToolExecutor, HandlerRegistry


META = ProviderMetadata("test", "tool-model", "sha256:test", 1)


class FakeRouter:
    def propose_tool(self, messages, turn):
        proposal = ModelActionProposal.action(
            "control_access", {"action": "open", "target": "driver_door"}, META
        )
        turn.record_proposal(proposal)
        return proposal


def coordinator(calls: list) -> GuardedAgentCoordinator:
    registry = HandlerRegistry()
    registry.register(
        "open_door",
        lambda proposal: calls.append(proposal)
        or {"message": "Đã mở cửa.", "state_version": 9},
    )
    agent = ApprovedTextAgent(
        model_router=FakeRouter(),
        mapper=load_default_mapper(load_registry(), load_manifest()),
        executor=ApprovedToolExecutor(registry),
        id_factory=lambda prefix: f"{prefix}-1",
    )
    return GuardedAgentCoordinator(agent)


def turn() -> GuardedTurnRequest:
    return GuardedTurnRequest("session-1", "turn-1", "request-1", "Mở cửa ghế lái")


def decision(outcome: str, **overrides) -> UpstreamGuardrailDecision:
    values = {
        "request_id": "request-1",
        "intent": "open_door",
        "outcome": outcome,
        "response": "Bạn có chắc muốn mở cửa không?" if outcome == "CONFIRM" else "Đã xử lý.",
        "state_version": 8,
        "rule_id": "R001",
        "confirmation_id": "confirmation-1" if outcome == "CONFIRM" else None,
        "expires_at": "2099-01-01T00:00:00Z" if outcome == "CONFIRM" else None,
    }
    values.update(overrides)
    return UpstreamGuardrailDecision(**values)


def test_allow_calls_agent_tool_and_executes_action():
    calls = []

    result = coordinator(calls).handle_decision(turn(), decision("ALLOW"))

    assert result.status is TurnStatus.COMPLETED
    assert result.message == "Đã mở cửa."
    assert len(calls) == 1


def test_allow_does_not_require_guardrail_response_text():
    calls = []

    result = coordinator(calls).handle_decision(turn(), decision("ALLOW", response=""))

    assert result.status is TurnStatus.COMPLETED
    assert result.message == "Đã mở cửa."
    assert len(calls) == 1


def test_guardrail_decision_for_another_request_is_rejected_without_action():
    calls = []

    with pytest.raises(ValueError, match="request_id does not match"):
        coordinator(calls).handle_decision(
            turn(), decision("ALLOW", request_id="request-from-another-turn")
        )

    assert calls == []


@pytest.mark.parametrize("outcome", ["BLOCK", "BLOCK_UNSAFE", "BLOCK_UNAVAILABLE"])
def test_block_returns_guardrail_explanation_without_action(outcome):
    calls = []

    result = coordinator(calls).handle_decision(
        turn(), decision(outcome, response="Không thể mở cửa vì xe đang chạy.")
    )

    assert result.status is TurnStatus.BLOCKED
    assert result.message == "Không thể mở cửa vì xe đang chạy."
    assert result.rule_id == "R001"
    assert calls == []


def test_confirm_waits_and_rejection_never_executes():
    calls = []
    guarded = coordinator(calls)

    pending = guarded.handle_decision(turn(), decision("CONFIRM"))
    result = guarded.resolve_confirmation("confirmation-1", accepted=False)

    assert pending.status is TurnStatus.NEEDS_CONFIRMATION
    assert result.status is TurnStatus.BLOCKED
    assert result.reason == "CONFIRMATION_REJECTED"
    assert calls == []


def test_confirm_acceptance_requires_fresh_allow_then_executes_once():
    calls = []
    guarded = coordinator(calls)
    guarded.handle_decision(turn(), decision("CONFIRM"))

    result = guarded.resolve_confirmation(
        "confirmation-1", accepted=True, refreshed_decision=decision("ALLOW")
    )

    assert result.status is TurnStatus.COMPLETED
    assert len(calls) == 1
    with pytest.raises(ValueError, match="already resolved"):
        guarded.resolve_confirmation(
            "confirmation-1", accepted=True, refreshed_decision=decision("ALLOW")
        )
    assert len(calls) == 1


def test_confirm_acceptance_can_be_blocked_by_fresh_state_without_action():
    calls = []
    guarded = coordinator(calls)
    guarded.handle_decision(turn(), decision("CONFIRM"))

    result = guarded.resolve_confirmation(
        "confirmation-1",
        accepted=True,
        refreshed_decision=decision(
            "BLOCK_UNSAFE", response="Không thể mở cửa vì xe đã bắt đầu di chuyển."
        ),
    )

    assert result.status is TurnStatus.BLOCKED
    assert result.message == "Không thể mở cửa vì xe đã bắt đầu di chuyển."
    assert calls == []


def test_confirm_acceptance_without_fresh_guardrail_decision_does_not_execute():
    calls = []
    guarded = coordinator(calls)
    guarded.handle_decision(turn(), decision("CONFIRM"))

    with pytest.raises(ValueError, match="fresh Guardrail decision"):
        guarded.resolve_confirmation("confirmation-1", accepted=True)

    assert calls == []
