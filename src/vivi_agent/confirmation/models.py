"""Typed domain models for Confirmation Lifecycle Integration (CNF-01).

Defines pending confirmation state, lifecycle transitions, and resolution results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConfirmationState(str, Enum):
    """Lifecycle state of a pending driver confirmation."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"
    REJECTED = "REJECTED"


@dataclass
class PendingConfirmation:
    """Immutable record of a pending confirmation requirement.

    Deliberately excludes live Guardrail permits; permits are only issued after
    fresh Guardrail re-evaluation upon confirmation.
    """

    confirmation_id: str
    proposal_id: str
    session_id: str
    turn_id: str
    request_id: str
    prompt: str
    expires_at: str
    single_use: bool = True
    state: ConfirmationState = ConfirmationState.PENDING
    action_proposal: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert pending record to dictionary representation."""
        return {
            "confirmation_id": self.confirmation_id,
            "proposal_id": self.proposal_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "request_id": self.request_id,
            "prompt": self.prompt,
            "expires_at": self.expires_at,
            "single_use": self.single_use,
            "state": self.state.value,
            "action_proposal": dict(self.action_proposal),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ConfirmationResult:
    """Typed outcome of a confirm or cancel resolution request."""

    status: str  # "completed", "blocked", "needs_confirmation", "cancelled", "expired", "failed"
    confirmation_id: str
    state: ConfirmationState
    decision: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert resolution result to dictionary representation."""
        return {
            "status": self.status,
            "confirmation_id": self.confirmation_id,
            "state": self.state.value,
            "decision": dict(self.decision) if self.decision else None,
            "execution": dict(self.execution) if self.execution else None,
            "error": dict(self.error) if self.error else None,
            "message": self.message,
        }
