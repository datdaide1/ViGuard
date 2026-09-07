"""Confirmation package for Confirmation Lifecycle Integration (CNF-01).

Exports ConfirmationManager, PendingConfirmation, ConfirmationState, and ConfirmationResult.
"""

from vehicle_agent.confirmation.manager import ConfirmationManager
from vehicle_agent.confirmation.models import (
    ConfirmationResult,
    ConfirmationState,
    PendingConfirmation,
)

__all__ = [
    "ConfirmationState",
    "PendingConfirmation",
    "ConfirmationResult",
    "ConfirmationManager",
]
