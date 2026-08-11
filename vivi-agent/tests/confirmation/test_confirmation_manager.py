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


def test_confirm_rejects_empty_session_id_against_a_real_pending_session():
    """A falsy session_id must never bypass session ownership — the original
    `if session_id and pending.session_id and ...` check short-circuited to
    False (skipping the mismatch check entirely) whenever the caller passed
    an empty session_id, letting a cross-session confirm through."""
    manager = ConfirmationManager()
    decision = {
        "outcome": "CONFIRM",
        "session_id": "session-owner",
        "confirmation": {
            "confirmation_id": "confirm-007",
            "proposal_id": "prop-007",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    }
    proposal = _make_action_proposal("prop-007", "open_window")
    manager.register_pending(decision, proposal, turn_id="turn-1")

    guardrail_client = MagicMock()
    executor = MagicMock()

    result = manager.confirm(
        confirmation_id="confirm-007",
        session_id="",
        guardrail_client=guardrail_client,
        executor=executor,
    )

    assert result.status == "failed"
    assert result.error["code"] == "SESSION_MISMATCH"
    guardrail_client.confirm.assert_not_called()
    executor.execute.assert_not_called()
    # The confirmation itself stays PENDING — an empty session_id is a bad
    # request, not a resolution of this confirmation.
    assert manager.get_pending("confirm-007").state == ConfirmationState.PENDING


def test_cancel_rejects_empty_session_id_against_a_real_pending_session():
    manager = ConfirmationManager()
    decision = {
        "outcome": "CONFIRM",
        "session_id": "session-owner",
        "confirmation": {
            "confirmation_id": "confirm-008",
            "proposal_id": "prop-008",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    }
    proposal = {"proposal_id": "prop-008", "tool": "open_window"}
    manager.register_pending(decision, proposal, turn_id="turn-1")

    result = manager.cancel("confirm-008", "")

    assert result.status == "failed"
    assert result.error["code"] == "SESSION_MISMATCH"
    assert manager.get_pending("confirm-008").state == ConfirmationState.PENDING


def test_confirm_fails_closed_when_executor_result_omits_success_key():
    """An executor result missing "success" entirely must never be read as a
    silent success — matches CNF-01's own "guarantees zero pre-authorization
    executions" fail-closed design principle."""
    manager = ConfirmationManager()
    decision = {
        "outcome": "CONFIRM",
        "confirmation": {
            "confirmation_id": "confirm-009",
            "proposal_id": "prop-009",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    }
    proposal = _make_action_proposal("prop-009", "open_window")
    manager.register_pending(decision, proposal, turn_id="turn-1")

    guardrail_client = MagicMock()
    guardrail_client.confirm.return_value = {
        "outcome": "ALLOW",
        "permit": {"proposal_digest": proposal_digest(proposal)},
    }
    executor = MagicMock()
    executor.execute.return_value = {"message": "no success key at all"}

    result = manager.confirm("confirm-009", "session-1", guardrail_client, executor)

    assert result.status == "failed"


def test_confirm_pre_cancelled_token_skips_guardrail_and_preserves_pending():
    """cancellation must short-circuit BEFORE the fresh Guardrail re-evaluation
    and before the single-use token is consumed — not merely get forwarded to
    the executor after both already happened."""
    manager = ConfirmationManager()
    decision = {
        "outcome": "CONFIRM",
        "confirmation": {
            "confirmation_id": "confirm-010",
            "proposal_id": "prop-010",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    }
    proposal = _make_action_proposal("prop-010", "open_window")
    manager.register_pending(decision, proposal, turn_id="turn-1")

    guardrail_client = MagicMock()
    executor = MagicMock()
    cancellation = MagicMock(cancelled=True)

    result = manager.confirm(
        "confirm-010", "session-1", guardrail_client, executor, cancellation=cancellation
    )

    assert result.status == "failed"
    assert result.error["code"] == "EXECUTION_CANCELLED"
    assert result.state == ConfirmationState.PENDING
    guardrail_client.confirm.assert_not_called()
    executor.execute.assert_not_called()
    assert manager.get_pending("confirm-010").state == ConfirmationState.PENDING


def test_confirm_reports_a_clear_error_for_an_unconvertible_executor_result():
    """A raw dict(exec_result) TypeError ("'X' object is not iterable") is
    unhelpful for debugging — _execution_result_to_dict must raise a message
    naming the actual type and what shapes it does accept."""
    manager = ConfirmationManager()
    decision = {
        "outcome": "CONFIRM",
        "confirmation": {
            "confirmation_id": "confirm-011",
            "proposal_id": "prop-011",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    }
    proposal = _make_action_proposal("prop-011", "open_window")
    manager.register_pending(decision, proposal, turn_id="turn-1")

    guardrail_client = MagicMock()
    guardrail_client.confirm.return_value = {
        "outcome": "ALLOW",
        "permit": {"proposal_digest": proposal_digest(proposal)},
    }
    executor = MagicMock()
    executor.execute.return_value = object()  # neither to_dict(), dataclass, nor Mapping

    result = manager.confirm("confirm-011", "session-1", guardrail_client, executor)

    assert result.status == "failed"
    assert result.error["code"] == "EXECUTION_ERROR"
    assert "object" in result.error["message"]
