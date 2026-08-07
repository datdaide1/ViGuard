from __future__ import annotations

import ast
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from vivi_agent.catalog import load_manifest
from vivi_agent.contracts.guardrail.v1.contract import CONTRACT_VERSION, proposal_digest
from vivi_agent.model_providers import (
    ModelActionProposal,
    ModelErrorCode,
    ModelProviderError,
    ProviderMetadata,
)
from vivi_agent.orchestrator import (
    AgentOrchestrator,
    CancellationToken,
    ExecutionResult,
    MessageEndpoint,
    TurnError,
    TurnRequest,
    TurnState,
    TurnStatus,
)
from vivi_agent.tools.mapping import load_default_mapper
from vivi_agent.tools.registry import load_registry


META = ProviderMetadata("openai", "test-model", "sha256:test", 1)
REQUEST = TurnRequest("session-1", "turn-1", "request-1", "Mở cửa ghế lái")


class FakeRouter:
    def __init__(self, proposal=None, error=None):
        self.proposal = proposal or ModelActionProposal.action(
            "control_access", {"action": "open", "target": "driver_door"}, META
        )
        self.error = error
        self.calls = 0

    def propose_tool(self, messages, turn):
        self.calls += 1
        if self.error:
            raise self.error
        turn.record_proposal(self.proposal)
        return self.proposal

    def compose_response(self, facts, turn):
        assert set(facts) <= {"outcome", "facts", "state_version"}
        return ModelActionProposal.response("Pin còn 42 phần trăm.", META)


class FakeGuardrail:
    def __init__(self, outcome="ALLOW", failure=None):
        self.outcome = outcome
        self.failure = failure
        self.calls = 0

    def evaluate(self, proposal):
        self.calls += 1
        if self.failure:
            raise self.failure
        decision = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": "guardrail-request-1",
            "proposal_id": proposal["proposal_id"],
            "intent": "open_door",
            "outcome": self.outcome,
            "rule_id": "R001",
            "state_version": 12,
            "policy_checksum": "sha256:" + "a" * 64,
            "reason_code": "POLICY_CONDITION_MATCHED",
            "relevant_state": {"speed": 0},
        }
        if self.outcome == "ALLOW":
            decision["permit"] = {
                "permit_id": "permit-1",
                "proposal_digest": proposal_digest(proposal),
                "intent": "open_door",
                "rule_id": "R001",
                "state_version": 12,
                "policy_checksum": "sha256:" + "a" * 64,
                "issued_at": "2026-08-04T00:00:00Z",
                "expires_at": "2026-08-04T00:00:02Z",
                "single_use": True,
            }
        elif self.outcome == "CONFIRM":
            decision["confirmation"] = {
                "confirmation_id": "confirmation-1",
                "proposal_id": proposal["proposal_id"],
                "expires_at": "2026-08-04T00:00:30Z",
                "single_use": True,
            }
        elif self.outcome == "ANSWER":
            decision["answer"] = {"grounded": True, "facts": {"battery_pct": 42}}
        return decision


class FakeExecutor:
    def __init__(self, result=None):
        self.result = result or ExecutionResult(
            True, "execution-1", "Đã mở cửa ghế lái.", 13, {"driver_door": "open"}
        )
        self.calls = 0

    def execute(self, proposal, decision, cancellation):
        self.calls += 1
        assert decision["outcome"] == "ALLOW"
        assert not cancellation.cancelled
        return self.result


class ConcurrentExecutor(FakeExecutor):
    def __init__(self):
        super().__init__()
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def execute(self, proposal, decision, cancellation):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.03)
        with self._lock:
            self.active -= 1
        return self.result


def make_orchestrator(router=None, guardrail=None, executor=None):
    return AgentOrchestrator(
        model_router=router or FakeRouter(),
        mapper=load_default_mapper(load_registry(), load_manifest()),
        guardrail=guardrail or FakeGuardrail(),
        executor=executor or FakeExecutor(),
        id_factory=lambda prefix: f"{prefix}-1",
    )


def test_success_is_reported_only_after_execution_result():
    executor = FakeExecutor()
    result = make_orchestrator(executor=executor).handle_message(REQUEST)

    assert executor.calls == 1
    assert result.status is TurnStatus.COMPLETED
    assert result.message == "Đã mở cửa ghế lái."
    assert result.execution_id == "execution-1"
    assert result.trace[-2:] == (TurnState.EXECUTING, TurnState.COMPLETED)


def test_execution_failure_never_reports_success():
    executor = FakeExecutor(
        ExecutionResult(
            False,
            "execution-1",
            "ignored",
            error=TurnError("VEHICLE_GATEWAY_ERROR", "gateway unavailable", True),
        )
    )
    result = make_orchestrator(executor=executor).handle_message(REQUEST)

    assert result.status is TurnStatus.FAILED
    assert result.error.code == "VEHICLE_GATEWAY_ERROR"
    assert "Đã" not in result.message


def test_guardrail_failure_fails_closed_without_execution():
    guardrail = FakeGuardrail(failure=TimeoutError("offline"))
    executor = FakeExecutor()
    result = make_orchestrator(guardrail=guardrail, executor=executor).handle_message(REQUEST)

    assert result.status is TurnStatus.FAILED
    assert result.error.code == "ORCHESTRATION_DEPENDENCY_ERROR"
    assert executor.calls == 0


def test_guardrail_intent_mismatch_fails_closed_without_execution():
    class WrongIntentGuardrail(FakeGuardrail):
        def evaluate(self, proposal):
            decision = super().evaluate(proposal)
            decision["intent"] = "close_door"
            decision["permit"]["intent"] = "close_door"
            return decision

    executor = FakeExecutor()
    result = make_orchestrator(
        guardrail=WrongIntentGuardrail(), executor=executor
    ).handle_message(REQUEST)

    assert result.status is TurnStatus.FAILED
    assert result.error.code == "DECISION_INTENT_MISMATCH"
    assert executor.calls == 0


def test_block_and_confirmation_do_not_execute():
    for outcome, expected in (
        ("BLOCK_UNSAFE", TurnStatus.BLOCKED),
        ("CONFIRM", TurnStatus.NEEDS_CONFIRMATION),
    ):
        executor = FakeExecutor()
        result = make_orchestrator(
            guardrail=FakeGuardrail(outcome), executor=executor
        ).handle_message(REQUEST)
        assert result.status is expected
        assert executor.calls == 0


def test_malformed_confirmation_fails_closed():
    class MalformedConfirmationGuardrail(FakeGuardrail):
        def evaluate(self, proposal):
            decision = super().evaluate(proposal)
            decision["confirmation"]["confirmation_id"] = None
            return decision

    result = make_orchestrator(
        guardrail=MalformedConfirmationGuardrail("CONFIRM")
    ).handle_message(REQUEST)

    assert result.status is TurnStatus.FAILED
    assert result.error.code == "MALFORMED_GUARDRAIL_RESPONSE"


def test_clarification_never_reaches_guardrail():
    router = FakeRouter(ModelActionProposal.clarification("Bạn muốn mở cửa nào?", META))
    guardrail = FakeGuardrail()
    result = make_orchestrator(router=router, guardrail=guardrail).handle_message(REQUEST)

    assert result.state is TurnState.CLARIFICATION
    assert result.message == "Bạn muốn mở cửa nào?"
    assert guardrail.calls == 0


def test_model_failure_is_typed_degraded_response():
    router = FakeRouter(
        error=ModelProviderError(ModelErrorCode.TIMEOUT, "timeout", retryable=True)
    )
    executor = FakeExecutor()
    result = make_orchestrator(router=router, executor=executor).handle_message(REQUEST)

    assert result.status is TurnStatus.DEGRADED
    assert result.reason == ModelErrorCode.TIMEOUT.value
    assert result.retryable is True
    assert executor.calls == 0


def test_pre_cancelled_turn_has_zero_side_effects():
    token = CancellationToken()
    token.cancel()
    router, guardrail, executor = FakeRouter(), FakeGuardrail(), FakeExecutor()
    result = make_orchestrator(router, guardrail, executor).handle_message(REQUEST, token)

    assert result.state is TurnState.FAILED
    assert result.error.code == "TURN_CANCELLED"
    assert router.calls == guardrail.calls == executor.calls == 0


def test_state_changing_turns_for_one_session_do_not_execute_in_parallel():
    executor = ConcurrentExecutor()
    orchestrator = make_orchestrator(executor=executor)
    requests = (
        TurnRequest("session-1", "turn-1", "request-1", "Mở cửa ghế lái"),
        TurnRequest("session-1", "turn-2", "request-2", "Mở cửa ghế lái"),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(orchestrator.handle_message, requests))

    assert all(result.status is TurnStatus.COMPLETED for result in results)
    assert executor.max_active == 1


def test_state_changing_turns_for_different_sessions_can_execute_in_parallel():
    executor = ConcurrentExecutor()
    orchestrator = make_orchestrator(executor=executor)
    requests = (
        TurnRequest("session-1", "turn-1", "request-1", "Mở cửa ghế lái"),
        TurnRequest("session-2", "turn-2", "request-2", "Mở cửa ghế lái"),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(orchestrator.handle_message, requests))

    assert all(result.status is TurnStatus.COMPLETED for result in results)
    assert executor.max_active == 2


def test_answer_composer_receives_only_typed_grounded_facts():
    result = make_orchestrator(guardrail=FakeGuardrail("ANSWER")).handle_message(REQUEST)
    assert result.status is TurnStatus.COMPLETED
    assert result.message == "Pin còn 42 phần trăm."


def test_message_endpoint_returns_contract_valid_payload():
    endpoint = MessageEndpoint(
        make_orchestrator(),
        clock=lambda: datetime(2026, 8, 4, tzinfo=timezone.utc),
    )
    response = endpoint.post_message(
        {
            "contract_version": "1.0.0",
            "kind": "request",
            "request_type": "message",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "request_id": "request-1",
            "occurred_at": "2026-08-04T00:00:00Z",
            "message": "Mở cửa ghế lái",
        }
    )
    assert response["status"] == "completed"
    assert response["execution_id"] == "execution-1"


def test_execution_result_to_dict_is_json_serializable():
    """Without to_dict(), a plain dict(ExecutionResult(...)) raises TypeError
    (frozen dataclass, not iterable) and dataclasses.asdict() raises on the
    MappingProxyType `facts` field — see confirmation/manager.py's
    _execution_result_to_dict for the consumer this originally broke."""
    import json

    result = ExecutionResult(
        success=False,
        execution_id="exec-1",
        message="denied",
        state_version=3,
        facts={"intent": "open_window"},
        error=TurnError(code="EXECUTION_DENIED", message="denied", retryable=False),
    )

    as_dict = result.to_dict()

    assert as_dict == {
        "success": False,
        "execution_id": "exec-1",
        "message": "denied",
        "state_version": 3,
        "facts": {"intent": "open_window"},
        "error": {"code": "EXECUTION_DENIED", "message": "denied", "retryable": False},
    }
    json.dumps(as_dict)  # must not raise


def test_execution_result_to_dict_success_has_no_error():
    result = ExecutionResult(success=True, execution_id="exec-2", message="ok")
    assert result.to_dict()["error"] is None


def test_orchestrator_has_no_action_handler_registry_reference():
    root = Path(__file__).parents[2] / "src" / "vivi_agent" / "orchestrator"
    for source_path in root.glob("*.py"):
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        assert all("handler" not in name.lower() and "registry" not in name.lower() for name in imported)
        assert "ActionHandlerRegistry" not in source
