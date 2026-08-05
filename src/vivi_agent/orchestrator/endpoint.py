"""Agent-UI message endpoint implemented as a framework-neutral callable."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from ..contracts.agent_ui.v1.contract import CONTRACT_VERSION, validate_public_payload
from .orchestrator import AgentOrchestrator, CancellationToken, TurnRequest, TurnStatus


class MessageEndpoint:
    def __init__(
        self,
        orchestrator: AgentOrchestrator,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def post_message(
        self, payload: Mapping[str, Any], cancellation: CancellationToken | None = None
    ) -> dict[str, Any]:
        validate_public_payload(payload)
        if payload.get("kind") != "request" or payload.get("request_type") != "message":
            raise ValueError("message endpoint accepts only message requests")
        result = self._orchestrator.handle_message(
            TurnRequest(
                session_id=payload["session_id"],
                turn_id=payload["turn_id"],
                request_id=payload["request_id"],
                message=payload["message"],
            ),
            cancellation,
        )
        response: dict[str, Any] = {
            "contract_version": CONTRACT_VERSION,
            "kind": "response",
            "status": result.status.value,
            "session_id": payload["session_id"],
            "turn_id": payload["turn_id"],
            "request_id": payload["request_id"],
            "occurred_at": self._clock().isoformat().replace("+00:00", "Z"),
            "message": result.message,
        }
        if result.proposal_id:
            response["proposal_id"] = result.proposal_id
        if result.status is TurnStatus.COMPLETED:
            if result.execution_id:
                response["execution_id"] = result.execution_id
            if result.state_version is not None:
                response["state_version"] = result.state_version
        elif result.status is TurnStatus.BLOCKED:
            response.update(
                reason=result.reason,
                rule_id=result.rule_id,
                state_version=result.state_version,
            )
        elif result.status is TurnStatus.NEEDS_CONFIRMATION:
            response.update(
                confirmation_id=result.confirmation_id,
                expires_at=result.expires_at,
            )
        elif result.status is TurnStatus.FAILED:
            if result.execution_id:
                response["execution_id"] = result.execution_id
            response["error"] = result.error.to_dict() if result.error else {
                "code": "ORCHESTRATION_FAILED",
                "message": "Turn failed",
                "retryable": False,
            }
        elif result.status is TurnStatus.DEGRADED:
            response.update(
                reason=result.reason,
                degraded_capability=result.degraded_capability,
                retryable=bool(result.retryable),
            )
        validate_public_payload(response)
        return response
