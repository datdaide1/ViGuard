"""Vehicle Tool Gateway implementation."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from vehicle_agent.orchestrator.orchestrator import ExecutionResult, TurnError
from .errors import (
    ExecutionError,
    GatewayExecutionError,
    HandlerNotFoundError,
    PermitVerificationError,
    ReplayAttackError,
)
from .verifier import PermitStore, PermitVerifier

ActuatorHandler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class HandlerRegistry:
    """Registry mapping tool or intent names to actuator handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, ActuatorHandler] = {}

    def register(self, tool_or_intent: str, handler: ActuatorHandler) -> None:
        """Register an actuator handler for a tool or intent name."""
        if not tool_or_intent or not isinstance(tool_or_intent, str):
            raise ValueError("tool_or_intent must be a non-empty string")
        self._handlers[tool_or_intent] = handler

    def get(self, tool_or_intent: str) -> ActuatorHandler | None:
        """Retrieve handler registered for tool or intent name."""
        return self._handlers.get(tool_or_intent)

    def unregister(self, tool_or_intent: str) -> None:
        """Remove a handler registration."""
        self._handlers.pop(tool_or_intent, None)


class VehicleToolGateway:
    """Single execution boundary for vehicle tools.

    Guarantees fail-closed authorization verification using Guardrail permits
    before delegating to registered actuator handlers.
    """

    def __init__(
        self,
        verifier: PermitVerifier | None = None,
        registry: HandlerRegistry | None = None,
    ) -> None:
        self._verifier = verifier or PermitVerifier()
        self._registry = registry or HandlerRegistry()

    @property
    def verifier(self) -> PermitVerifier:
        return self._verifier

    @property
    def store(self) -> PermitStore:
        return self._verifier.store

    @property
    def registry(self) -> HandlerRegistry:
        return self._registry

    def execute(
        self,
        proposal: Mapping[str, Any],
        decision_or_permit: Mapping[str, Any],
        cancellation: Any = None,
        current_time: datetime | None = None,
    ) -> ExecutionResult:
        """Execute authorized vehicle tool call.

        Parameters
        ----------
        proposal:
            Canonical ActionProposal dictionary.
        decision_or_permit:
            Either a full Guardrail decision object (containing outcome and permit)
            or an ActionPermit object directly.
        cancellation:
            Optional cancellation token (e.g. CancellationToken with .cancelled property).
        current_time:
            Optional override for current timestamp (for deterministic testing).

        Returns
        -------
        ExecutionResult:
            Typed result containing success flag, execution_id, message, state_version,
            facts, or error details.
        """
        with self._verifier.store.lifecycle_boundary():
            return self._execute_under_lifecycle_gate(
                proposal,
                decision_or_permit,
                cancellation=cancellation,
                current_time=current_time,
            )

    def _execute_under_lifecycle_gate(
        self,
        proposal: Mapping[str, Any],
        decision_or_permit: Mapping[str, Any],
        cancellation: Any = None,
        current_time: datetime | None = None,
    ) -> ExecutionResult:
        """Execute while holding the PermitStore lifecycle boundary."""
        execution_id = f"exec-{uuid.uuid4().hex[:12]}"

        # Step 0: Check cancellation prior to processing
        if cancellation is not None and getattr(cancellation, "cancelled", False):
            return ExecutionResult(
                success=False,
                execution_id=execution_id,
                message="Execution cancelled",
                error=TurnError(
                    code="EXECUTION_CANCELLED",
                    message="Action execution was cancelled prior to completion",
                    retryable=False,
                ),
            )

        # Extract permit and decision context
        decision: Mapping[str, Any] | None = None
        permit: Mapping[str, Any] | None = None

        if isinstance(decision_or_permit, Mapping):
            kind = decision_or_permit.get("kind")
            if kind == "decision":
                decision = decision_or_permit
                outcome = decision.get("outcome")
                if outcome != "ALLOW":
                    return ExecutionResult(
                        success=False,
                        execution_id=execution_id,
                        message=f"Execution denied: policy outcome is {outcome}",
                        error=TurnError(
                            code="EXECUTION_DENIED",
                            message=f"Policy outcome {outcome!r} does not permit execution",
                            retryable=False,
                            # Preserve policy diagnostics for internal callers
                            # (logs, event pipeline) without widening the
                            # UI-facing error contract — see TurnError.details.
                            details={
                                "rule_id": decision.get("rule_id"),
                                "reason_code": decision.get("reason_code"),
                            },
                        ),
                    )
                permit = decision.get("permit")
                if not isinstance(permit, Mapping):
                    return ExecutionResult(
                        success=False,
                        execution_id=execution_id,
                        message="Execution denied: ALLOW decision missing permit",
                        error=TurnError(
                            code="INVALID_PERMIT",
                            message="ALLOW decision missing permit object",
                            retryable=False,
                        ),
                    )
            elif "permit_id" in decision_or_permit:
                permit = decision_or_permit
            else:
                return ExecutionResult(
                    success=False,
                    execution_id=execution_id,
                    message="Execution denied: Invalid decision or permit payload",
                    error=TurnError(
                        code="INVALID_PERMIT",
                        message="Payload is neither a decision nor an ActionPermit",
                        retryable=False,
                    ),
                )
        else:
            return ExecutionResult(
                success=False,
                execution_id=execution_id,
                message="Execution denied: Missing decision/permit payload",
                error=TurnError(
                    code="INVALID_PERMIT",
                    message="Missing decision or permit",
                    retryable=False,
                ),
            )

        # Step 1: Verify permit (fail closed, 0 handler call count on failure)
        try:
            self._verifier.verify(
                proposal=proposal,
                permit=permit,
                decision=decision,
                current_time=current_time,
            )
        except PermitVerificationError as exc:
            return ExecutionResult(
                success=False,
                execution_id=execution_id,
                message=f"Permit verification failed: {exc.message}",
                error=TurnError(
                    code=exc.code,
                    message=exc.message,
                    retryable=exc.retryable,
                ),
            )

        # Step 2: Atomic permit consumption (mark used in store)
        permit_id = permit["permit_id"]
        try:
            self._verifier.store.mark_used(permit_id)
        except ReplayAttackError as exc:
            return ExecutionResult(
                success=False,
                execution_id=execution_id,
                message=f"Permit consumption failed: {exc.message}",
                error=TurnError(
                    code=exc.code,
                    message=exc.message,
                    retryable=exc.retryable,
                ),
            )

        # Step 3: Lookup handler by tool or intent
        tool_name = proposal.get("tool")
        intent_name = permit.get("intent")

        handler = self._registry.get(tool_name) or (self._registry.get(intent_name) if intent_name else None)
        if handler is None:
            err = HandlerNotFoundError(tool_name or intent_name or "unknown")
            return ExecutionResult(
                success=False,
                execution_id=execution_id,
                message=err.message,
                error=TurnError(
                    code=err.code,
                    message=err.message,
                    retryable=err.retryable,
                ),
            )

        # Step 4: Invoke actuator handler
        try:
            handler_output = handler(proposal)
            if not isinstance(handler_output, Mapping):
                err = GatewayExecutionError(
                    "Actuator handler return value must be a dictionary or Mapping",
                    code="INVALID_HANDLER_OUTPUT",
                )
                return ExecutionResult(
                    success=False,
                    execution_id=execution_id,
                    message=err.message,
                    error=TurnError(
                        code=err.code,
                        message=err.message,
                        retryable=err.retryable,
                    ),
                )

            state_version = handler_output.get("state_version")
            facts = handler_output.get("facts", {})
            msg = handler_output.get("message", "Tool execution succeeded")

            return ExecutionResult(
                success=True,
                execution_id=execution_id,
                message=str(msg),
                state_version=state_version if isinstance(state_version, int) else None,
                facts=facts if isinstance(facts, Mapping) else {},
            )
        except ExecutionError as exc:
            return ExecutionResult(
                success=False,
                execution_id=execution_id,
                message=f"Handler execution error: {exc.message}",
                error=TurnError(
                    code=exc.code,
                    message=exc.message,
                    retryable=exc.retryable,
                ),
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                execution_id=execution_id,
                message=f"Handler execution error: {exc}",
                error=TurnError(
                    code="EXECUTION_FAILED",
                    message=str(exc),
                    retryable=False,
                ),
            )
