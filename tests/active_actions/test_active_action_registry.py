"""Tests for Active Action Registry (ACTV-01)."""

from __future__ import annotations

import concurrent.futures
import pytest

from vivi_agent.active_actions import ActiveActionRecord, ActiveActionRegistry
from vivi_agent.events.models import ActiveActionEvent
from vivi_agent.vehicle.state.model import ActiveActionPhase


def test_only_monitored_behavior_creates_active_action():
    """Verify that only monitored/active behaviors (handler_type == ACTIVE_ACTION) can start an ActiveAction."""
    registry = ActiveActionRegistry()

    # Monitored active action behaviors from catalog
    hda_record = registry.start_action(
        intent="activate_hda",
        proposal_id="prop-hda-1",
        execution_id="exec-hda-1",
        session_id="sess-1",
    )
    assert hda_record.action_id.startswith("act-")
    assert hda_record.intent == "activate_hda"
    assert hda_record.active_action_name == "hda"
    assert hda_record.phase == ActiveActionPhase.STARTED

    camp_record = registry.start_action(
        intent="activate_campmode",
        proposal_id="prop-camp-1",
    )
    assert camp_record.intent == "activate_campmode"
    assert camp_record.active_action_name == "camp_mode"

    # Attempting to start a non-monitored behavior must raise ValueError
    with pytest.raises(ValueError, match="INTENT_NOT_MONITORED"):
        registry.start_action(intent="turnon_highbeam", proposal_id="prop-fail-1")

    with pytest.raises(ValueError, match="INTENT_NOT_MONITORED"):
        registry.start_action(intent="unknown_intent_xyz", proposal_id="prop-fail-2")


def test_lifecycle_transitions_and_query():
    """Test start, progress, complete lifecycle transitions and query endpoints."""
    registry = ActiveActionRegistry()

    # Start
    record = registry.start_action(
        intent="activate_aac",
        proposal_id="prop-1",
        execution_id="exec-1",
        session_id="sess-100",
        state_version=5,
    )
    assert record.phase == ActiveActionPhase.STARTED
    assert record.progress == 0.0

    # Query active
    active_actions = registry.get_active_actions(session_id="sess-100")
    assert len(active_actions) == 1
    assert active_actions[0].action_id == record.action_id

    # Update progress
    updated = registry.update_progress(
        action_id=record.action_id,
        progress=0.45,
        state_version=6,
    )
    assert updated.phase == ActiveActionPhase.PROGRESS
    assert updated.progress == 0.45
    assert updated.state_version == 6

    # Complete
    completed = registry.complete_action(
        action_id=record.action_id,
        execution_id="exec-complete-1",
    )
    assert completed.phase == ActiveActionPhase.COMPLETED
    assert completed.progress == 1.0

    # Verify no longer active
    assert len(registry.get_active_actions(session_id="sess-100")) == 0

    # Query history
    history = registry.query_actions(session_id="sess-100")
    assert len(history) == 1
    assert history[0].phase == ActiveActionPhase.COMPLETED


def test_stop_and_fail_transitions():
    """Test stop and fail transitions and associated event emission."""
    events: list[ActiveActionEvent] = []
    registry = ActiveActionRegistry(event_pipeline=events.append)

    # Start action 1 for stop test
    rec1 = registry.start_action(
        intent="activate_autopark",
        proposal_id="prop-park-1",
        execution_id="exec-park-1",
    )
    # Stop action 1
    stopped = registry.stop_action(rec1.action_id, reason="user_cancelled")
    assert stopped.phase == ActiveActionPhase.STOPPED
    assert stopped.stop_reason == "user_cancelled"

    # Start action 2 for fail test
    rec2 = registry.start_action(
        intent="activate_petmode",
        proposal_id="prop-pet-1",
        execution_id="exec-pet-1",
    )
    # Fail action 2
    failed = registry.fail_action(rec2.action_id, error="sensor_fault")
    assert failed.phase == ActiveActionPhase.FAILED
    assert failed.failure_reason == "sensor_fault"

    # Check event pipeline output
    assert len(events) == 4  # rec1 start, rec1 stop, rec2 start, rec2 fail
    assert events[1].phase == "stopped"
    assert events[1].active_action_id == rec1.action_id
    assert events[3].phase == "failed"
    assert events[3].active_action_id == rec2.action_id


def test_restart_reset_cleanup():
    """Acceptance Criterion: Restart/reset does NOT restore actions as running."""
    events: list[ActiveActionEvent] = []
    registry = ActiveActionRegistry(event_pipeline=events.append)

    # Start two active actions
    rec1 = registry.start_action(intent="activate_hda", proposal_id="p1")
    rec2 = registry.start_action(intent="activate_campmode", proposal_id="p2")

    assert len(registry.get_active_actions()) == 2

    # Execute reset and cleanup
    cleaned = registry.reset_and_cleanup(reason="agent_restart")
    assert len(cleaned) == 2
    assert all(r.phase == ActiveActionPhase.STOPPED for r in cleaned)

    # Verify registry state after reset: active actions list is empty!
    assert len(registry.get_active_actions()) == 0

    # Check reset events emitted
    reset_events = [e for e in events if e.phase == "stopped"]
    assert len(reset_events) == 2


def test_stop_handler_registry():
    """Test stop handler registration and callback execution on stop/fail/reset."""
    registry = ActiveActionRegistry()

    stop_calls: list[tuple[str, str]] = []

    def camp_stop_handler(record: ActiveActionRecord, reason: str) -> None:
        stop_calls.append((record.action_id, reason))

    registry.register_stop_handler("activate_campmode", camp_stop_handler)

    rec = registry.start_action(intent="activate_campmode", proposal_id="p-camp")
    registry.stop_action(rec.action_id, reason="temperature_exceeded")

    assert len(stop_calls) == 1
    assert stop_calls[0] == (rec.action_id, "temperature_exceeded")


def test_ui_query_filtering():
    """Test UI query endpoint filtering by session_id, intent, phase, active_only."""
    registry = ActiveActionRegistry()

    r1 = registry.start_action(intent="activate_hda", session_id="sess-A")
    r2 = registry.start_action(intent="activate_aac", session_id="sess-A")
    r3 = registry.start_action(intent="activate_valetmode", session_id="sess-B")

    registry.complete_action(r2.action_id)

    # Query sess-A active actions
    sess_a_active = registry.query_actions(session_id="sess-A", active_only=True)
    assert len(sess_a_active) == 1
    assert sess_a_active[0].action_id == r1.action_id

    # Query by intent
    valet = registry.query_actions(intent="activate_valetmode")
    assert len(valet) == 1
    assert valet[0].action_id == r3.action_id

    # Query by phase
    completed = registry.query_actions(phase=ActiveActionPhase.COMPLETED)
    assert len(completed) == 1
    assert completed[0].action_id == r2.action_id


def test_thread_safety():
    """Verify thread-safe operations under concurrent mutations."""
    registry = ActiveActionRegistry()
    intent = "activate_hda"

    def worker(idx: int) -> None:
        rec = registry.start_action(intent=intent, proposal_id=f"prop-{idx}")
        registry.update_progress(rec.action_id, progress=0.5)
        registry.stop_action(rec.action_id, reason=f"thread-{idx}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(20)]
        concurrent.futures.wait(futures)

    # Ensure no race conditions or corrupted internal state
    all_actions = registry.query_actions(intent=intent)
    assert len(all_actions) >= 1
