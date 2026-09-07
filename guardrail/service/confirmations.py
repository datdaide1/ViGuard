"""Guardrail-side pending-confirmation store .

A ``CONFIRM`` decision on the action path parks the proposal here behind a
single-use, time-boxed ``confirmation_id``. ``POST /v1/confirmations/confirm``
looks it up, and the service then re-evaluates policy against a **fresh** state
snapshot : a confirmation only ever unlocks a fresh permit, it
never carries one.

Unknown / expired / already-consumed ids all resolve the same way:
``CONFIRMATION_NOT_ACTIVE`` (fail closed). A confirm request from a session
other than the one that raised the CONFIRM is rejected *without* consuming the
token (``ConfirmationSessionMismatch``) so the rightful session can still confirm.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .envelope import CONFIRM_TTL, new_id


class ConfirmationSessionMismatch(Exception):
    """The confirm request's session_id is not the one that raised the CONFIRM."""


@dataclass(frozen=True)
class PendingConfirmation:
    confirmation_id: str
    proposal: dict[str, Any]
    intent: str
    origin_rule_id: str
    session_id: str
    issued_at: datetime
    expires_at: datetime


class PendingConfirmationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingConfirmation] = {}
        self._consumed: set[str] = set()

    def create(
        self, proposal: dict[str, Any], intent: str, origin_rule_id: str, *, now: datetime | None = None
    ) -> PendingConfirmation:
        issued = now or datetime.now(timezone.utc)
        session_id = str(proposal.get("session_id") or "")
        record = PendingConfirmation(
            confirmation_id=new_id("confirm"),
            proposal=dict(proposal),
            intent=intent,
            origin_rule_id=origin_rule_id,
            session_id=session_id,
            issued_at=issued,
            expires_at=issued + CONFIRM_TTL,
        )
        with self._lock:
            self._pending[record.confirmation_id] = record
        return record

    def consume(
        self, confirmation_id: str, *, session_id: str, now: datetime | None = None
    ) -> PendingConfirmation | None:
        """Atomically take a still-valid pending confirmation, or return None.

        None covers every "not active" case: unknown id, expired, or replay.
        Raises ``ConfirmationSessionMismatch`` (leaving the token intact) when the
        id is live but ``session_id`` is not the originating session.
        """

        moment = now or datetime.now(timezone.utc)
        with self._lock:
            record = self._pending.get(confirmation_id)
            if record is None:
                return None
            if record.session_id and record.session_id != session_id:
                raise ConfirmationSessionMismatch(confirmation_id)
            self._pending.pop(confirmation_id, None)
            self._consumed.add(confirmation_id)
            if moment > record.expires_at:
                return None
            return record

    def peek(self, confirmation_id: str) -> PendingConfirmation | None:
        with self._lock:
            return self._pending.get(confirmation_id)
