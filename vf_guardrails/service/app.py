"""Transport-free request core for the Guardrail HTTP service.

``GuardrailService.handle(path, payload) -> (status, body)`` is the whole
contract surface; ``http.py`` is a thin stdlib ``http.server`` shell over it and
tests drive this class directly.

2'.1 implements the action path end to end and a minimal query path. CONFIRM
lifecycle (2'.2) and the monitor path (2'.3) return typed "not yet" errors so
nothing half-works silently.
"""
from __future__ import annotations

from typing import Any

from policy import PolicyEngine, RuleSet

from .envelope import (
    CONTRACT_VERSION,
    WireError,
    decision_envelope,
    error_envelope,
    require_contract_version,
    validate_action_proposal,
)
from .state_store import VehicleStateStore
from .tool_map import DEFAULT_MAPPER, EXPLAIN_INTENTS, QUERY_INTENTS, ToolMapper, ToolMappingError

# engine fail-closed reason -> HTTP status for the typed error envelope
_FAIL_CLOSED_STATUS = 422
_ACTION_ROUTE = "/v1/evaluate/action"
_QUERY_ROUTE = "/v1/evaluate/query"
_CONFIRM_ROUTE = "/v1/confirmations/confirm"
_MONITOR_ROUTE = "/v1/monitor/evaluate"


class GuardrailService:
    def __init__(
        self,
        *,
        store: VehicleStateStore | None = None,
        engine: PolicyEngine | None = None,
        mapper: ToolMapper | None = None,
    ) -> None:
        self.store = store or VehicleStateStore()
        self.engine = engine or PolicyEngine(RuleSet.load())
        self.mapper = mapper or DEFAULT_MAPPER

    # ------------------------------------------------------------------ routing
    def handle(self, path: str, payload: Any) -> tuple[int, dict[str, Any]]:
        if not isinstance(payload, dict):
            return 400, error_envelope("unknown", "INVALID_JSON", "request body must be a JSON object")
        request_id = _as_id(payload.get("request_id")) or _as_id(payload.get("proposal_id")) or "unknown"
        try:
            require_contract_version(payload)
        except WireError as exc:
            return 409, error_envelope(request_id, exc.code, str(exc))

        if path == _ACTION_ROUTE:
            return self._evaluate_action(payload)
        if path == _QUERY_ROUTE:
            return self._evaluate_query(payload, request_id)
        if path in (_CONFIRM_ROUTE, _MONITOR_ROUTE):
            return 501, error_envelope(
                request_id,
                "NOT_YET_IMPLEMENTED",
                f"{path} arrives in a later Phase 2' increment",
            )
        return 404, error_envelope(request_id, "ROUTE_NOT_FOUND", path)

    # ------------------------------------------------------------------ action
    def _evaluate_action(self, proposal: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        proposal_id = _as_id(proposal.get("proposal_id")) or "unknown"
        try:
            validate_action_proposal(proposal)
        except WireError as exc:
            status = 409 if exc.code == "CONTRACT_VERSION_MISMATCH" else 400
            return status, error_envelope(proposal_id, exc.code, str(exc))

        try:
            intent = self.mapper.resolve(proposal["tool"], proposal["arguments"])
        except ToolMappingError as exc:
            return _FAIL_CLOSED_STATUS, error_envelope(proposal_id, exc.code, str(exc))

        state, state_version = self.store.snapshot()
        decision = self.engine.evaluate(intent, state, check_mode="gate")

        if decision.is_fail_closed:
            return _FAIL_CLOSED_STATUS, error_envelope(
                proposal_id, decision.reason_code, decision.error or "policy fail-closed"
            )
        if decision.outcome == "CONFIRM":
            return 501, error_envelope(
                proposal_id,
                "CONFIRM_NOT_YET_IMPLEMENTED",
                "CONFIRM lifecycle arrives in increment 2'.2",
            )

        try:
            body = decision_envelope(
                request_id=None,
                proposal=proposal,
                intent=decision.intent,
                outcome=decision.outcome,
                rule_id=decision.rule_id or "",
                state_version=state_version,
                policy_checksum=self.engine.policy_checksum,
                reason_code=decision.reason_code,
                relevant_state=decision.relevant_state,
            )
        except WireError as exc:
            return _FAIL_CLOSED_STATUS, error_envelope(proposal_id, exc.code, str(exc))
        return 200, body

    # ------------------------------------------------------------------ query
    def _evaluate_query(self, payload: dict[str, Any], request_id: str) -> tuple[int, dict[str, Any]]:
        """Minimal query path (2'.1). Full ANSWER fact-shaping lands in 2'.2 (P2-D3)."""

        tool = payload.get("tool")
        arguments = payload.get("arguments")
        if not isinstance(tool, str) or not isinstance(arguments, dict):
            return 400, error_envelope(
                request_id, "INVALID_QUERY", "query requires 'tool' and 'arguments'"
            )
        try:
            intent = self.mapper.resolve(tool, arguments)
        except ToolMappingError as exc:
            return _FAIL_CLOSED_STATUS, error_envelope(request_id, exc.code, str(exc))
        if intent not in QUERY_INTENTS | EXPLAIN_INTENTS:
            return _FAIL_CLOSED_STATUS, error_envelope(
                request_id, "NOT_A_QUERY_INTENT", f"{intent!r} is not a read-only query"
            )

        state, state_version = self.store.snapshot()
        decision = self.engine.evaluate(intent, state, check_mode="gate")
        if decision.is_fail_closed:
            return _FAIL_CLOSED_STATUS, error_envelope(
                request_id, decision.reason_code, decision.error or "policy fail-closed"
            )
        body = {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": request_id if request_id != "unknown" else "req-query",
            "proposal_id": _as_id(payload.get("proposal_id")) or "query",
            "intent": decision.intent,
            "outcome": decision.outcome,
            "rule_id": decision.rule_id or "",
            "state_version": state_version,
            "policy_checksum": self.engine.policy_checksum,
            "reason_code": decision.reason_code.split(" ", 1)[0],
            "relevant_state": decision.relevant_state,
        }
        if decision.outcome == "ANSWER":
            body["answer"] = {"grounded": True, "facts": dict(decision.relevant_state)}
        return 200, body


def _as_id(value: Any) -> str | None:
    return value if isinstance(value, str) and 1 <= len(value) <= 128 else None
