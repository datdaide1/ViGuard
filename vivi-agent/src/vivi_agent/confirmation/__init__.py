"""Confirmation package for Confirmation Lifecycle Integration (CNF-01).

Exports ConfirmationManager, PendingConfirmation, ConfirmationState, and ConfirmationResult.
"""

from vivi_agent.confirmation.manager import ConfirmationManager
from vivi_agent.confirmation.models import (
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
