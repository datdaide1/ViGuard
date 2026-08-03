"""Fail-closed semantic validation for the public Agent-UI v1 contract."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

CONTRACT_VERSION = "1.0.0"

REQUEST_TYPES = frozenset({"message", "confirm", "cancel", "simulation_control", "reset"})
RESPONSE_STATUSES = frozenset(
    {"completed", "blocked", "needs_confirmation", "failed", "degraded"}
)
EVENT_TYPES = frozenset(
    {"proposal", "decision", "execution", "state_changed", "active_action"}
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FORBIDDEN_KEY_MARKERS = frozenset(
    {
        "authorization",
        "apikey",
        "xapikey",
        "accesstoken",
        "refreshtoken",
        "secret",
        "clientsecret",
        "password",
        "systemprompt",
        "developerprompt",
        "hiddenreasoning",
        "chainofthought",
        "providerthought",
        "permit",
        "permitid",
    }
)

_COMMON = {"contract_version", "kind", "session_id", "request_id", "occurred_at"}
_REQUEST_FIELDS = {
    "message": _COMMON | {"turn_id", "message"},
    "confirm": _COMMON | {"turn_id", "proposal_id", "confirmation_id"},
    "cancel": _COMMON | {"turn_id", "proposal_id", "confirmation_id"},
    "simulation_control": _COMMON | {"control", "parameters"},
    "reset": _COMMON | {"scope"},
}
_RESPONSE_BASE = _COMMON | {"status", "turn_id", "message"}
_RESPONSE_FIELDS = {
    "completed": _RESPONSE_BASE | {"proposal_id", "execution_id", "state_version"},
    "blocked": _RESPONSE_BASE | {"reason", "proposal_id", "rule_id", "state_version"},
    "needs_confirmation": _RESPONSE_BASE
    | {"proposal_id", "confirmation_id", "expires_at"},
    "failed": _RESPONSE_BASE | {"proposal_id", "execution_id", "error"},
    "degraded": _RESPONSE_BASE
    | {"reason", "proposal_id", "degraded_capability", "retryable"},
}
_EVENT_BASE = _COMMON | {"event_id", "sequence", "turn_id", "actor"}
_EVENT_FIELDS = {
    "proposal": _EVENT_BASE | {"proposal_id", "intent", "summary"},
    "decision": _EVENT_BASE
    | {"proposal_id", "outcome", "reason_code", "rule_id", "state_version"},
    "execution": _EVENT_BASE
    | {"proposal_id", "execution_id", "phase", "intent", "detail"},
    "state_changed": _EVENT_BASE
    | {"state_version", "changes", "source_execution_id"},
    "active_action": _EVENT_BASE
    | {"proposal_id", "execution_id", "active_action_id", "intent", "phase", "progress"},
}

_REQUIRED = {
    "message": _COMMON | {"turn_id", "message"},
    "confirm": _COMMON | {"turn_id", "proposal_id", "confirmation_id"},
    "cancel": _COMMON | {"turn_id", "proposal_id", "confirmation_id"},
    "simulation_control": _COMMON | {"control", "parameters"},
    "reset": _COMMON | {"scope"},
    "completed": _COMMON | {"status", "turn_id", "message"},
    "blocked": _COMMON | {"status", "turn_id", "message", "reason", "rule_id", "state_version"},
    "needs_confirmation": _COMMON
    | {"status", "turn_id", "message", "proposal_id", "confirmation_id", "expires_at"},
    "failed": _COMMON | {"status", "turn_id", "message", "error"},
    "degraded": _COMMON
    | {"status", "turn_id", "message", "degraded_capability", "retryable"},
    "proposal": _EVENT_BASE | {"proposal_id", "intent", "summary"},
    "decision": _EVENT_BASE
    | {"proposal_id", "outcome", "reason_code", "rule_id", "state_version"},
    "execution": _EVENT_BASE | {"proposal_id", "execution_id", "phase", "intent"},
    "state_changed": _EVENT_BASE | {"state_version", "changes"},
    "active_action": _EVENT_BASE
    | {"proposal_id", "execution_id", "active_action_id", "intent", "phase"},
}

_EXECUTION_PHASES = frozenset({"started", "succeeded", "failed", "stopped"})
_ACTIVE_PHASES = frozenset({"started", "progress", "stopped", "failed", "completed"})
_DECISION_OUTCOMES = frozenset(
    {"ALLOW", "BLOCK_UNSAFE", "BLOCK_UNAVAILABLE", "CONFIRM", "NOT_VOICE_ACTIONABLE", "ANSWER", "UNKNOWN"}
)


class AgentUIContractError(ValueError):
    """Typed integration error for a malformed or unsafe public payload."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _reject_private_fields(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = re.sub(r"[^a-z0-9]", "", str(raw_key).lower())
            if any(marker in key for marker in _FORBIDDEN_KEY_MARKERS):
                raise AgentUIContractError(
                    "PRIVATE_FIELD_EXPOSED", f"Public payload contains forbidden field {path}.{raw_key}"
                )
            _reject_private_fields(child, f"{path}.{raw_key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _reject_private_fields(child, f"{path}[{index}]")


def _require_identifier(payload: Mapping[str, Any], field: str) -> None:
    value = payload.get(field)
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise AgentUIContractError("INVALID_IDENTIFIER", f"{field} is not a valid public identifier")


def _validate_shape(payload: Mapping[str, Any], discriminator: str, allowed: set[str]) -> None:
    missing = sorted(_REQUIRED[discriminator] - set(payload))
    if missing:
        raise AgentUIContractError("MISSING_FIELD", f"{discriminator} is missing: {', '.join(missing)}")
    extras = sorted(set(payload) - allowed)
    if extras:
        raise AgentUIContractError("UNEXPECTED_FIELD", f"{discriminator} has unexpected fields: {', '.join(extras)}")
    if payload.get("contract_version") != CONTRACT_VERSION:
        raise AgentUIContractError(
            "CONTRACT_VERSION_MISMATCH",
            f"Expected {CONTRACT_VERSION!r}, got {payload.get('contract_version')!r}",
        )
    for field in ("session_id", "request_id"):
        _require_identifier(payload, field)


def validate_public_payload(payload: Mapping[str, Any]) -> None:
    """Validate one closed public request, response, or event envelope."""

    if not isinstance(payload, Mapping):
        raise AgentUIContractError("INVALID_PAYLOAD", "Public payload must be an object")
    _reject_private_fields(payload)
    kind = payload.get("kind")
    if kind == "request":
        request_type = payload.get("request_type")
        if request_type not in REQUEST_TYPES:
            raise AgentUIContractError("UNKNOWN_REQUEST", f"Unsupported request_type: {request_type!r}")
        allowed = _REQUEST_FIELDS[request_type] | {"request_type"}
        _validate_shape(payload, request_type, allowed)
        if request_type == "message" and (not isinstance(payload["message"], str) or not payload["message"].strip()):
            raise AgentUIContractError("INVALID_MESSAGE", "message must be non-empty")
        if request_type == "simulation_control" and not isinstance(payload["parameters"], Mapping):
            raise AgentUIContractError("INVALID_PARAMETERS", "parameters must be an object")
    elif kind == "response":
        status = payload.get("status")
        if status not in RESPONSE_STATUSES:
            raise AgentUIContractError("UNKNOWN_STATUS", f"Unsupported response status: {status!r}")
        _validate_shape(payload, status, _RESPONSE_FIELDS[status])
        if status == "degraded" and not isinstance(payload["retryable"], bool):
            raise AgentUIContractError("INVALID_RESPONSE", "retryable must be boolean")
    elif kind == "event":
        event_type = payload.get("event_type")
        if event_type not in EVENT_TYPES:
            raise AgentUIContractError("UNKNOWN_EVENT", f"Unsupported event_type: {event_type!r}")
        _validate_shape(payload, event_type, _EVENT_FIELDS[event_type] | {"event_type"})
        for field in ("event_id", "turn_id"):
            _require_identifier(payload, field)
        if not isinstance(payload["sequence"], int) or isinstance(payload["sequence"], bool) or payload["sequence"] < 1:
            raise AgentUIContractError("INVALID_SEQUENCE", "sequence must be a positive integer")
        if event_type == "execution" and payload["phase"] not in _EXECUTION_PHASES:
            raise AgentUIContractError("INVALID_PHASE", "Unsupported execution phase")
        if event_type == "active_action" and payload["phase"] not in _ACTIVE_PHASES:
            raise AgentUIContractError("INVALID_PHASE", "Unsupported active action phase")
        if event_type == "decision" and payload["outcome"] not in _DECISION_OUTCOMES:
            raise AgentUIContractError("INVALID_OUTCOME", "Unsupported decision outcome")
        if event_type == "state_changed" and not isinstance(payload["changes"], Mapping):
            raise AgentUIContractError("INVALID_STATE_CHANGE", "changes must be an object")
    else:
        raise AgentUIContractError("UNKNOWN_KIND", "kind must be request, response, or event")


def validate_event_stream(events: Sequence[Mapping[str, Any]]) -> None:
    """Validate ordering and correlation for one session event stream.

    Global sequence is contiguous. Per proposal, decision follows proposal,
    execution follows ALLOW, and state/active-action effects follow execution.
    Operator state changes may exist without an Agent proposal or execution.
    """

    expected_sequence = 1
    session_id: str | None = None
    proposals: dict[str, tuple[str, str, str]] = {}
    decisions: dict[str, str] = {}
    executions: dict[str, tuple[str, str, str, str]] = {}
    for event in events:
        validate_public_payload(event)
        if event.get("kind") != "event":
            raise AgentUIContractError("NON_EVENT_IN_STREAM", "Event stream contains a non-event payload")
        if session_id is None:
            session_id = event["session_id"]
        elif event["session_id"] != session_id:
            raise AgentUIContractError("SESSION_MISMATCH", "Event stream mixes sessions")
        if event["sequence"] != expected_sequence:
            raise AgentUIContractError("EVENT_ORDER_GAP", f"Expected sequence {expected_sequence}")
        expected_sequence += 1

        event_type = event["event_type"]
        proposal_id = event.get("proposal_id")
        if event_type == "proposal":
            if proposal_id in proposals:
                raise AgentUIContractError("DUPLICATE_PROPOSAL", "proposal_id was already emitted")
            proposals[proposal_id] = (
                event["turn_id"],
                event["request_id"],
                event["intent"],
            )
        elif event_type == "decision":
            proposal = proposals.get(proposal_id)
            if proposal is None or proposal[:2] != (event["turn_id"], event["request_id"]):
                raise AgentUIContractError("DECISION_BEFORE_PROPOSAL", "decision has no correlated proposal")
            if proposal_id in decisions:
                raise AgentUIContractError("DUPLICATE_DECISION", "proposal already has a decision")
            decisions[proposal_id] = event["outcome"]
        elif event_type == "execution":
            execution_id = event["execution_id"]
            if decisions.get(proposal_id) != "ALLOW":
                raise AgentUIContractError("EXECUTION_WITHOUT_ALLOW", "execution requires an ALLOW decision")
            proposal = proposals.get(proposal_id)
            if proposal is None or proposal != (
                event["turn_id"],
                event["request_id"],
                event["intent"],
            ):
                raise AgentUIContractError(
                    "EXECUTION_CORRELATION_MISMATCH",
                    "execution does not match its proposal correlation fields",
                )
            if event["phase"] == "started":
                if execution_id in executions:
                    raise AgentUIContractError("DUPLICATE_EXECUTION", "execution was already started")
                executions[execution_id] = (
                    proposal_id,
                    event["turn_id"],
                    event["request_id"],
                    "started",
                )
            else:
                execution = executions.get(execution_id)
                expected = (proposal_id, event["turn_id"], event["request_id"], "started")
                if execution != expected:
                    code = "EXECUTION_ALREADY_TERMINAL" if execution is not None else "EXECUTION_NOT_STARTED"
                    raise AgentUIContractError(code, "execution must transition once from started to terminal")
                executions[execution_id] = (*execution[:3], event["phase"])
        elif event_type == "active_action":
            execution = executions.get(event["execution_id"])
            if execution != (
                proposal_id,
                event["turn_id"],
                event["request_id"],
                "started",
            ):
                raise AgentUIContractError("ACTIVE_ACTION_BEFORE_EXECUTION", "active action has no execution start")
        elif event_type == "state_changed" and event.get("actor") == "AGENT":
            source_execution_id = event.get("source_execution_id")
            execution = executions.get(source_execution_id)
            if execution is None or execution[3] != "started":
                raise AgentUIContractError("STATE_CHANGE_WITHOUT_EXECUTION", "Agent state change has no execution")
