"""Fail-closed semantic validation for the Guardrail-Agent v1 contract."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

CONTRACT_VERSION = "1.0.0"
OUTCOMES = frozenset(
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
NON_EXECUTABLE_OUTCOMES = OUTCOMES - {"ALLOW"}

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
_DECISION_REQUIRED = {
    "contract_version",
    "kind",
    "request_id",
    "proposal_id",
    "intent",
    "outcome",
    "rule_id",
    "state_version",
    "policy_checksum",
    "reason_code",
    "relevant_state",
}
_PERMIT_REQUIRED = {
    "permit_id",
    "proposal_digest",
    "intent",
    "rule_id",
    "state_version",
    "policy_checksum",
    "issued_at",
    "expires_at",
    "single_use",
}
_DECISION_OPTIONAL = {"answer", "confirmation", "permit"}
_ERROR_FIELDS = {"contract_version", "kind", "request_id", "error"}
_ERROR_DETAIL_FIELDS = {"code", "message", "retryable", "details"}
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class ContractValidationError(ValueError):
    """Typed local integration error; it is never a policy outcome."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.execution_allowed = False


def _require_version(payload: Mapping[str, Any]) -> None:
    if payload.get("contract_version") != CONTRACT_VERSION:
        raise ContractValidationError(
            "CONTRACT_VERSION_MISMATCH",
            f"Expected contract {CONTRACT_VERSION!r}, got {payload.get('contract_version')!r}",
        )


def _require_fields(payload: Mapping[str, Any], fields: set[str], kind: str) -> None:
    missing = sorted(field for field in fields if field not in payload)
    if missing:
        raise ContractValidationError(
            "MALFORMED_GUARDRAIL_RESPONSE",
            f"{kind} is missing required fields: {', '.join(missing)}",
        )


def _reject_extra_fields(payload: Mapping[str, Any], fields: set[str], kind: str) -> None:
    extras = sorted(set(payload) - fields)
    if extras:
        raise ContractValidationError(
            "MALFORMED_GUARDRAIL_RESPONSE",
            f"{kind} has unexpected fields: {', '.join(extras)}",
        )


def _require_identifier(value: Any, field: str) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ContractValidationError(
            "MALFORMED_GUARDRAIL_RESPONSE", f"{field} must be a non-empty identifier"
        )


def _require_digest(value: Any, field: str) -> None:
    if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
        raise ContractValidationError(
            "INVALID_PERMIT", f"{field} must be a lowercase sha256 digest"
        )


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ContractValidationError("INVALID_PERMIT", f"{field} must be a date-time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractValidationError("INVALID_PERMIT", f"{field} must be a date-time") from exc
    if parsed.tzinfo is None:
        raise ContractValidationError("INVALID_PERMIT", f"{field} must include a timezone")
    return parsed


def validate_action_proposal(proposal: Mapping[str, Any]) -> None:
    """Validate the closed Agent-to-Guardrail action proposal envelope."""

    _require_version(proposal)
    _require_fields(proposal, _PROPOSAL_FIELDS, "ActionProposal")
    extras = sorted(set(proposal) - _PROPOSAL_FIELDS)
    if extras:
        raise ContractValidationError(
            "INVALID_ACTION_PROPOSAL", f"Unexpected fields: {', '.join(extras)}"
        )
    if not isinstance(proposal["arguments"], Mapping):
        raise ContractValidationError("INVALID_ACTION_PROPOSAL", "arguments must be an object")


def proposal_digest(proposal: Mapping[str, Any]) -> str:
    """Digest the immutable execution-relevant projection of a valid proposal.

    Model/provider metadata is deliberately excluded: it is trace metadata and must
    not change the authorization identity of the canonical tool call.
    """

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


def validate_guardrail_result(result: Mapping[str, Any]) -> None:
    """Validate a Guardrail decision or typed integration error, fail closed."""

    _require_version(result)
    kind = result.get("kind")
    if kind == "error":
        _require_fields(
            result,
            {"contract_version", "kind", "request_id", "error"},
            "GuardrailError",
        )
        error = result["error"]
        if not isinstance(error, Mapping) or not {"code", "message", "retryable"} <= set(error):
            raise ContractValidationError(
                "MALFORMED_GUARDRAIL_RESPONSE", "GuardrailError.error is malformed"
            )
        if "permit" in result:
            raise ContractValidationError(
                "PERMIT_FORBIDDEN", "Typed errors cannot contain a permit"
            )
        _reject_extra_fields(result, _ERROR_FIELDS, "GuardrailError")
        _reject_extra_fields(error, _ERROR_DETAIL_FIELDS, "GuardrailError.error")
        _require_identifier(result["request_id"], "request_id")
        _require_identifier(error["code"], "error.code")
        if not isinstance(error["message"], str) or not error["message"]:
            raise ContractValidationError(
                "MALFORMED_GUARDRAIL_RESPONSE", "error.message must be non-empty"
            )
        if not isinstance(error["retryable"], bool):
            raise ContractValidationError(
                "MALFORMED_GUARDRAIL_RESPONSE", "error.retryable must be boolean"
            )
        return
    if kind != "decision":
        raise ContractValidationError(
            "MALFORMED_GUARDRAIL_RESPONSE", "kind must be decision or error"
        )

    _require_fields(result, _DECISION_REQUIRED, "GuardrailDecision")
    _reject_extra_fields(result, _DECISION_REQUIRED | _DECISION_OPTIONAL, "GuardrailDecision")
    for field in ("request_id", "proposal_id", "intent", "rule_id", "reason_code"):
        _require_identifier(result[field], field)
    if not isinstance(result["state_version"], int) or isinstance(result["state_version"], bool):
        raise ContractValidationError(
            "MALFORMED_GUARDRAIL_RESPONSE", "state_version must be an integer"
        )
    _require_digest(result["policy_checksum"], "policy_checksum")
    if not isinstance(result["relevant_state"], Mapping):
        raise ContractValidationError(
            "MALFORMED_GUARDRAIL_RESPONSE", "relevant_state must be an object"
        )
    outcome = result["outcome"]
    if outcome not in OUTCOMES:
        raise ContractValidationError("UNKNOWN_OUTCOME", f"Unsupported outcome: {outcome!r}")

    permit = result.get("permit")
    if outcome in NON_EXECUTABLE_OUTCOMES and "permit" in result:
        raise ContractValidationError(
            "PERMIT_FORBIDDEN", f"{outcome} cannot contain a permit"
        )
    if outcome == "ALLOW":
        if not isinstance(permit, Mapping):
            raise ContractValidationError("PERMIT_REQUIRED", "ALLOW requires a permit")
        _require_fields(permit, _PERMIT_REQUIRED, "ActionPermit")
        _reject_extra_fields(permit, _PERMIT_REQUIRED, "ActionPermit")
        for field in ("permit_id", "intent", "rule_id"):
            _require_identifier(permit[field], f"permit.{field}")
        _require_digest(permit["proposal_digest"], "permit.proposal_digest")
        _require_digest(permit["policy_checksum"], "permit.policy_checksum")
        if not isinstance(permit["state_version"], int) or isinstance(
            permit["state_version"], bool
        ):
            raise ContractValidationError(
                "INVALID_PERMIT", "permit.state_version must be an integer"
            )
        if permit["single_use"] is not True:
            raise ContractValidationError(
                "INVALID_PERMIT", "ActionPermit.single_use must be true"
            )
        for field in ("intent", "rule_id", "state_version", "policy_checksum"):
            if permit[field] != result[field]:
                raise ContractValidationError(
                    "INVALID_PERMIT", f"Permit {field} does not match decision"
                )
        issued_at = _parse_timestamp(permit["issued_at"], "permit.issued_at")
        expires_at = _parse_timestamp(permit["expires_at"], "permit.expires_at")
        if expires_at <= issued_at:
            raise ContractValidationError(
                "INVALID_PERMIT", "permit.expires_at must be after permit.issued_at"
            )
