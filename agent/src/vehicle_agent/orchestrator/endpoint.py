"""Agent-UI message endpoint implemented as a framework-neutral callable."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import logging
from typing import TYPE_CHECKING, Any
import uuid

from ..contracts.agent_ui.v1.contract import CONTRACT_VERSION, validate_public_payload
from .orchestrator import AgentOrchestrator, CancellationToken, TurnRequest, TurnStatus

if TYPE_CHECKING:
    from ..events.pipeline import AgentEventPipeline


logger = logging.getLogger(__name__)


class MessageEndpoint:
    def __init__(
        self,
        orchestrator: AgentOrchestrator,
        *,
        clock: Callable[[], datetime] | None = None,
        event_pipeline: AgentEventPipeline | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if event_pipeline is None:
            # Lazy import avoids extending the package-initialization cycle through
            # orchestrator -> events -> store -> public contract.
            from ..events.pipeline import AgentEventPipeline

            event_pipeline = AgentEventPipeline()
        self.event_pipeline = event_pipeline

    def post_message(
        self, payload: Mapping[str, Any], cancellation: CancellationToken | None = None
    ) -> dict[str, Any]:
        validate_public_payload(payload)
        if payload.get("kind") != "request" or payload.get("request_type") != "message":
            raise ValueError("message endpoint accepts only message requests")
        streaming = payload["contract_version"] == CONTRACT_VERSION
        if streaming:
            self._emit_progress(payload, "received", 0.0)
            self._emit_progress(payload, "resolving", 0.1)
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
            "contract_version": payload["contract_version"],
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
        if streaming:
            self._emit_progress(payload, "responding", 0.8)
            stream_id = f"stream-{uuid.uuid4().hex[:12]}"
            chunks = [result.message[index:index + 128] for index in range(0, len(result.message), 128)] or [" "]
            content_kind = "answer" if result.status is TurnStatus.COMPLETED else "status"
            for index, delta in enumerate(chunks):
                self._safe_emit(
                    self.event_pipeline.emit_response_chunk,
                    payload["session_id"], payload["turn_id"], payload["request_id"],
                    stream_id, index, delta,
                    content_kind=content_kind, final=index == len(chunks) - 1,
                )
            terminal = "failed" if result.status is TurnStatus.FAILED else "completed"
            self._emit_progress(payload, terminal, 1.0)
        validate_public_payload(response)
        return response

    def _emit_progress(self, payload: Mapping[str, Any], phase: str, progress: float) -> None:
        self._safe_emit(
            self.event_pipeline.emit_turn_progress,
            payload["session_id"], payload["turn_id"], payload["request_id"], phase, progress,
        )

    @staticmethod
    def _safe_emit(emitter: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> None:
        try:
            emitter(*args, **kwargs)
        except Exception:
            logger.exception("Public progress projection failed; terminal response remains authoritative")
