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


def proposal_digest(proposal: Mapping[str, Any]) -> str:
    """Faithful copy of contract v1 ``proposal_digest`` (byte-for-byte identical)."""

    validate_action_proposal(proposal)
    projection = {
        "arguments": proposal["arguments"],
        "contract_version": proposal["contract_version"],
        "proposal_id": proposal["proposal_id"],
        "session_id": proposal["session_id"],
        "source_turn_id": proposal["source_turn_id"],
        "tool": proposal["tool"],
    }
    canonical = json.dumps(
        projection,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


# --- outbound builders -------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


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
) -> dict[str, Any]:
    """Build a GuardrailDecision. Attaches a bound permit iff ``outcome == 'ALLOW'``."""

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
    if outcome == "ANSWER" and answer is not None:
        decision["answer"] = dict(answer)
    if outcome == "ALLOW":
        decision["permit"] = _permit(
            proposal=proposal,
            intent=intent,
            rule_id=rule_id,
            state_version=int(state_version),
            policy_checksum=policy_checksum,
        )
    return decision


def _reason_token(reason_code: str) -> str:
    """Engine emits e.g. ``POLICY_ALLOW (precedence over R031)``; the wire field is
    a bare identifier. Keep the leading token, drop the parenthetical detail."""

    token = str(reason_code).split(" ", 1)[0].strip() or "POLICY_DECISION"
    return token[:128]
