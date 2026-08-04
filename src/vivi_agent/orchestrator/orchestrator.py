"""Fail-closed orchestration of one ViVi Agent message turn.

This module owns sequencing only.  Guardrail authorization and vehicle
execution are injected ports so the orchestrator cannot mint permits or reach
an action-handler registry.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol

from ..contracts.guardrail.v1.contract import (
    CONTRACT_VERSION,
    ContractValidationError,
    validate_guardrail_result,
)
from ..model_providers import (
    ModelErrorCode,
    ModelProviderError,
    ModelProviderRouter,
    ProposalKind,
    TurnBinding,
)
from ..tools.mapping import ToolMapper, UnsupportedToolMappingError


class TurnState(str, Enum):
    RECEIVED = "received"
    RESOLVING = "resolving"
    CLARIFICATION = "clarification"
    PROPOSED = "proposed"
    AUTHORIZING = "authorizing"
    BLOCKED = "blocked"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TurnStatus(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    NEEDS_CONFIRMATION = "needs_confirmation"
    FAILED = "failed"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class TurnError:
    code: str
    message: str
    retryable: bool = False

    def to_dict(self) -> dict[str, str | bool]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


@dataclass(frozen=True)
class TurnRequest:
    session_id: str
    turn_id: str
    request_id: str
    message: str
    messages: Sequence[Mapping[str, str]] = ()


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    execution_id: str
    message: str
    state_version: int | None = None
    facts: Mapping[str, Any] = field(default_factory=dict)
    error: TurnError | None = None

    def __post_init__(self) -> None:
        if self.success and self.error is not None:
            raise ValueError("successful execution cannot contain an error")
        if not self.success and self.error is None:
            raise ValueError("failed execution requires a typed error")
        object.__setattr__(self, "facts", MappingProxyType(dict(self.facts)))


@dataclass(frozen=True)
class TurnResult:
    status: TurnStatus
    state: TurnState
    message: str
    proposal_id: str | None = None
    execution_id: str | None = None
    state_version: int | None = None
    rule_id: str | None = None
    reason: str | None = None
    confirmation_id: str | None = None
    expires_at: str | None = None
    error: TurnError | None = None
    degraded_capability: str | None = None
    retryable: bool | None = None
    trace: tuple[TurnState, ...] = ()


class GuardrailClient(Protocol):
    """Authorization port implemented by GRD-ADP-01."""

    def evaluate(self, proposal: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ActionExecutor(Protocol):
    """Execution port implemented by the vehicle gateway tasks."""

    def execute(
        self,
        proposal: Mapping[str, Any],
        decision: Mapping[str, Any],
        cancellation: "CancellationToken",
    ) -> ExecutionResult: ...


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise TurnCancelled


class TurnCancelled(RuntimeError):
    pass


class AgentOrchestrator:
    """Run a single, sequential state-changing proposal through its gates."""

    def __init__(
        self,
        *,
        model_router: ModelProviderRouter,
        mapper: ToolMapper,
        guardrail: GuardrailClient,
        executor: ActionExecutor,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._model_router = model_router
        self._mapper = mapper
        self._guardrail = guardrail
        self._executor = executor
        self._id_factory = id_factory or (lambda prefix: f"{prefix}-{uuid.uuid4().hex}")
        self._session_locks_guard = threading.Lock()
        self._session_locks: dict[str, tuple[threading.Lock, int]] = {}

    def handle_message(
        self, request: TurnRequest, cancellation: CancellationToken | None = None
    ) -> TurnResult:
        token = cancellation or CancellationToken()
        trace = [TurnState.RECEIVED]
        proposal_id: str | None = None
        try:
            self._validate_request(request)
            token.raise_if_cancelled()
            trace.append(TurnState.RESOLVING)
            binding = TurnBinding()
            messages = [*request.messages, {"role": "user", "content": request.message}]
            proposal = self._model_router.propose_tool(messages, binding)
            token.raise_if_cancelled()

            if proposal.kind is not ProposalKind.ACTION:
                trace.append(TurnState.CLARIFICATION)
                return TurnResult(
                    TurnStatus.COMPLETED,
                    TurnState.CLARIFICATION,
                    proposal.text or "Vui lòng làm rõ yêu cầu.",
                    trace=tuple(trace),
                )

            proposal_id = self._id_factory("proposal")
            action_proposal = {
                "contract_version": CONTRACT_VERSION,
                "proposal_id": proposal_id,
                "session_id": request.session_id,
                "source_turn_id": request.turn_id,
                "tool": proposal.tool_name,
                "arguments": dict(proposal.arguments or {}),
                "model_provider": proposal.metadata.provider,
                "model_id": proposal.metadata.model_id,
            }
            mapped = self._mapper.map_proposal(action_proposal)
            trace.append(TurnState.PROPOSED)
            token.raise_if_cancelled()

            with self._state_change_lock(request.session_id):
                token.raise_if_cancelled()
                trace.append(TurnState.AUTHORIZING)
                decision = self._guardrail.evaluate(action_proposal)
                validate_guardrail_result(decision)
                self._validate_decision_correlation(
                    decision, proposal_id, mapped.canonical_action.intent
                )
                token.raise_if_cancelled()

                if decision["kind"] == "error":
                    error = decision["error"]
                    return self._failed(
                        trace,
                        proposal_id,
                        TurnError(error["code"], error["message"], error["retryable"]),
                    )

                outcome = decision["outcome"]
                if outcome == "ALLOW":
                    if decision["permit"]["proposal_digest"] != mapped.proposal_digest:
                        raise ContractValidationError(
                            "INVALID_PERMIT", "permit digest does not match the mapped proposal"
                        )
                    binding.start_side_effect()
                    trace.append(TurnState.EXECUTING)
                    execution = self._executor.execute(action_proposal, decision, token)
                    token.raise_if_cancelled()
                    if not execution.success:
                        return self._failed(trace, proposal_id, execution.error, execution.execution_id)
                    trace.append(TurnState.COMPLETED)
                    message = self._grounded_success_message(execution)
                    return TurnResult(
                        TurnStatus.COMPLETED,
                        TurnState.COMPLETED,
                        message,
                        proposal_id=proposal_id,
                        execution_id=execution.execution_id,
                        state_version=execution.state_version,
                        trace=tuple(trace),
                    )

                if outcome == "CONFIRM":
                    confirmation = self._validate_confirmation(decision, proposal_id)
                    trace.append(TurnState.AWAITING_CONFIRMATION)
                    return TurnResult(
                        TurnStatus.NEEDS_CONFIRMATION,
                        TurnState.AWAITING_CONFIRMATION,
                        confirmation.get("prompt") or "Yêu cầu cần được xác nhận.",
                        proposal_id=proposal_id,
                        confirmation_id=confirmation["confirmation_id"],
                        expires_at=confirmation["expires_at"],
                        trace=tuple(trace),
                    )

                if outcome == "ANSWER":
                    answer = decision.get("answer")
                    if not isinstance(answer, Mapping) or answer.get("grounded") is not True:
                        raise ContractValidationError(
                            "MALFORMED_GUARDRAIL_RESPONSE", "ANSWER requires typed grounded facts"
                        )
                    response = self._model_router.compose_response(
                        {
                            "outcome": "ANSWER",
                            "facts": dict(answer.get("facts", {})),
                            "state_version": decision["state_version"],
                        },
                        binding,
                    )
                    if response.kind is not ProposalKind.RESPONSE or not response.text:
                        raise ContractValidationError(
                            "UNGROUNDED_RESPONSE", "response composer returned no grounded response"
                        )
                    trace.append(TurnState.COMPLETED)
                    return TurnResult(
                        TurnStatus.COMPLETED,
                        TurnState.COMPLETED,
                        response.text,
                        proposal_id=proposal_id,
                        state_version=decision["state_version"],
                        trace=tuple(trace),
                    )

                trace.append(TurnState.BLOCKED)
                return TurnResult(
                    TurnStatus.BLOCKED,
                    TurnState.BLOCKED,
                    "Yêu cầu không được phép thực thi.",
                    proposal_id=proposal_id,
                    state_version=decision["state_version"],
                    rule_id=decision["rule_id"],
                    reason=decision["reason_code"],
                    trace=tuple(trace),
                )
        except TurnCancelled:
            trace.append(TurnState.CANCELLED)
            return self._failed(
                trace, proposal_id, TurnError("TURN_CANCELLED", "Turn was cancelled", False)
            )
        except ModelProviderError as exc:
            trace.append(TurnState.FAILED)
            return TurnResult(
                TurnStatus.DEGRADED,
                TurnState.FAILED,
                "Tạm thời không thể xử lý yêu cầu.",
                proposal_id=proposal_id,
                reason=exc.code.value,
                degraded_capability="intent_resolution",
                retryable=exc.retryable,
                trace=tuple(trace),
            )
        except (ContractValidationError, UnsupportedToolMappingError) as exc:
            code = getattr(exc, "code", "ORCHESTRATION_VALIDATION_ERROR")
            return self._failed(trace, proposal_id, TurnError(code, str(exc), False))
        except Exception:
            # Guardrail transport failures and unknown execution boundary errors
            # are deliberately collapsed without leaking internals.
            return self._failed(
                trace,
                proposal_id,
                TurnError("ORCHESTRATION_DEPENDENCY_ERROR", "A required safety dependency failed", False),
            )

    @staticmethod
    def _validate_request(request: TurnRequest) -> None:
        for name in ("session_id", "turn_id", "request_id"):
            value = getattr(request, name)
            if not isinstance(value, str) or not value or len(value) > 128:
                raise ValueError(f"{name} must be a non-empty identifier")
        if not isinstance(request.message, str) or not request.message.strip():
            raise ValueError("message must be non-empty")

    @staticmethod
    def _validate_decision_correlation(
        decision: Mapping[str, Any], proposal_id: str, mapped_intent: str
    ) -> None:
        if decision["kind"] != "decision":
            return
        if decision["proposal_id"] != proposal_id:
            raise ContractValidationError(
                "DECISION_CORRELATION_MISMATCH", "Guardrail decision references another proposal"
            )
        if decision["intent"] != mapped_intent:
            raise ContractValidationError(
                "DECISION_INTENT_MISMATCH", "Guardrail decision references another intent"
            )

    @staticmethod
    def _validate_confirmation(
        decision: Mapping[str, Any], proposal_id: str
    ) -> Mapping[str, Any]:
        confirmation = decision.get("confirmation")
        if not isinstance(confirmation, Mapping):
            raise ContractValidationError(
                "MALFORMED_GUARDRAIL_RESPONSE", "CONFIRM requires confirmation details"
            )
        confirmation_id = confirmation.get("confirmation_id")
        if not isinstance(confirmation_id, str) or not 1 <= len(confirmation_id) <= 128:
            raise ContractValidationError(
                "MALFORMED_GUARDRAIL_RESPONSE", "confirmation_id must be an identifier"
            )
        if confirmation.get("proposal_id") != proposal_id:
            raise ContractValidationError(
                "CONFIRMATION_CORRELATION_MISMATCH", "confirmation references another proposal"
            )
        if confirmation.get("single_use") is not True:
            raise ContractValidationError(
                "MALFORMED_GUARDRAIL_RESPONSE", "confirmation must be single-use"
            )
        expires_at = confirmation.get("expires_at")
        if not isinstance(expires_at, str):
            raise ContractValidationError(
                "MALFORMED_GUARDRAIL_RESPONSE", "confirmation expiry must be a date-time"
            )
        try:
            parsed_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractValidationError(
                "MALFORMED_GUARDRAIL_RESPONSE", "confirmation expiry must be a date-time"
            ) from exc
        if parsed_expiry.tzinfo is None:
            raise ContractValidationError(
                "MALFORMED_GUARDRAIL_RESPONSE", "confirmation expiry must include a timezone"
            )
        prompt = confirmation.get("prompt")
        if prompt is not None and (not isinstance(prompt, str) or not prompt.strip()):
            raise ContractValidationError(
                "MALFORMED_GUARDRAIL_RESPONSE", "confirmation prompt must be non-empty text"
            )
        return confirmation

    @contextmanager
    def _state_change_lock(self, session_id: str):
        """Serialize one session without retaining inactive session IDs."""

        with self._session_locks_guard:
            entry = self._session_locks.get(session_id)
            lock, users = entry if entry is not None else (threading.Lock(), 0)
            self._session_locks[session_id] = (lock, users + 1)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            with self._session_locks_guard:
                current_lock, current_users = self._session_locks[session_id]
                if current_users == 1:
                    del self._session_locks[session_id]
                else:
                    self._session_locks[session_id] = (current_lock, current_users - 1)

    @staticmethod
    def _grounded_success_message(execution: ExecutionResult) -> str:
        # The execution port is the only authority allowed to assert success.
        return execution.message

    @staticmethod
    def _failed(
        trace: list[TurnState],
        proposal_id: str | None,
        error: TurnError | None,
        execution_id: str | None = None,
    ) -> TurnResult:
        typed_error = error or TurnError("EXECUTION_FAILED", "Execution failed", False)
        if not trace or trace[-1] is not TurnState.FAILED:
            trace.append(TurnState.FAILED)
        return TurnResult(
            TurnStatus.FAILED,
            TurnState.FAILED,
            "Không thể hoàn tất yêu cầu.",
            proposal_id=proposal_id,
            execution_id=execution_id,
            error=typed_error,
            trace=tuple(trace),
        )
