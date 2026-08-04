"""Typed errors for vehicle tool execution and permit verification."""

from __future__ import annotations


class ExecutionError(Exception):
    """Base class for vehicle tool execution exceptions."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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

    def __init__(self, message: str, code: str = "EXECUTION_FAILED") -> None:
        super().__init__(code, message)
