"""Stable Agent-side authorization boundary.

Core Agent code imports this package only. Vendor/service-specific transports
belong under ``vehicle_agent.integrations``.
"""

from .contract import (
    CONTRACT_VERSION,
    ContractValidationError,
    proposal_digest,
    validate_action_proposal,
    validate_guardrail_result,
)
from .ports import ActionAuthorizer, ConfirmationAuthorizer, MonitorAuthorizer

AuthorizationContractError = ContractValidationError
authorization_request_digest = proposal_digest
validate_authorization_result = validate_guardrail_result

__all__ = [
    "ActionAuthorizer",
    "AuthorizationContractError",
    "CONTRACT_VERSION",
    "ConfirmationAuthorizer",
    "MonitorAuthorizer",
    "authorization_request_digest",
    "validate_action_proposal",
    "validate_authorization_result",
]
