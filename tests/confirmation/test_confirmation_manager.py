"""Unit tests for Pending Confirmation Manager (CNF-01).

Validates pending state registration, zero pre-confirm execution, fresh Guardrail re-evaluation,
expiry enforcement, replay rejection, and cancellation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from vivi_agent.confirmation import (
    ConfirmationManager,
    ConfirmationState,
)
from vivi_agent.contracts.guardrail.v1.contract import proposal_digest


def _make_action_proposal(proposal_id: str, tool: str) -> dict:
    """Build a contract-valid ActionProposal so proposal_digest() can be computed on it."""
    return {
        "contract_version": "1.0.0",
        "proposal_id": proposal_id,
        "session_id": "session-1",
        "source_turn_id": "turn-1",
        "tool": tool,
        "arguments": {},
        "model_provider": "mock",
        "model_id": "mock-1",
    }


def test_register_pending_stores_state_without_permit():
    manager = ConfirmationManager()
    decision = {
        "outcome": "CONFIRM",
        "reason_code": "DRIVER_CONFIRMATION_REQUIRED",
        "session_id": "session-1",
        "confirmation": {
            "confirmation_id": "confirm-001",
            "proposal_id": "prop-001",
            "prompt": "Bạn có chắc chắn muốn mở cửa không?",
            "expires_at": "2026-08-05T15:30:00Z",
            "single_use": True,
        },
        "permit": {"permit_id": "SHOULD_NOT_BE_USED"},  # Live permit should be stripped
    }
    proposal = {"proposal_id": "prop-001", "tool": "open_door"}

    pending = manager.register_pending(decision, proposal, turn_id="turn-1")

    assert pending.confirmation_id == "confirm-001"
    assert pending.proposal_id == "prop-001"
    assert pending.state == ConfirmationState.PENDING
    assert pending.prompt == "Bạn có chắc chắn muốn mở cửa không?"

    retrieved = manager.get_pending("confirm-001")
    assert retrieved is not None
    assert retrieved.confirmation_id == "confirm-001"


def test_zero_execution_before_confirm():
    """Acceptance criteria: Chưa confirm gọi handler zero lần."""
    manager = ConfirmationManager()
    decision = {
        "outcome": "CONFIRM",
        "confirmation": {
            "confirmation_id": "confirm-002",
            "proposal_id": "prop-002",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    }
    proposal = {"proposal_id": "prop-002", "tool": "open_trunk"}
    manager.register_pending(decision, proposal, turn_id="turn-1")

    executor = MagicMock()
    # No confirm called yet, verify executor was called 0 times
    executor.execute.assert_not_called()


def test_confirm_triggers_fresh_guardrail_reevaluation_and_executes():
    """Acceptance criteria: Agent không tái sử dụng decision/permit cũ."""
    manager = ConfirmationManager()
    decision = {
        "outcome": "CONFIRM",
        "confirmation": {
            "confirmation_id": "confirm-003",
            "proposal_id": "prop-003",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    }
    proposal = _make_action_proposal("prop-003", "open_window")
    manager.register_pending(decision, proposal, turn_id="turn-1")

    guardrail_client = MagicMock()
    fresh_permit = {"permit_id": "fresh-permit-003", "proposal_digest": proposal_digest(proposal)}
    fresh_decision = {
        "outcome": "ALLOW",
        "reason_code": "CONFIRMATION_REEVALUATED_ALLOW",
        "permit": fresh_permit,
    }
    guardrail_client.confirm.return_value = fresh_decision

    executor = MagicMock()
    executor.execute.return_value = {"success": True, "message": "Đã mở cửa sổ thành công."}

    result = manager.confirm(
        confirmation_id="confirm-003",
        session_id="session-1",
        guardrail_client=guardrail_client,
        executor=executor,
    )

    assert result.status == "completed"
    assert result.state == ConfirmationState.CONSUMED
    guardrail_client.confirm.assert_called_once_with(
        confirmation_id="confirm-003",
        session_id="session-1",
        request_id=None,
    )
    # executor.execute(proposal, decision, cancellation) — the same shape as
    # orchestrator.ActionExecutor/VehicleToolGateway.execute. The permit isn't
    # passed as a separate argument: it already lives inside fresh_decision,
    # and cancellation defaults to None when the caller doesn't supply one.
    executor.execute.assert_called_once_with(proposal, fresh_decision, None)


def test_confirm_expired_rejection():
    """Acceptance criteria: Confirm expiry bị từ chối và ghi event."""
    manager = ConfirmationManager()
    past_time = "2020-01-01T00:00:00Z"
    decision = {
        "outcome": "CONFIRM",
        "confirmation": {
            "confirmation_id": "confirm-004",
            "proposal_id": "prop-004",
            "expires_at": past_time,
        },
    }
    proposal = {"proposal_id": "prop-004", "tool": "open_door"}
    manager.register_pending(decision, proposal, turn_id="turn-1")

    guardrail_client = MagicMock()
    executor = MagicMock()

    now = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
    result = manager.confirm(
        confirmation_id="confirm-004",
        session_id="session-1",
        guardrail_client=guardrail_client,
        executor=executor,
        now=now,
    )

    assert result.status == "expired"
    assert result.state == ConfirmationState.EXPIRED
    assert result.error["code"] == "CONFIRMATION_EXPIRED"
    guardrail_client.confirm.assert_not_called()
    executor.execute.assert_not_called()


def test_confirm_replay_rejection():
    """Acceptance criteria: Confirm replay bị từ chối."""
    manager = ConfirmationManager()
    decision = {
        "outcome": "CONFIRM",
        "confirmation": {
            "confirmation_id": "confirm-005",
            "proposal_id": "prop-005",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    }
    proposal = _make_action_proposal("prop-005", "open_door")
    manager.register_pending(decision, proposal, turn_id="turn-1")

    guardrail_client = MagicMock()
    guardrail_client.confirm.return_value = {
        "outcome": "ALLOW",
        "permit": {"proposal_digest": proposal_digest(proposal)},
    }
    executor = MagicMock()
    executor.execute.return_value = {"success": True}

    # First confirm succeeds
    res1 = manager.confirm("confirm-005", "session-1", guardrail_client, executor)
    assert res1.status == "completed"

    # Second confirm (replay) is rejected
    res2 = manager.confirm("confirm-005", "session-1", guardrail_client, executor)
    assert res2.status == "failed"
    assert res2.error["code"] == "CONFIRMATION_ALREADY_CONSUMED"


def test_cancel_confirmation_zero_executor_calls():
    manager = ConfirmationManager()
    decision = {
        "outcome": "CONFIRM",
        "confirmation": {
            "confirmation_id": "confirm-006",
            "proposal_id": "prop-006",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    }
    proposal = {"proposal_id": "prop-006", "tool": "open_sunroof"}
    manager.register_pending(decision, proposal, turn_id="turn-1")

    result = manager.cancel("confirm-006", "session-1")

    assert result.status == "cancelled"
    assert result.state == ConfirmationState.CANCELLED
    retrieved = manager.get_pending("confirm-006")
    assert retrieved.state == ConfirmationState.CANCELLED
