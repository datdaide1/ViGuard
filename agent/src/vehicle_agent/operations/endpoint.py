"""Framework-neutral public boundary for OPS-01 operations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from ..contracts.agent_ui.v1.contract import CONTRACT_VERSION, validate_public_payload
from .runtime import HealthRegistry, RuntimeOperations, UIConnectionRegistry


class OperationsEndpoint:
    """Expose reset, health/readiness, and UI reconnect without tool execution."""

    def __init__(
        self,
        runtime: RuntimeOperations,
        health: HealthRegistry,
        ui_connections: UIConnectionRegistry,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._runtime = runtime
        self._health = health
        self._ui_connections = ui_connections
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def post_reset(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        validate_public_payload(payload)
        if payload.get("kind") != "request" or payload.get("request_type") != "reset":
            raise ValueError("reset endpoint accepts only reset requests")
        self._runtime.reset(payload["scope"], session_id=payload["session_id"])
        response = {
            "contract_version": CONTRACT_VERSION,
            "kind": "response",
            "status": "completed",
            "session_id": payload["session_id"],
            # Agent-UI v1 responseBase requires a turn_id while resetRequest
            # intentionally has none. request_id is the stable reset turn.
            "turn_id": payload["request_id"],
            "request_id": payload["request_id"],
            "occurred_at": self._clock().isoformat().replace("+00:00", "Z"),
            "message": "Runtime reset completed.",
        }
        validate_public_payload(response)
        return response

    def get_health(self) -> Mapping[str, Any]:
        return self._health.snapshot()

    def reconnect(self, session_id: str, connection_id: str) -> dict[str, Any]:
        return self._ui_connections.reconnect(session_id, connection_id).to_dict()
