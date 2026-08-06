"""Pending Confirmation Manager (CNF-01).

Manages the lifecycle of pending confirmations, enforces single-use & expiry rules,
orchestrates fresh Guardrail re-evaluation, and guarantees zero pre-authorization executions.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from vivi_agent.confirmation.models import (
    ConfirmationResult,
    ConfirmationState,
    PendingConfirmation,
)

logger = logging.getLogger(__name__)


class ConfirmationManager:
    """Thread-safe manager for driver confirmation lifecycle."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingConfirmation] = {}
        self._lock = threading.Lock()

    def register_pending(
        self,
        decision: Mapping[str, Any],
        proposal: Mapping[str, Any],
        turn_id: str,
    ) -> PendingConfirmation:
        """Register a new pending confirmation from a Guardrail CONFIRM decision.

        Deliberately strips any live execution permits to ensure no execution can occur
        until explicit confirmation.
        """
        confirmation_info = decision.get("confirmation")
        if not isinstance(confirmation_info, Mapping):
            raise ValueError("Guardrail CONFIRM decision missing required confirmation payload")

        confirmation_id = str(confirmation_info["confirmation_id"])
        proposal_id = str(confirmation_info["proposal_id"])
        session_id = str(decision.get("session_id") or proposal.get("session_id", "unknown"))
        request_id = str(decision.get("request_id") or proposal.get("request_id", "unknown"))
        prompt = str(confirmation_info.get("prompt") or decision.get("reason_code") or "Yêu cầu cần xác nhận")
        expires_at = str(confirmation_info.get("expires_at", ""))
        single_use = bool(confirmation_info.get("single_use", True))

        pending = PendingConfirmation(
            confirmation_id=confirmation_id,
            proposal_id=proposal_id,
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            prompt=prompt,
            expires_at=expires_at,
            single_use=single_use,
            state=ConfirmationState.PENDING,
            action_proposal=dict(proposal),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        with self._lock:
            self._pending[confirmation_id] = pending

        logger.info("Registered pending confirmation %s for proposal %s", confirmation_id, proposal_id)
        return pending

    def get_pending(self, confirmation_id: str) -> PendingConfirmation | None:
        """Retrieve a pending confirmation record if it exists."""
        with self._lock:
            return self._pending.get(confirmation_id)

    def is_expired(self, pending: PendingConfirmation, now: datetime | None = None) -> bool:
        """Check if a pending confirmation has passed its expiration time."""
        if not pending.expires_at:
            return False

        try:
            exp_dt = datetime.fromisoformat(pending.expires_at.replace("Z", "+00:00"))
            current_dt = now or datetime.now(timezone.utc)
            if current_dt.tzinfo is None:
                current_dt = current_dt.replace(tzinfo=timezone.utc)
            return current_dt > exp_dt
        except (ValueError, TypeError):
            return False

    def confirm(
        self,
        confirmation_id: str,
        session_id: str,
        guardrail_client: Any,
        executor: Any = None,
        request_id: str | None = None,
        now: datetime | None = None,
    ) -> ConfirmationResult:
        """Resolve a pending confirmation via fresh Guardrail re-evaluation.

        Acceptance criteria:
        - Never reuses old decisions or permits.
        - Obtains fresh decision & single-use permit from Guardrail `confirm`.
        - Rejects expired, wrong session, or already consumed confirmations under lock.
        - Executes vehicle action ONLY if fresh decision outcome is `ALLOW`.
        """
        with self._lock:
            pending = self._pending.get(confirmation_id)

            if pending is None:
                return ConfirmationResult(
                    status="failed",
                    confirmation_id=confirmation_id,
                    state=ConfirmationState.REJECTED,
                    error={
                        "code": "CONFIRMATION_NOT_FOUND",
                        "message": f"Confirmation {confirmation_id} is unknown or invalid",
                    },
                    message="Yêu cầu xác nhận không tồn tại.",
                )

            if (
                session_id
                and pending.session_id
                and pending.session_id != "unknown"
                and session_id != pending.session_id
            ):
                return ConfirmationResult(
                    status="failed",
                    confirmation_id=confirmation_id,
                    state=pending.state,
                    error={
                        "code": "SESSION_MISMATCH",
                        "message": "Confirmation session ID does not match request session",
                    },
                    message="Phiên làm việc không trùng khớp.",
                )

            if pending.state is not ConfirmationState.PENDING:
                return ConfirmationResult(
                    status="failed",
                    confirmation_id=confirmation_id,
                    state=pending.state,
                    error={
                        "code": "CONFIRMATION_ALREADY_CONSUMED",
                        "message": f"Confirmation is already {pending.state.value}",
                    },
                    message="Yêu cầu xác nhận đã được xử lý trước đó.",
                )

            if self.is_expired(pending, now):
                pending.state = ConfirmationState.EXPIRED
                return ConfirmationResult(
                    status="expired",
                    confirmation_id=confirmation_id,
                    state=ConfirmationState.EXPIRED,
                    error={
                        "code": "CONFIRMATION_EXPIRED",
                        "message": "Confirmation period has expired",
                    },
                    message="Yêu cầu xác nhận đã hết hạn.",
                )

            # Mark in-flight / confirmed state under lock to prevent concurrent re-evaluation
            pending.state = ConfirmationState.CONFIRMED

        # Re-evaluate with Guardrail client to get a fresh decision & permit
        try:
            fresh_decision = guardrail_client.confirm(
                confirmation_id=confirmation_id,
                session_id=session_id,
                request_id=request_id,
            )
        except Exception as exc:
            logger.error("Guardrail confirmation re-evaluation failed: %s", exc)
            with self._lock:
                pending.state = ConfirmationState.PENDING  # Revert on transport error
            return ConfirmationResult(
                status="failed",
                confirmation_id=confirmation_id,
                state=ConfirmationState.PENDING,
                error={
                    "code": getattr(exc, "code", "GUARDRAIL_ERROR"),
                    "message": str(exc),
                },
                message="Lỗi khi xác minh với hệ thống Guardrail.",
            )

        with self._lock:
            pending.state = ConfirmationState.CONSUMED

        fresh_outcome = fresh_decision.get("outcome")
        outcome_str = str(fresh_outcome) if fresh_outcome is not None else ""

        # Only execute if fresh decision outcome is ALLOW
        if outcome_str == "ALLOW":
            fresh_permit = fresh_decision.get("permit")
            if executor is not None:
                try:
                    exec_result = executor.execute(pending.action_proposal, fresh_decision, fresh_permit)
                    exec_dict = exec_result.to_dict() if hasattr(exec_result, "to_dict") else dict(exec_result)
                    exec_success = exec_dict.get("success", True)
                    return ConfirmationResult(
                        status="completed" if exec_success else "failed",
                        confirmation_id=confirmation_id,
                        state=ConfirmationState.CONSUMED,
                        decision=dict(fresh_decision),
                        execution=exec_dict,
                        message=str(exec_dict.get("message") or "Đã thực hiện sau khi xác nhận."),
                    )
                except Exception as exc:
                    return ConfirmationResult(
                        status="failed",
                        confirmation_id=confirmation_id,
                        state=ConfirmationState.CONSUMED,
                        decision=dict(fresh_decision),
                        error={"code": "EXECUTION_ERROR", "message": str(exc)},
                        message="Không thể thực hiện thao tác sau khi xác nhận.",
                    )

            return ConfirmationResult(
                status="completed",
                confirmation_id=confirmation_id,
                state=ConfirmationState.CONSUMED,
                decision=dict(fresh_decision),
                message="Xác nhận thành công.",
            )

        # Fresh decision blocked or needs further confirmation
        status_name = "blocked" if outcome_str.startswith("BLOCK") else "needs_confirmation"
        return ConfirmationResult(
            status=status_name,
            confirmation_id=confirmation_id,
            state=ConfirmationState.CONSUMED,
            decision=dict(fresh_decision),
            message="Yêu cầu bị từ chối sau khi re-evaluate.",
        )

    def cancel(
        self,
        confirmation_id: str,
        session_id: str,
        now: datetime | None = None,
    ) -> ConfirmationResult:
        """Cancel a pending confirmation requirement.

        Guarantees actuator/handler is called ZERO times.
        """
        with self._lock:
            pending = self._pending.get(confirmation_id)

            if pending is None:
                return ConfirmationResult(
                    status="failed",
                    confirmation_id=confirmation_id,
                    state=ConfirmationState.REJECTED,
                    error={
                        "code": "CONFIRMATION_NOT_FOUND",
                        "message": f"Confirmation {confirmation_id} is unknown or invalid",
                    },
                    message="Yêu cầu xác nhận không tồn tại.",
                )

            if (
                session_id
                and pending.session_id
                and pending.session_id != "unknown"
                and session_id != pending.session_id
            ):
                return ConfirmationResult(
                    status="failed",
                    confirmation_id=confirmation_id,
                    state=pending.state,
                    error={
                        "code": "SESSION_MISMATCH",
                        "message": "Confirmation session ID does not match request session",
                    },
                    message="Phiên làm việc không trùng khớp.",
                )

            if pending.state is not ConfirmationState.PENDING:
                return ConfirmationResult(
                    status="failed",
                    confirmation_id=confirmation_id,
                    state=pending.state,
                    error={
                        "code": "CONFIRMATION_ALREADY_CONSUMED",
                        "message": f"Confirmation is already {pending.state.value}",
                    },
                    message="Yêu cầu xác nhận đã được xử lý trước đó.",
                )

            if self.is_expired(pending, now):
                pending.state = ConfirmationState.EXPIRED
                return ConfirmationResult(
                    status="expired",
                    confirmation_id=confirmation_id,
                    state=ConfirmationState.EXPIRED,
                    error={
                        "code": "CONFIRMATION_EXPIRED",
                        "message": "Confirmation period has expired",
                    },
                    message="Yêu cầu xác nhận đã hết hạn.",
                )

            pending.state = ConfirmationState.CANCELLED

        return ConfirmationResult(
            status="cancelled",
            confirmation_id=confirmation_id,
            state=ConfirmationState.CANCELLED,
            message="Yêu cầu đã được hủy bỏ thành công.",
        )
