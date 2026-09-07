"""Fixtures and test environment setup for E2E-01 vertical slice: open_door."""

from __future__ import annotations

from typing import Any, Callable, Mapping
from dataclasses import dataclass, field

from vehicle_agent.contracts.guardrail.v1.contract import CONTRACT_VERSION, proposal_digest
from vehicle_agent.model_providers import (
    ModelActionProposal,
    ProviderMetadata,
    TurnBinding,
)
from vehicle_agent.vehicle.state import (
    Gear,
    VehicleStateMachine,
    DoorPosition,
    LockState,
)
from vehicle_agent.vehicle.execution import (
    VehicleToolGateway,
    make_open_door_handler,
)
from vehicle_agent.events import AgentEventPipeline, AgentEventStore
from vehicle_agent.tools.mapping import load_default_mapper
from vehicle_agent.orchestrator import ExecutionResult, CancellationToken


META = ProviderMetadata(
    provider="openai",
    model_id="gpt-4o",
    config_checksum="sha256:e2e-test",
    latency_ms=10,
)


class ActuatorSpy:
    """Actuator spy wrapper asserting exact call counts and execution details."""

    def __init__(self, target_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.target_handler = target_handler
        self.call_count: int = 0
        self.calls: list[dict[str, Any]] = []

    def __call__(self, proposal: dict[str, Any]) -> dict[str, Any]:
        self.call_count += 1
        self.calls.append(proposal)
        if self.target_handler:
            return self.target_handler(proposal)
        return {
            "state_version": 1,
            "facts": {"target_door": proposal.get("arguments", {}).get("door", "driver_door"), "position": "open"},
            "message": "Đã mở cửa ghế lái.",
        }


class SpyExecutor:
    """ActionExecutor wrapper for Orchestrator that proxies to VehicleToolGateway and tracks execution calls."""

    def __init__(self, gateway: VehicleToolGateway) -> None:
        self.gateway = gateway
        self.call_count: int = 0
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def execute(
        self,
        proposal: Mapping[str, Any],
        decision: Mapping[str, Any],
        cancellation: CancellationToken,
    ) -> ExecutionResult:
        self.call_count += 1
        self.calls.append((dict(proposal), dict(decision)))
        return self.gateway.execute(proposal, decision, cancellation)


class E2EMockModelRouter:
    """Mock model provider router for E2E tests."""

    def __init__(self, proposal: ModelActionProposal | None = None) -> None:
        self.proposal = proposal or ModelActionProposal.action(
            "control_access", {"action": "open", "target": "driver_door"}, META
        )
        self.calls: int = 0

    def propose_tool(self, messages: Any, turn: TurnBinding) -> ModelActionProposal:
        self.calls += 1
        turn.record_proposal(self.proposal)
        return self.proposal

    def compose_response(self, facts: Any, turn: TurnBinding) -> ModelActionProposal:
        return ModelActionProposal.response("Đã mở cửa xe.", META)


class E2EMockGuardrailClient:
    """Mock Guardrail authorization port configurable for ALLOW, BLOCK, or custom responses."""

    def __init__(
        self,
        outcome: str = "ALLOW",
        rule_id: str = "R_OPEN_DOOR_SAFE",
        reason_code: str = "SAFE_PARKED_STATE",
        custom_response: dict[str, Any] | None = None,
        permit_override: dict[str, Any] | None = None,
        state_machine: VehicleStateMachine | None = None,
    ) -> None:
        self.outcome = outcome
        self.rule_id = rule_id
        self.reason_code = reason_code
        self.custom_response = custom_response
        self.permit_override = permit_override
        self.state_machine = state_machine
        self.calls: int = 0
        self.last_proposal: dict[str, Any] | None = None

    def evaluate(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        self.calls += 1
        self.last_proposal = dict(proposal)
        if self.custom_response is not None:
            return self.custom_response

        digest = proposal_digest(proposal)
        state_ver = 1
        relevant_state: dict[str, Any] = {"speed": 0, "gear": "P"}
        if self.state_machine is not None:
            snap = self.state_machine.snapshot()
            state_ver = snap.state_version
            relevant_state = {
                "speed": snap.motion.speed_kph,
                "gear": snap.transmission.gear.value,
            }

        response: dict[str, Any] = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": f"req-grd-{self.calls}",
            "proposal_id": proposal["proposal_id"],
            "intent": "open_door",
            "outcome": self.outcome,
            "rule_id": self.rule_id,
            "state_version": state_ver,
            "policy_checksum": "sha256:" + "a" * 64,
            "reason_code": self.reason_code,
            "relevant_state": relevant_state,
        }

        if self.outcome == "ALLOW":
            if self.permit_override is not None:
                response["permit"] = self.permit_override
            else:
                response["permit"] = {
                    "permit_id": f"permit-e2e-{self.calls}",
                    "proposal_digest": digest,
                    "intent": "open_door",
                    "rule_id": self.rule_id,
                    "state_version": state_ver,
                    "policy_checksum": "sha256:" + "a" * 64,
                    "issued_at": "2026-08-04T00:00:00Z",
                    "expires_at": "2099-01-01T00:00:00Z",
                    "single_use": True,
                }
        return response


@dataclass
class E2ETestEnvironment:
    """Bundles all components of the vertical slice runtime for testing."""

    state_machine: VehicleStateMachine
    spy_actuator: ActuatorSpy
    gateway: VehicleToolGateway
    spy_executor: SpyExecutor
    guardrail: E2EMockGuardrailClient
    model_router: E2EMockModelRouter
    event_store: AgentEventStore
    event_pipeline: AgentEventPipeline

    def reset(self) -> None:
        """Reset state machine and event store to baseline via public API."""
        self.state_machine.reset("parked_powered_off")
        self.event_store.clear()
        self.spy_actuator.call_count = 0
        self.spy_actuator.calls.clear()
        self.spy_executor.call_count = 0
        self.spy_executor.calls.clear()
        self.guardrail.calls = 0
        self.model_router.calls = 0


def create_e2e_environment(
    speed: float = 0.0,
    gear: Gear = Gear.PARK,
    guardrail_outcome: str = "ALLOW",
    guardrail_rule_id: str = "R_OPEN_DOOR_SAFE",
    guardrail_reason_code: str = "SAFE_PARKED_STATE",
    guardrail_custom_response: dict[str, Any] | None = None,
) -> E2ETestEnvironment:
    """Factory creating a fully wired E2E test environment for open_door."""

    from dataclasses import replace
    from vehicle_agent.vehicle.state import ActorKind, MotionPhase

    state_machine = VehicleStateMachine()
    if speed != 0.0 or gear != Gear.PARK:
        state_machine.apply(
            lambda s: replace(
                s,
                motion=replace(
                    s.motion,
                    speed_kph=speed,
                    phase=MotionPhase.MOVING if speed > 0 else MotionPhase.STOPPED,
                ),
                transmission=replace(s.transmission, gear=gear),
            ),
            actor_kind=ActorKind.SYSTEM,
            actor_id="test-setup",
            correlation_id="setup-1",
        )

    raw_handler = make_open_door_handler(state_machine)
    spy_actuator = ActuatorSpy(target_handler=raw_handler)

    gateway = VehicleToolGateway()
    gateway.registry.register("open_door", spy_actuator)
    gateway.registry.register("control_access", spy_actuator)

    spy_executor = SpyExecutor(gateway)
    guardrail = E2EMockGuardrailClient(
        outcome=guardrail_outcome,
        rule_id=guardrail_rule_id,
        reason_code=guardrail_reason_code,
        custom_response=guardrail_custom_response,
        state_machine=state_machine,
    )
    model_router = E2EMockModelRouter()
    event_store = AgentEventStore()
    event_pipeline = AgentEventPipeline(store=event_store)

    return E2ETestEnvironment(
        state_machine=state_machine,
        spy_actuator=spy_actuator,
        gateway=gateway,
        spy_executor=spy_executor,
        guardrail=guardrail,
        model_router=model_router,
        event_store=event_store,
        event_pipeline=event_pipeline,
    )
