"""Typed errors for vehicle tool execution and permit verification."""

from __future__ import annotations


class ExecutionError(Exception):
    """Base class for vehicle tool execution exceptions."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class PermitVerificationError(ExecutionError):
    """Base class for errors occurring during permit verification."""


class InvalidPermitError(PermitVerificationError):
    """Permit schema or decision mismatch error."""

    def __init__(self, message: str) -> None:
        super().__init__("INVALID_PERMIT", message)


class ExpiredPermitError(PermitVerificationError):
    """Permit expiration error."""

    def __init__(self, message: str = "Permit has expired") -> None:
        super().__init__("PERMIT_EXPIRED", message)


class SubstitutionAttackError(PermitVerificationError):
    """Permit proposal digest does not match the executed proposal."""

    def __init__(self, message: str = "Permit proposal digest mismatch (substitution attempt)") -> None:
        super().__init__("PROPOSAL_MISMATCH", message)


class ReplayAttackError(PermitVerificationError):
    """Permit has already been consumed (replay attempt)."""

    def __init__(self, message: str = "Permit has already been consumed (replay attempt)") -> None:
        super().__init__("PERMIT_REPLAYED", message)


class HandlerNotFoundError(ExecutionError):
    """No handler registered for the specified intent/tool."""

    def __init__(self, tool: str) -> None:
        super().__init__("HANDLER_NOT_FOUND", f"No actuator handler registered for tool/intent {tool!r}")


class GatewayExecutionError(ExecutionError):
    """Error during handler execution."""

    def __init__(self, message: str, code: str = "EXECUTION_FAILED", retryable: bool = False) -> None:
        super().__init__(code, message, retryable=retryable)


class InvalidDoorTargetError(ExecutionError):
    """Door target is missing or unsupported."""

    def __init__(self, message: str) -> None:
        super().__init__("INVALID_DOOR_TARGET", message)


class BehaviorConfigValidationError(ExecutionError):
    """Behavior configuration schema or parameter validation failure."""

    def __init__(self, message: str, code: str = "INVALID_BEHAVIOR_CONFIG") -> None:
        super().__init__(code, message)


class BehaviorReadinessError(ExecutionError):
    """Behavior readiness check failure for handler registry."""

    def __init__(self, message: str) -> None:
        super().__init__("BEHAVIOR_READINESS_FAILED", message)


