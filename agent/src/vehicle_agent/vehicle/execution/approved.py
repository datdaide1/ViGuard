"""Actuator execution for proposals already correlated with an upstream ALLOW."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from collections.abc import Callable

from ...orchestrator.orchestrator import CancellationToken, ExecutionResult, TurnError
from ...tools.mapping import MappedProposal
from .errors import ExecutionError, GatewayExecutionError, HandlerNotFoundError
from .gateway import HandlerRegistry


class ApprovedToolExecutor:
    """Invoke registered handlers without embedding Guardrail policy in Agent core."""

    def __init__(
        self,
        registry: HandlerRegistry,
        *,
        state_version_reader: Callable[[], int] | None = None,
        mutating_intents: frozenset[str] = frozenset(),
    ) -> None:
        self._registry = registry
        self._state_version_reader = state_version_reader
        self._mutating_intents = mutating_intents

    @property
    def registry(self) -> HandlerRegistry:
        return self._registry

    def execute_approved(
        self,
        proposal: Mapping[str, object],
        mapped: MappedProposal,
        cancellation: CancellationToken,
    ) -> ExecutionResult:
        execution_id = f"exec-{uuid.uuid4().hex[:12]}"
        if cancellation.cancelled:
            return self._failure(
                execution_id, "EXECUTION_CANCELLED", "Action execution was cancelled", False
            )

        tool_name = proposal.get("tool")
        intent = mapped.canonical_action.intent
        handler = self._registry.get(str(tool_name)) if tool_name else None
        handler = handler or self._registry.get(intent)
        if handler is None:
            error = HandlerNotFoundError(str(tool_name or intent))
            return self._failure(execution_id, error.code, error.message, error.retryable)

        try:
            output = handler(proposal)
            if not isinstance(output, Mapping):
                error = GatewayExecutionError(
                    "Actuator handler return value must be a dictionary or Mapping",
                    code="INVALID_HANDLER_OUTPUT",
                )
                return self._failure(execution_id, error.code, error.message, error.retryable)
            state_version = output.get("state_version")
            facts = output.get("facts", {})
            if intent in self._mutating_intents and self._state_version_reader is not None:
                actual_version = self._state_version_reader()
                if (
                    not isinstance(state_version, int)
                    or isinstance(state_version, bool)
                    or state_version != actual_version
                ):
                    return self._failure(
                        execution_id,
                        "EXECUTION_VERIFICATION_FAILED",
                        "Handler result does not match the current vehicle state version",
                        False,
                    )
            return ExecutionResult(
                success=True,
                execution_id=execution_id,
                message=str(output.get("message", "Tool execution succeeded")),
                state_version=(
                    state_version
                    if isinstance(state_version, int) and not isinstance(state_version, bool)
                    else None
                ),
                facts=facts if isinstance(facts, Mapping) else {},
            )
        except ExecutionError as exc:
            return self._failure(execution_id, exc.code, exc.message, exc.retryable)
        except Exception:
            return self._failure(
                execution_id, "EXECUTION_FAILED", "Actuator handler failed", False
            )

    @staticmethod
    def _failure(
        execution_id: str, code: str, message: str, retryable: bool
    ) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            execution_id=execution_id,
            message=message,
            error=TurnError(code, message, retryable),
        )


AgentToolExecutor = ApprovedToolExecutor
