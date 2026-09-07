"""Build schema-exact wire envelopes for the Guardrail->Agent v1 contract.

The digest + proposal validation here are a faithful copy of the shared wire
spec (``vivi_agent/authorization/contract.py``); decision D1 keeps the two
services from importing each other, so the contract primitives are duplicated
and locked by tests against the Agent's own ``examples.json`` /
``validate_guardrail_result``.

Guarantees enforced here (PRD BR-02/BR-04, contract fail-closed rules):
  - a permit is attached **only** to ``ALLOW``; every other outcome, and every
    error, carries none;
  - the permit is bound to the exact proposal (``proposal_digest``), single-use,
    time-boxed, and its ``intent`` / ``rule_id`` / ``state_version`` /
    ``policy_checksum`` equal the decision's;
  - no field outside the contract's closed set is ever emitted.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

CONTRACT_VERSION = "1.0.0"
PERMIT_TTL = timedelta(seconds=2)  # matches wire/examples.json
CONFIRM_TTL = timedelta(seconds=30)  # matches wire/examples.json (10:00:00 -> 10:00:30)

_OUTCOMES = frozenset(
    {
        "ALLOW",
        "BLOCK_UNSAFE",
        "BLOCK_UNAVAILABLE",
        "CONFIRM",
        "NOT_VOICE_ACTIONABLE",
        "ANSWER",
        "UNKNOWN",
    }
)
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

# --- copied from contract v1: closed ActionProposal envelope -------------------
_PROPOSAL_FIELDS = {
    "contract_version",
    "proposal_id",
    "session_id",
    "source_turn_id",
    "tool",
    "arguments",
    "model_provider",
    "model_id",
}


class WireError(ValueError):
    """A wire-level defect in an inbound payload. Never a policy outcome."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.execution_allowed = False


def _identifier(value: Any, field: str, code: str) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise WireError(code, f"{field} must be a non-empty identifier (<=128 chars)")


def require_contract_version(payload: Mapping[str, Any]) -> None:
    if payload.get("contract_version") != CONTRACT_VERSION:
        raise WireError(
            "CONTRACT_VERSION_MISMATCH",
            f"Expected contract {CONTRACT_VERSION!r}, got {payload.get('contract_version')!r}",
        )


def validate_action_proposal(proposal: Mapping[str, Any]) -> None:
    """Faithful copy of contract v1 ``validate_action_proposal`` (fail closed)."""

    require_contract_version(proposal)
    missing = sorted(f for f in _PROPOSAL_FIELDS if f not in proposal)
    if missing:
        raise WireError(
            "MALFORMED_GUARDRAIL_RESPONSE",
            f"ActionProposal is missing required fields: {', '.join(missing)}",
        )
    extras = sorted(set(proposal) - _PROPOSAL_FIELDS)
    if extras:
        raise WireError("INVALID_ACTION_PROPOSAL", f"Unexpected fields: {', '.join(extras)}")
    if not isinstance(proposal["arguments"], Mapping):
        raise WireError("INVALID_ACTION_PROPOSAL", "arguments must be an object")
    for field in ("proposal_id", "session_id", "source_turn_id", "tool", "model_provider", "model_id"):
        _identifier(proposal[field], field, "INVALID_ACTION_PROPOSAL")


def _sha256_projection(projection: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        projection,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def proposal_digest(proposal: Mapping[str, Any]) -> str:
    """Faithful copy of contract v1 ``proposal_digest`` (byte-for-byte identical)."""

    validate_action_proposal(proposal)
    return _sha256_projection(
        {
            "arguments": proposal["arguments"],
            "contract_version": proposal["contract_version"],
            "proposal_id": proposal["proposal_id"],
            "session_id": proposal["session_id"],
            "source_turn_id": proposal["source_turn_id"],
            "tool": proposal["tool"],
        }
    )


def monitor_request_digest(payload: Mapping[str, Any]) -> str:
    """Bind a monitor decision to its request. Not part of contract v1's digest
    spec (there is no proposal on the monitor path); it only has to be a valid
    ``sha256:...`` string so the ALLOW-shaped "keep running" reply passes the
    Agent's ``validate_guardrail_result``."""

    return _sha256_projection(
        {
            "active_action_id": str(payload.get("active_action_id", "")),
            "contract_version": CONTRACT_VERSION,
            "intent": str(payload.get("intent", "")),
            "request_id": str(payload.get("request_id", "")),
        }
    )


# --- outbound builders -------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


_new_id = new_id  # backward-compatible alias for intra-module use


def error_envelope(
    request_id: str, code: str, message: str, *, retryable: bool = False,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """A typed GuardrailError. Carries no permit, ever."""

    error: dict[str, Any] = {"code": code, "message": message, "retryable": bool(retryable)}
    if details is not None:
        error["details"] = dict(details)
    return {
        "contract_version": CONTRACT_VERSION,
        "kind": "error",
        "request_id": request_id if isinstance(request_id, str) and request_id else "unknown",
        "error": error,
    }


def _permit(
    *, proposal: Mapping[str, Any], intent: str, rule_id: str,
    state_version: int, policy_checksum: str,
) -> dict[str, Any]:
    issued = _now()
    return {
        "permit_id": _new_id("permit"),
        "proposal_digest": proposal_digest(proposal),
        "intent": intent,
        "rule_id": rule_id,
        "state_version": state_version,
        "policy_checksum": policy_checksum,
        "issued_at": issued.isoformat(),
        "expires_at": (issued + PERMIT_TTL).isoformat(),
        "single_use": True,
    }


def decision_envelope(
    *,
    request_id: str | None,
    proposal: Mapping[str, Any],
    intent: str,
    outcome: str,
    rule_id: str,
    state_version: int,
    policy_checksum: str,
    reason_code: str,
    relevant_state: Mapping[str, Any],
    answer: Mapping[str, Any] | None = None,
    confirmation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a GuardrailDecision. Attaches a bound permit iff ``outcome == 'ALLOW'``;
    a ``confirmation`` block iff ``outcome == 'CONFIRM'``."""

    if outcome not in _OUTCOMES:
        raise WireError("UNKNOWN_OUTCOME", f"unsupported outcome {outcome!r}")
    if not isinstance(rule_id, str) or not rule_id:
        raise WireError("MALFORMED_GUARDRAIL_RESPONSE", "rule_id must be a non-empty identifier")
    if not _DIGEST_PATTERN.fullmatch(str(policy_checksum)):
        raise WireError("MALFORMED_GUARDRAIL_RESPONSE", "policy_checksum must be a sha256 digest")

    decision: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "kind": "decision",
        "request_id": request_id if isinstance(request_id, str) and request_id else _new_id("req"),
        "proposal_id": proposal["proposal_id"],
        "intent": intent,
        "outcome": outcome,
        "rule_id": rule_id,
        "state_version": int(state_version),
        "policy_checksum": policy_checksum,
        "reason_code": _reason_token(reason_code),
        "relevant_state": dict(relevant_state),
    }
    if outcome in ("ANSWER", "UNKNOWN") and answer is not None:
        decision["answer"] = dict(answer)
    if outcome == "CONFIRM":
        if not isinstance(confirmation, Mapping):
            raise WireError("MALFORMED_GUARDRAIL_RESPONSE", "CONFIRM requires a confirmation block")
        decision["confirmation"] = dict(confirmation)
    if outcome == "ALLOW":
        decision["permit"] = _permit(
            proposal=proposal,
            intent=intent,
            rule_id=rule_id,
            state_version=int(state_version),
            policy_checksum=policy_checksum,
        )
    return decision


def query_decision_envelope(
    *,
    request_id: str,
    proposal_id: str,
    intent: str,
    outcome: str,
    rule_id: str,
    state_version: int,
    policy_checksum: str,
    reason_code: str,
    relevant_state: Mapping[str, Any],
    answer: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """A read-only-query decision (ANSWER / UNKNOWN). Never carries a permit."""

    if outcome not in ("ANSWER", "UNKNOWN"):
        raise WireError("UNKNOWN_OUTCOME", f"query path cannot return {outcome!r}")
    decision: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "kind": "decision",
        "request_id": request_id or _new_id("req-query"),
        "proposal_id": proposal_id,
        "intent": intent,
        "outcome": outcome,
        "rule_id": rule_id or "Q000",
        "state_version": int(state_version),
        "policy_checksum": policy_checksum,
        "reason_code": _reason_token(reason_code),
        "relevant_state": dict(relevant_state),
    }
    if answer is not None:
        decision["answer"] = dict(answer)
    return decision


def confirmation_block(confirmation_id: str, proposal_id: str, expires_at: str) -> dict[str, Any]:
    """The wire ``pendingConfirmation`` (schema: exactly these four fields)."""

    return {
        "confirmation_id": confirmation_id,
        "proposal_id": proposal_id,
        "expires_at": expires_at,
        "single_use": True,
    }


def monitor_decision_envelope(
    *,
    request_id: str,
    active_action_id: str,
    intent: str,
    outcome: str,
    rule_id: str,
    state_version: int,
    policy_checksum: str,
    reason_code: str,
    relevant_state: Mapping[str, Any],
    digest: str,
) -> dict[str, Any]:
    """Monitor-path decision.

    The Agent's monitor adapter treats ``outcome == 'ALLOW'`` as "keep running"
    and every other outcome as "stop". Contract v1 has no dedicated
    monitor-continue signal, so "keep running" is expressed as an ALLOW carrying
    a permit bound to ``digest`` (``monitor_request_digest``) -- the adapter does
    not consume it, but ``validate_guardrail_result`` requires it. A stop is the
    real blocking outcome + ``rule_id``, no permit.
    """

    decision: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "kind": "decision",
        "request_id": request_id or _new_id("req-mon"),
        "proposal_id": active_action_id,  # correlation id on the monitor path
        "intent": intent,
        "outcome": outcome,
        "rule_id": rule_id,
        "state_version": int(state_version),
        "policy_checksum": policy_checksum,
        "reason_code": _reason_token(reason_code),
        "relevant_state": dict(relevant_state),
    }
    if outcome == "ALLOW":
        issued = _now()
        decision["permit"] = {
            "permit_id": _new_id("permit-mon"),
            "proposal_digest": digest,
            "intent": intent,
            "rule_id": rule_id,
            "state_version": int(state_version),
            "policy_checksum": policy_checksum,
            "issued_at": issued.isoformat(),
            "expires_at": (issued + PERMIT_TTL).isoformat(),
            "single_use": True,
        }
    return decision


def _reason_token(reason_code: str) -> str:
    """Engine emits e.g. ``POLICY_ALLOW (precedence over R031)``; the wire field is
    a bare identifier. Keep the leading token, drop the parenthetical detail."""

    token = str(reason_code).split(" ", 1)[0].strip() or "POLICY_DECISION"
    return token[:128]
