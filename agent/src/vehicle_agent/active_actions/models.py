"""Active Action Models (ACTV-01).

Data entities representing continuous/long-running active action lifecycle records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from vehicle_agent.vehicle.state.model import ActiveActionPhase


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ActiveActionRecord:
    """Detailed record of a monitored long-running active action in the registry."""

    action_id: str
    intent: str
    active_action_name: str
    phase: ActiveActionPhase = ActiveActionPhase.STARTED
    progress: float = 0.0
    proposal_id: str = ""
    decision_id: str = ""
    execution_id: str = ""
    state_version: int = 0
    session_id: str = ""
    request_id: str = ""
    turn_id: str = ""
    stop_reason: str = ""
    failure_reason: str = ""
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action_id:
            raise ValueError("action_id must be a non-empty string")
        if not self.intent:
            raise ValueError("intent must be a non-empty string")
        if not isinstance(self.phase, ActiveActionPhase):
            raise ValueError(f"phase must be an instance of ActiveActionPhase, got {type(self.phase)}")
        if not isinstance(self.progress, (int, float)) or not (0.0 <= self.progress <= 1.0):
            raise ValueError(f"progress must be a float in range [0.0, 1.0], got {self.progress}")
        if not isinstance(self.state_version, int) or self.state_version < 0:
            raise ValueError(f"state_version must be a non-negative int, got {self.state_version}")

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dict format for serialization / API responses."""
        return {
            "action_id": self.action_id,
            "intent": self.intent,
            "active_action_name": self.active_action_name,
            "phase": self.phase.value if isinstance(self.phase, ActiveActionPhase) else str(self.phase),
            "progress": self.progress,
            "proposal_id": self.proposal_id,
            "decision_id": self.decision_id,
            "execution_id": self.execution_id,
            "state_version": self.state_version,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "turn_id": self.turn_id,
            "stop_reason": self.stop_reason,
            "failure_reason": self.failure_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }
