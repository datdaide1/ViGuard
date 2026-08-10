"""Permit Store lifecycle and Permit Verifier implementation."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from vivi_agent.authorization import (
    AuthorizationContractError,
    authorization_request_digest,
    validate_action_proposal,
)
from .errors import (
    ExpiredPermitError,
    InvalidPermitError,
    PermitVerificationError,
    ReplayAttackError,
    SubstitutionAttackError,
)


def _parse_iso_timestamp(ts: Any, field_name: str) -> datetime:
    if not isinstance(ts, str):
        raise InvalidPermitError(f"{field_name} must be an ISO date string")
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidPermitError(f"Invalid timestamp format in {field_name}: {ts}") from exc
    if dt.tzinfo is None:
        raise InvalidPermitError(f"{field_name} must include timezone info")
    return dt


class PermitStore:
    """Thread-safe lifecycle store for consumed single-use permits.

    Guarantees atomic permit consumption to prevent replay attacks across
    concurrent execution calls.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self._consumed_permits: set[str] = set()
        self._revoked_before: dict[str, datetime] = {}
        self._global_revoked_before: datetime | None = None

    def mark_used(self, permit_id: str) -> None:
        """Mark permit_id as consumed.

        Raises ReplayAttackError if permit_id was already consumed.
        """
        if not permit_id or not isinstance(permit_id, str):
            raise InvalidPermitError("permit_id must be a non-empty string")
        with self._lock:
            if permit_id in self._consumed_permits:
                raise ReplayAttackError(f"Permit {permit_id!r} has already been consumed")
            self._consumed_permits.add(permit_id)

    def is_used(self, permit_id: str) -> bool:
        """Check whether permit_id has been consumed."""
        with self._lock:
            return permit_id in self._consumed_permits

    def clear(self) -> None:
        """Reset consumed permit history for isolated tests.

        Runtime reset must use :meth:`revoke_before`; clearing consumption
        history in production would make used permits replayable.
        """
        with self._lock:
            self._consumed_permits.clear()

    def revoke_before(self, timestamp: datetime, session_id: str | None = None) -> None:
        """Revoke permits issued at or before a runtime reset boundary."""
        if timestamp.tzinfo is None:
            raise ValueError("revocation timestamp must be timezone-aware")
        with self._lock:
            if session_id is None:
                current = self._global_revoked_before
                self._global_revoked_before = timestamp if current is None else max(current, timestamp)
            else:
                current = self._revoked_before.get(session_id)
                self._revoked_before[session_id] = timestamp if current is None else max(current, timestamp)

    def is_revoked(self, session_id: str, issued_at: datetime) -> bool:
        with self._lock:
            cutoffs = [
                cutoff
                for cutoff in (self._global_revoked_before, self._revoked_before.get(session_id))
                if cutoff is not None
            ]
            return bool(cutoffs and issued_at <= max(cutoffs))

    @contextmanager
    def lifecycle_boundary(self):
        """Serialize complete actuator executions and runtime resets.

        VehicleToolGateway holds this boundary from permit verification through
        actuator completion. RuntimeOperations holds the same boundary for the
        entire reset, so neither operation can cross the other.
        """
        with self._lifecycle_lock:
            yield


class PermitVerifier:
    """Fail-closed verifier for Guardrail permits against action proposals."""

    def __init__(self, store: PermitStore | None = None) -> None:
        self._store = store or PermitStore()

    @property
    def store(self) -> PermitStore:
        return self._store

    def verify(
        self,
        proposal: Mapping[str, Any],
        permit: Mapping[str, Any],
        decision: Mapping[str, Any] | None = None,
        current_time: datetime | None = None,
    ) -> None:
        """Verify action permit against proposal, decision context, and store lifecycle.

        Raises typed PermitVerificationError subclasses on failure.
        Does NOT consume the permit from store; consumption happens atomically in gateway.
        """
        # 1. Validate proposal envelope syntax
        try:
            validate_action_proposal(proposal)
        except AuthorizationContractError as exc:
            raise InvalidPermitError(f"Invalid proposal envelope: {exc}") from exc

        # 2. Check permit required fields
        if not isinstance(permit, Mapping):
            raise InvalidPermitError("Permit must be an object")

        required_fields = {
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
        missing = sorted(required_fields - set(permit.keys()))
        if missing:
            raise InvalidPermitError(f"Permit missing required fields: {', '.join(missing)}")

        if permit.get("single_use") is not True:
            raise InvalidPermitError("Permit single_use must be True")

        permit_id = permit["permit_id"]
        if not isinstance(permit_id, str) or not permit_id:
            raise InvalidPermitError("permit_id must be a non-empty string")

        # 3. Check replay attack
        if self._store.is_used(permit_id):
            raise ReplayAttackError(f"Permit {permit_id!r} has already been consumed")

        # 4. Check substitution attack (recalculate proposal digest)
        expected_digest = authorization_request_digest(proposal)
        actual_digest = permit.get("proposal_digest")
        if actual_digest != expected_digest:
            raise SubstitutionAttackError(
                f"Permit proposal_digest {actual_digest!r} does not match computed proposal digest {expected_digest!r}"
            )

        # 5. Consistency check with decision if supplied
        if decision is not None:
            if decision.get("outcome") != "ALLOW":
                raise InvalidPermitError(
                    f"Decision outcome must be ALLOW to execute permit, got {decision.get('outcome')!r}"
                )
            for field in ("intent", "rule_id", "state_version", "policy_checksum"):
                if decision.get(field) != permit.get(field):
                    raise InvalidPermitError(
                        f"Permit field {field!r} ({permit.get(field)!r}) does not match decision ({decision.get(field)!r})"
                    )

        # 6. Check expiration
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        issued_at = _parse_iso_timestamp(permit["issued_at"], "issued_at")
        expires_at = _parse_iso_timestamp(permit["expires_at"], "expires_at")

        session_id = proposal.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise InvalidPermitError("Proposal missing session_id")
        if self._store.is_revoked(session_id, issued_at):
            raise InvalidPermitError("Permit was revoked by runtime reset")

        if expires_at <= issued_at:
            raise InvalidPermitError("permit.expires_at must be strictly after permit.issued_at")

        if now > expires_at:
            raise ExpiredPermitError(f"Permit expired at {expires_at.isoformat()}, current time is {now.isoformat()}")

        if now < issued_at:
            raise InvalidPermitError(f"Permit not valid until {issued_at.isoformat()}, current time is {now.isoformat()}")
