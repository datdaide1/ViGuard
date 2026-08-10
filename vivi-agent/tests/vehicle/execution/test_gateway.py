"""Boundary, anti-replay, anti-substitution, and lifecycle tests for Vehicle Tool Gateway."""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import pytest

from vivi_agent.contracts.guardrail.v1.contract import proposal_digest
from vivi_agent.orchestrator.orchestrator import CancellationToken
from vivi_agent.vehicle.execution import (
    ExpiredPermitError,
    GatewayExecutionError,
    HandlerRegistry,
    InvalidPermitError,
    PermitStore,
    PermitVerifier,
    ReplayAttackError,
    SubstitutionAttackError,
    VehicleToolGateway,
)


class ActuatorSpy:
    """Spy wrapper for vehicle actuator handlers to assert execution boundary rules."""

    def __init__(self, return_value: Any = None) -> None:
        self.call_count = 0
        self.last_proposal: Mapping[str, Any] | None = None
        self.return_value = return_value if return_value is not None else {
            "state_version": 42,
            "message": "Actuator executed successfully",
            "facts": {"door": "driver_door", "target_state": "open"},
        }

    def __call__(self, proposal: Mapping[str, Any]) -> Any:
        self.call_count += 1
        self.last_proposal = proposal
        return self.return_value


def make_proposal(
    proposal_id: str = "prop-101",
    session_id: str = "sess-001",
    source_turn_id: str = "turn-001",
    tool: str = "open_door",
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": "1.0.0",
        "proposal_id": proposal_id,
        "session_id": session_id,
        "source_turn_id": source_turn_id,
        "tool": tool,
        "arguments": arguments if arguments is not None else {"door": "driver_door"},
        "model_provider": "openai",
        "model_id": "gpt-4o",
    }


def make_permit(
    proposal: dict[str, Any],
    permit_id: str = "permit-101",
    intent: str = "open_door",
    rule_id: str = "R001",
    state_version: int = 41,
    policy_checksum: str = "sha256:" + "a" * 64,
    issued_at: str = "2026-08-04T12:00:00Z",
    expires_at: str = "2026-08-04T12:05:00Z",
    single_use: bool = True,
) -> dict[str, Any]:
    digest = proposal_digest(proposal)
    return {
        "permit_id": permit_id,
        "proposal_digest": digest,
        "intent": intent,
        "rule_id": rule_id,
        "state_version": state_version,
        "policy_checksum": policy_checksum,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "single_use": single_use,
    }


def make_decision(
    proposal: dict[str, Any],
    permit: dict[str, Any] | None = None,
    outcome: str = "ALLOW",
    request_id: str = "req-101",
    rule_id: str = "R001",
    state_version: int = 41,
    policy_checksum: str = "sha256:" + "a" * 64,
    reason_code: str = "SAFE_OPERATION",
) -> dict[str, Any]:
    if permit is None and outcome == "ALLOW":
        permit = make_permit(
            proposal,
            rule_id=rule_id,
            state_version=state_version,
            policy_checksum=policy_checksum,
        )

    dec = {
        "contract_version": "1.0.0",
        "kind": "decision",
        "request_id": request_id,
        "proposal_id": proposal["proposal_id"],
        "intent": permit["intent"] if permit else proposal["tool"],
        "outcome": outcome,
        "rule_id": rule_id,
        "state_version": state_version,
        "policy_checksum": policy_checksum,
        "reason_code": reason_code,
        "relevant_state": {"door": "closed"},
    }
    if permit is not None:
        dec["permit"] = permit
    return dec


# --- VERIFIER & PERMIT STORE TESTS ---


def test_permit_verifier_valid_proposal_and_permit():
    proposal = make_proposal()
    permit = make_permit(proposal)
    decision = make_decision(proposal, permit)
    verifier = PermitVerifier()

    now = datetime.fromisoformat("2026-08-04T12:01:00+00:00")
    verifier.verify(proposal=proposal, permit=permit, decision=decision, current_time=now)


def test_permit_verifier_substitution_attack():
    proposal = make_proposal()
    permit = make_permit(proposal)

    # Substituted proposal with modified arguments
    substituted_proposal = make_proposal(arguments={"door": "passenger_door"})

    verifier = PermitVerifier()
    now = datetime.fromisoformat("2026-08-04T12:01:00+00:00")

    with pytest.raises(SubstitutionAttackError):
        verifier.verify(proposal=substituted_proposal, permit=permit, current_time=now)


def test_permit_verifier_expired_permit():
    proposal = make_proposal()
    permit = make_permit(proposal, expires_at="2026-08-04T12:05:00Z")
    verifier = PermitVerifier()

    now = datetime.fromisoformat("2026-08-04T12:10:00+00:00")  # After expiration
    with pytest.raises(ExpiredPermitError):
        verifier.verify(proposal=proposal, permit=permit, current_time=now)


def test_permit_verifier_future_permit():
    proposal = make_proposal()
    permit = make_permit(proposal, issued_at="2026-08-04T12:05:00Z")
    verifier = PermitVerifier()

    now = datetime.fromisoformat("2026-08-04T12:00:00+00:00")  # Before issue
    with pytest.raises(InvalidPermitError):
        verifier.verify(proposal=proposal, permit=permit, current_time=now)


def test_permit_store_single_use_replay():
    store = PermitStore()
    store.mark_used("permit-001")
    assert store.is_used("permit-001") is True
    assert store.is_used("permit-002") is False

    with pytest.raises(ReplayAttackError):
        store.mark_used("permit-001")


# --- VEHICLE TOOL GATEWAY TESTS ---


def test_gateway_successful_execution():
    spy = ActuatorSpy()
    registry = HandlerRegistry()
    registry.register("open_door", spy)

    gateway = VehicleToolGateway(registry=registry)
    proposal = make_proposal()
    decision = make_decision(proposal)

    now = datetime.fromisoformat("2026-08-04T12:01:00+00:00")
    result = gateway.execute(proposal, decision, current_time=now)

    assert result.success is True
    assert result.state_version == 42
    assert result.facts == {"door": "driver_door", "target_state": "open"}
    assert spy.call_count == 1
    assert spy.last_proposal == proposal
    assert gateway.store.is_used(decision["permit"]["permit_id"]) is True


def test_gateway_cancellation_token_cancels_execution():
    spy = ActuatorSpy()
    registry = HandlerRegistry()
    registry.register("open_door", spy)

    gateway = VehicleToolGateway(registry=registry)
    proposal = make_proposal()
    decision = make_decision(proposal)

    cancellation = CancellationToken()
    cancellation.cancel()

    result = gateway.execute(proposal, decision, cancellation=cancellation)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "EXECUTION_CANCELLED"
    assert spy.call_count == 0


@pytest.mark.parametrize(
    "outcome",
    ["BLOCK_UNSAFE", "BLOCK_UNAVAILABLE", "CONFIRM", "ANSWER", "UNKNOWN"],
)
def test_gateway_non_allow_outcomes_zero_handler_calls(outcome: str):
    spy = ActuatorSpy()
    registry = HandlerRegistry()
    registry.register("open_door", spy)

    gateway = VehicleToolGateway(registry=registry)
    proposal = make_proposal()
    decision = make_decision(proposal, permit=None, outcome=outcome)

    result = gateway.execute(proposal, decision)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "EXECUTION_DENIED"
    assert spy.call_count == 0
    # Policy diagnostics are preserved internally for logs/events...
    assert result.error.details["rule_id"] == decision["rule_id"]
    assert result.error.details["reason_code"] == decision["reason_code"]
    # ...but must not widen the Agent-UI failedResponse.error wire contract.
    assert set(result.error.to_dict()) == {"code", "message", "retryable"}


def test_gateway_replay_attack_second_execution_fails():
    spy = ActuatorSpy()
    registry = HandlerRegistry()
    registry.register("open_door", spy)

    gateway = VehicleToolGateway(registry=registry)
    proposal = make_proposal()
    decision = make_decision(proposal)
    now = datetime.fromisoformat("2026-08-04T12:01:00+00:00")

    # First execution -> succeeds
    res1 = gateway.execute(proposal, decision, current_time=now)
    assert res1.success is True
    assert spy.call_count == 1

    # Second execution with same permit -> fails with PERMIT_REPLAYED, 0 additional calls
    res2 = gateway.execute(proposal, decision, current_time=now)
    assert res2.success is False
    assert res2.error is not None
    assert res2.error.code == "PERMIT_REPLAYED"
    assert spy.call_count == 1  # Handler was NOT called a second time


def test_gateway_substitution_attack_fails_zero_handler_calls():
    spy = ActuatorSpy()
    registry = HandlerRegistry()
    registry.register("open_door", spy)

    gateway = VehicleToolGateway(registry=registry)
    proposal = make_proposal(arguments={"door": "driver_door"})
    decision = make_decision(proposal)

    # Attacker tries to execute modified proposal using original decision permit
    tampered_proposal = make_proposal(arguments={"door": "all_doors"})

    now = datetime.fromisoformat("2026-08-04T12:01:00+00:00")
    result = gateway.execute(tampered_proposal, decision, current_time=now)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "PROPOSAL_MISMATCH"
    assert spy.call_count == 0


def test_gateway_expired_permit_zero_handler_calls():
    spy = ActuatorSpy()
    registry = HandlerRegistry()
    registry.register("open_door", spy)

    gateway = VehicleToolGateway(registry=registry)
    proposal = make_proposal()
    decision = make_decision(proposal)

    # Current time after expiration
    now = datetime.fromisoformat("2026-08-04T12:10:00+00:00")
    result = gateway.execute(proposal, decision, current_time=now)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "PERMIT_EXPIRED"
    assert spy.call_count == 0


def test_gateway_missing_handler_fails_after_permit_check():
    registry = HandlerRegistry()  # Empty registry
    gateway = VehicleToolGateway(registry=registry)
    proposal = make_proposal()
    decision = make_decision(proposal)

    now = datetime.fromisoformat("2026-08-04T12:01:00+00:00")
    result = gateway.execute(proposal, decision, current_time=now)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "HANDLER_NOT_FOUND"


def test_gateway_non_mapping_handler_output_fails():
    spy = ActuatorSpy(return_value="unexpected_string_output")
    registry = HandlerRegistry()
    registry.register("open_door", spy)

    gateway = VehicleToolGateway(registry=registry)
    proposal = make_proposal()
    decision = make_decision(proposal)

    now = datetime.fromisoformat("2026-08-04T12:01:00+00:00")
    result = gateway.execute(proposal, decision, current_time=now)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "INVALID_HANDLER_OUTPUT"


def test_gateway_structured_execution_error_propagated():
    def custom_failing_handler(prop: Mapping[str, Any]) -> dict[str, Any]:
        raise GatewayExecutionError("Door mechanical jam detected", code="HARDWARE_JAM", retryable=True)

    registry = HandlerRegistry()
    registry.register("open_door", custom_failing_handler)

    gateway = VehicleToolGateway(registry=registry)
    proposal = make_proposal()
    decision = make_decision(proposal)

    now = datetime.fromisoformat("2026-08-04T12:01:00+00:00")
    result = gateway.execute(proposal, decision, current_time=now)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "HARDWARE_JAM"
    assert result.error.message == "Door mechanical jam detected"
    assert result.error.retryable is True


def test_gateway_handler_generic_exception_wrapped():
    def failing_handler(prop: Mapping[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Hardware actuator communication failure")

    registry = HandlerRegistry()
    registry.register("open_door", failing_handler)

    gateway = VehicleToolGateway(registry=registry)
    proposal = make_proposal()
    decision = make_decision(proposal)

    now = datetime.fromisoformat("2026-08-04T12:01:00+00:00")
    result = gateway.execute(proposal, decision, current_time=now)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "EXECUTION_FAILED"
    assert "Hardware actuator communication failure" in result.error.message


def test_concurrent_permit_consumption_thread_safety():
    spy = ActuatorSpy()
    registry = HandlerRegistry()
    registry.register("open_door", spy)

    gateway = VehicleToolGateway(registry=registry)
    proposal = make_proposal()
    decision = make_decision(proposal)
    now = datetime.fromisoformat("2026-08-04T12:01:00+00:00")

    results = []

    def worker():
        return gateway.execute(proposal, decision, current_time=now)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker) for _ in range(10)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]

    # Exactly 1 thread succeeds; all other 9 fail due to PERMIT_REPLAYED
    assert len(successes) == 1
    assert len(failures) == 9
    assert spy.call_count == 1
