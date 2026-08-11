"""Typed event models and constructors conforming to Agent-UI v1 contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
import uuid

CONTRACT_VERSION = "1.1.0"


def generate_id(prefix: str = "evt") -> str:
    """Generate a valid public identifier."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def current_iso_timestamp() -> str:
    """Return current timestamp in ISO 8601 UTC format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class EventBase:
    """Base class for public Agent UI events."""

    session_id: str
    turn_id: str
    request_id: str
    event_type: str
    event_id: str = field(default_factory=lambda: generate_id("evt"))
    occurred_at: str = field(default_factory=current_iso_timestamp)
    actor: str = "AGENT"
    contract_version: str = CONTRACT_VERSION
    kind: str = "event"

    def to_dict(self) -> dict[str, Any]:
        """Convert to raw dictionary representation."""
        return {
            "contract_version": self.contract_version,
            "kind": self.kind,
            "event_type": self.event_type,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "request_id": self.request_id,
            "occurred_at": self.occurred_at,
            "actor": self.actor,
        }


@dataclass(frozen=True)
class ProposalEvent(EventBase):
    """Event emitted when agent proposes an intent."""

    proposal_id: str = ""
    intent: str = ""
    summary: str = ""
    event_type: str = "proposal"

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "proposal_id": self.proposal_id,
            "intent": self.intent,
            "summary": self.summary,
        })
        return data


@dataclass(frozen=True)
class DecisionEvent(EventBase):
    """Event emitted when policy/guardrail decision is made for a proposal."""

    proposal_id: str = ""
    outcome: str = "ALLOW"
    reason_code: str = "PERMITTED"
    rule_id: str = "RULE_ALLOW_ALL"
    state_version: int = 0
    event_type: str = "decision"

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "proposal_id": self.proposal_id,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "rule_id": self.rule_id,
            "state_version": self.state_version,
        })
        return data


@dataclass(frozen=True)
class ExecutionEvent(EventBase):
    """Event emitted during execution lifecycle (started, succeeded, failed, stopped)."""

    proposal_id: str = ""
    execution_id: str = ""
    intent: str = ""
    phase: str = "started"
    detail: dict[str, Any] | None = None
    event_type: str = "execution"

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "proposal_id": self.proposal_id,
            "execution_id": self.execution_id,
            "intent": self.intent,
            "phase": self.phase,
        })
        if self.detail is not None:
            data["detail"] = self.detail
        return data


@dataclass(frozen=True)
class StateChangedEvent(EventBase):
    """Event emitted when vehicle or environment state updates."""

    state_version: int = 0
    changes: dict[str, Any] = field(default_factory=dict)
    source_execution_id: str | None = None
    event_type: str = "state_changed"

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "state_version": self.state_version,
            "changes": self.changes,
        })
        if self.source_execution_id is not None:
            data["source_execution_id"] = self.source_execution_id
        return data


@dataclass(frozen=True)
class ActiveActionEvent(EventBase):
    """Event emitted during continuous / timed active action lifecycle."""

    proposal_id: str = ""
    execution_id: str = ""
    active_action_id: str = ""
    intent: str = ""
    phase: str = "started"
    progress: float | None = None
    event_type: str = "active_action"

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "proposal_id": self.proposal_id,
            "execution_id": self.execution_id,
            "active_action_id": self.active_action_id,
            "intent": self.intent,
            "phase": self.phase,
        })
        if self.progress is not None:
            data["progress"] = self.progress
        return data


@dataclass(frozen=True)
class TurnProgressEvent(EventBase):
    """Public, non-reasoning progress for one Agent turn."""

    phase: str = "received"
    progress: float = 0.0
    message: str | None = None
    event_type: str = "turn_progress"

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"phase": self.phase, "progress": self.progress})
        if self.message is not None:
            data["message"] = self.message
        return data


@dataclass(frozen=True)
class ResponseChunkEvent(EventBase):
    """A normalized public response delta; never raw provider output."""

    stream_id: str = ""
    chunk_index: int = 0
    delta: str = ""
    content_kind: str = "answer"
    final: bool = False
    event_type: str = "response_chunk"

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "stream_id": self.stream_id,
                "chunk_index": self.chunk_index,
                "delta": self.delta,
                "content_kind": self.content_kind,
                "final": self.final,
            }
        )
        return data
