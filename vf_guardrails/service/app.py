"""Transport-free request core for the Guardrail HTTP service.

``GuardrailService.handle(path, payload) -> (status, body)`` is the whole
contract surface; ``http.py`` is a thin stdlib ``http.server`` shell over it and
tests drive this class directly.

Routes:
  POST /v1/evaluate/action        action authorization (2'.1)
  POST /v1/evaluate/query         read-only query (2'.1 minimal; P2-D3 in 2'.2)
  POST /v1/confirmations/confirm  resolve a CONFIRM against fresh state (2'.2)
  POST /v1/monitor/evaluate       monitor a running action (2'.3)
"""
from __future__ import annotations

from typing import Any

from policy import Decision, PolicyEngine, RuleSet, VehicleState

from .active_actions import MONITORED_INTENTS, ActiveActionRegistry
from .confirmations import ConfirmationSessionMismatch, PendingConfirmationStore
from .envelope import (
    CONTRACT_VERSION,
    WireError,
    confirmation_block,
    decision_envelope,
    error_envelope,
    monitor_decision_envelope,
    monitor_request_digest,
    require_contract_version,
    validate_action_proposal,
)
from .state_store import VehicleStateStore, validate_wire_vehicle_state
from .tool_map import DEFAULT_MAPPER, EXPLAIN_INTENTS, QUERY_INTENTS, ToolMapper, ToolMappingError

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
        confirmations: PendingConfirmationStore | None = None,
        active_actions: ActiveActionRegistry | None = None,
    ) -> None:
        self.store = store or VehicleStateStore()
        self.engine = engine or PolicyEngine(RuleSet.load())
        self.mapper = mapper or DEFAULT_MAPPER
        self.confirmations = confirmations or PendingConfirmationStore()
        self.active_actions = active_actions or ActiveActionRegistry()

    def _evaluate(self, intent: str, state: VehicleState, *, check_mode: str) -> Decision:
        """``PolicyEngine.evaluate`` with a belt-and-braces fail-closed guard.

        The engine already fails closed for every *known* failure mode; this
        only stops an unforeseen exception (e.g. a still-untyped value slipping
        into a rule comparison) from escaping as a bare 500 / transport failure.
        """

        try:
            return self.engine.evaluate(intent, state, check_mode=check_mode)
        except Exception as exc:  # noqa: BLE001 - deliberately fail closed on anything
            return Decision(
                intent=intent, check_mode=check_mode, outcome=None, rule_id=None,
                reason_code="ENGINE_EVAL_ERROR", error=f"{type(exc).__name__}: {exc}",
            )

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
        if path == _CONFIRM_ROUTE:
            return self._confirm(payload, request_id)
        if path == _MONITOR_ROUTE:
            return self._monitor(payload, request_id)
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
        decision = self._evaluate(intent, state, check_mode="gate")

        if decision.is_fail_closed:
            return _FAIL_CLOSED_STATUS, error_envelope(
                proposal_id, decision.reason_code, decision.error or "policy fail-closed"
            )

        if decision.outcome == "CONFIRM":
            record = self.confirmations.create(proposal, decision.intent, decision.rule_id or "")
            body = decision_envelope(
                request_id=None,
                proposal=proposal,
                intent=decision.intent,
                outcome="CONFIRM",
                rule_id=decision.rule_id or "R000",
                state_version=state_version,
                policy_checksum=self.engine.policy_checksum,
                reason_code=decision.reason_code,
                relevant_state=decision.relevant_state,
                confirmation=confirmation_block(
                    record.confirmation_id, proposal["proposal_id"], record.expires_at.isoformat()
                ),
            )
            return 200, body

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

        if decision.outcome == "ALLOW" and decision.intent in MONITORED_INTENTS:
            self.active_actions.register(proposal["proposal_id"], decision.intent)
        return 200, body

    # ------------------------------------------------------------------ confirm
    def _confirm(self, payload: dict[str, Any], request_id: str) -> tuple[int, dict[str, Any]]:
        confirmation_id = _as_id(payload.get("confirmation_id"))
        session_id = _as_id(payload.get("session_id"))
        if not confirmation_id or not session_id or not _as_id(payload.get("request_id")):
            return 400, error_envelope(
                request_id, "INVALID_CONFIRMATION",
                "confirm requires request_id, confirmation_id and session_id",
            )

        try:
            record = self.confirmations.consume(confirmation_id, session_id=session_id)
        except ConfirmationSessionMismatch:
            # Live token, wrong session: reject without consuming so the
            # originating session can still confirm.
            return 403, error_envelope(
                request_id, "CONFIRMATION_SESSION_MISMATCH",
                "Confirmation belongs to a different session",
            )
        if record is None:
            return 409, error_envelope(
                request_id, "CONFIRMATION_NOT_ACTIVE",
                "Confirmation is unknown, expired, or already consumed",
            )

        # PRD 8.4: re-evaluate against a FRESH state snapshot; a stale confirm
        # must never carry the original permit forward.
        state, state_version = self.store.snapshot()
        decision = self._evaluate(record.intent, state, check_mode="gate")

        if decision.is_fail_closed:
            return _FAIL_CLOSED_STATUS, error_envelope(
                request_id, decision.reason_code, decision.error or "policy fail-closed"
            )

        same_rule_confirm = (
            decision.outcome == "CONFIRM" and (decision.rule_id or "") == record.origin_rule_id
        )
        if decision.outcome == "ALLOW" or same_rule_confirm:
            # The driver has confirmed and conditions still permit -> one permit.
            body = decision_envelope(
                request_id=request_id,
                proposal=record.proposal,
                intent=record.intent,
                outcome="ALLOW",
                rule_id=decision.rule_id or record.origin_rule_id or "R000",
                state_version=state_version,
                policy_checksum=self.engine.policy_checksum,
                reason_code="CONFIRMATION_REEVALUATED_ALLOW",
                relevant_state=decision.relevant_state,
            )
            if record.intent in MONITORED_INTENTS:
                self.active_actions.register(record.proposal["proposal_id"], record.intent)
            return 200, body

        if decision.outcome == "CONFIRM":
            # A *different* confirmation rule now applies -> a new pending token.
            fresh = self.confirmations.create(record.proposal, record.intent, decision.rule_id or "")
            body = decision_envelope(
                request_id=request_id,
                proposal=record.proposal,
                intent=record.intent,
                outcome="CONFIRM",
                rule_id=decision.rule_id or "R000",
                state_version=state_version,
                policy_checksum=self.engine.policy_checksum,
                reason_code=decision.reason_code,
                relevant_state=decision.relevant_state,
                confirmation=confirmation_block(
                    fresh.confirmation_id,
                    record.proposal["proposal_id"],
                    fresh.expires_at.isoformat(),
                ),
            )
            return 200, body

        # State turned worse between CONFIRM and confirm -> block, no permit.
        body = decision_envelope(
            request_id=request_id,
            proposal=record.proposal,
            intent=record.intent,
            outcome=decision.outcome,
            rule_id=decision.rule_id or "",
            state_version=state_version,
            policy_checksum=self.engine.policy_checksum,
            reason_code=decision.reason_code,
            relevant_state=decision.relevant_state,
        )
        return 200, body

    # ------------------------------------------------------------------ monitor
    def _monitor(self, payload: dict[str, Any], request_id: str) -> tuple[int, dict[str, Any]]:
        active_action_id = _as_id(payload.get("active_action_id"))
        intent = _as_id(payload.get("intent"))
        if not active_action_id or not intent or not _as_id(payload.get("request_id")):
            return 400, error_envelope(
                request_id, "INVALID_MONITOR_REQUEST",
                "monitor requires request_id, active_action_id and intent",
            )

        vehicle_state = payload.get("vehicle_state")
        if vehicle_state is not None:
            if not isinstance(vehicle_state, dict):
                return 400, error_envelope(
                    request_id, "INVALID_VEHICLE_STATE", "vehicle_state must be an object"
                )
            try:
                state = validate_wire_vehicle_state(vehicle_state)
            except ValueError as exc:
                return 400, error_envelope(request_id, "INVALID_VEHICLE_STATE", str(exc))
            state_version = -1  # agent-supplied snapshot: no Guardrail version
        else:
            state, state_version = self.store.snapshot()

        decision = self._evaluate(intent, state, check_mode="monitor")
        digest = monitor_request_digest(payload)

        if decision.is_fail_closed:
            code = (
                "NOT_A_MONITORED_INTENT"
                if decision.reason_code in ("NO_RULE_FOR_PHASE", "INTENT_NOT_IN_CATALOG")
                else decision.reason_code
            )
            return _FAIL_CLOSED_STATUS, error_envelope(
                request_id, code, decision.error or "monitor fail-closed"
            )

        # NO_MONITOR_TRIGGER (outcome None) or an explicit monitor ALLOW -> keep running
        continue_running = decision.outcome in (None, "ALLOW")
        outcome = "ALLOW" if continue_running else decision.outcome
        rule_id = decision.rule_id or ("MONITOR_NO_TRIGGER" if continue_running else "MONITOR_RULE")

        if not continue_running:
            self.active_actions.deregister(active_action_id)

        body = monitor_decision_envelope(
            request_id=request_id,
            active_action_id=active_action_id,
            intent=intent,
            outcome=outcome,
            rule_id=rule_id,
            state_version=state_version if state_version >= 0 else 0,
            policy_checksum=self.engine.policy_checksum,
            reason_code=decision.reason_code,
            relevant_state=decision.relevant_state,
            digest=digest,
        )
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
        decision = self._evaluate(intent, state, check_mode="gate")
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
