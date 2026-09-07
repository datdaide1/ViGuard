"""Outer Guardrail outcome routing in front of the approved-text Agent."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Mapping

from .approved import ApprovedTextAgent, ApprovedTurnRequest
from .orchestrator import CancellationToken, TurnResult, TurnState, TurnStatus


BLOCK_OUTCOMES = frozenset({"BLOCK", "BLOCK_UNSAFE", "BLOCK_UNAVAILABLE"})


@dataclass(frozen=True)
class GuardedTurnRequest:
    session_id: str
    turn_id: str
    request_id: str
    message: str
    messages: tuple[Mapping[str, str], ...] = ()


@dataclass(frozen=True)
class UpstreamGuardrailDecision:
    """Small hand-off contract produced by the Guardrail-facing integration layer."""

    request_id: str
    intent: str
    outcome: str
    response: str = ""
    state_version: int | None = None
    rule_id: str | None = None
    confirmation_id: str | None = None
    expires_at: str | None = None


@dataclass(frozen=True)
class PendingApprovedTurn:
    request: GuardedTurnRequest
    decision: UpstreamGuardrailDecision


class GuardedAgentCoordinator:
    """Route ALLOW/CONFIRM/BLOCK without moving policy logic into Agent core."""

    def __init__(self, agent: ApprovedTextAgent) -> None:
        self._agent = agent
        self._pending: dict[str, PendingApprovedTurn] = {}
        self._pending_lock = threading.Lock()

    def handle_decision(
        self,
        request: GuardedTurnRequest,
        decision: UpstreamGuardrailDecision,
        cancellation: CancellationToken | None = None,
    ) -> TurnResult:
        self._validate(request, decision)
        if decision.outcome == "ALLOW":
            return self._execute(request, decision, cancellation)
        if decision.outcome == "CONFIRM":
            return self._register_confirmation(request, decision)
        return self._blocked(decision)

    def resolve_confirmation(
        self,
        confirmation_id: str,
        *,
        accepted: bool,
        refreshed_decision: UpstreamGuardrailDecision | None = None,
        cancellation: CancellationToken | None = None,
    ) -> TurnResult:
        with self._pending_lock:
            pending = self._pending.get(confirmation_id)
        if pending is None:
            raise ValueError("confirmation is missing, expired, or already resolved")
        if accepted and refreshed_decision is None:
            raise ValueError("accepted confirmation requires a fresh Guardrail decision")
        with self._pending_lock:
            pending = self._pending.pop(confirmation_id, None)
        if pending is None:
            raise ValueError("confirmation was resolved concurrently")
        if self._expired(pending.decision.expires_at):
            return TurnResult(
                TurnStatus.BLOCKED,
                TurnState.BLOCKED,
                "Yêu cầu xác nhận đã hết hạn.",
                confirmation_id=confirmation_id,
                reason="CONFIRMATION_EXPIRED",
                trace=(TurnState.RECEIVED, TurnState.BLOCKED),
            )
        if not accepted:
            return TurnResult(
                TurnStatus.BLOCKED,
                TurnState.BLOCKED,
                "Đã hủy yêu cầu.",
                confirmation_id=confirmation_id,
                reason="CONFIRMATION_REJECTED",
                trace=(TurnState.RECEIVED, TurnState.BLOCKED),
            )
        assert refreshed_decision is not None
        self._validate(pending.request, refreshed_decision)
        if refreshed_decision.intent != pending.decision.intent:
            raise ValueError("refreshed Guardrail decision changed the confirmed intent")
        return self.handle_decision(pending.request, refreshed_decision, cancellation)

    @property
    def pending_confirmations(self) -> Mapping[str, PendingApprovedTurn]:
        with self._pending_lock:
            return MappingProxyType(dict(self._pending))

    def _execute(
        self,
        request: GuardedTurnRequest,
        decision: UpstreamGuardrailDecision,
        cancellation: CancellationToken | None,
    ) -> TurnResult:
        return self._agent.handle_approved_text(
            ApprovedTurnRequest(
                session_id=request.session_id,
                turn_id=request.turn_id,
                request_id=request.request_id,
                message=request.message,
                intent_hint=decision.intent,
                state_version=decision.state_version,
                messages=request.messages,
            ),
            cancellation,
        )

    def _register_confirmation(
        self, request: GuardedTurnRequest, decision: UpstreamGuardrailDecision
    ) -> TurnResult:
        confirmation_id = decision.confirmation_id
        if confirmation_id is None:
            raise ValueError("CONFIRM requires confirmation_id")
        if self._expired(decision.expires_at):
            raise ValueError("CONFIRM requires a future expires_at")
        with self._pending_lock:
            if confirmation_id in self._pending:
                raise ValueError("confirmation_id already exists")
            self._pending[confirmation_id] = PendingApprovedTurn(request, decision)
        return TurnResult(
            TurnStatus.NEEDS_CONFIRMATION,
            TurnState.AWAITING_CONFIRMATION,
            decision.response,
            state_version=decision.state_version,
            rule_id=decision.rule_id,
            confirmation_id=confirmation_id,
            expires_at=decision.expires_at,
            trace=(TurnState.RECEIVED, TurnState.AWAITING_CONFIRMATION),
        )

    @staticmethod
    def _blocked(decision: UpstreamGuardrailDecision) -> TurnResult:
        return TurnResult(
            TurnStatus.BLOCKED,
            TurnState.BLOCKED,
            decision.response,
            state_version=decision.state_version,
            rule_id=decision.rule_id,
            reason=decision.outcome,
            trace=(TurnState.RECEIVED, TurnState.BLOCKED),
        )

    @staticmethod
    def _validate(
        request: GuardedTurnRequest, decision: UpstreamGuardrailDecision
    ) -> None:
        for name in ("session_id", "turn_id", "request_id"):
            value = getattr(request, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise ValueError(f"{name} must be a non-empty identifier")
        if not isinstance(request.message, str) or not request.message.strip():
            raise ValueError("message must be non-empty")
        if decision.outcome not in {"ALLOW", "CONFIRM", *BLOCK_OUTCOMES}:
            raise ValueError("unsupported Guardrail outcome")
        if not isinstance(decision.request_id, str) or not decision.request_id.strip():
            raise ValueError("Guardrail request_id must be non-empty")
        if decision.request_id != request.request_id:
            raise ValueError("Guardrail request_id does not match Agent request_id")
        if not isinstance(decision.intent, str) or not decision.intent.strip():
            raise ValueError("Guardrail intent must be non-empty")
        if decision.outcome != "ALLOW" and (
            not isinstance(decision.response, str) or not decision.response.strip()
        ):
            raise ValueError("CONFIRM/BLOCK Guardrail response must be non-empty")

    @staticmethod
    def _expired(expires_at: str | None) -> bool:
        if not isinstance(expires_at, str):
            return True
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return True
        return expiry.tzinfo is None or expiry <= datetime.now(timezone.utc)
