"""Unit tests for HERO-03 — Autopark/Camp mode hero behaviors."""

from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from vivi_agent.active_actions.registry import ActiveActionRegistry
from vivi_agent.behaviors.catalog import get_behavior_config
from vivi_agent.behaviors.hero.autopark_campmode import (
    AutoparkCampmodeMonitorHeroBehavior,
    make_monitored_active_action_handler,
    register_autopark_campmode_stop_handlers,
)
from vivi_agent.vehicle.state.machine import VehicleStateMachine
from vivi_agent.vehicle.state.model import ActiveActionPhase, AdasState, AutoparkState, ModeState
from vivi_agent.vehicle.state.presets import get_preset

_NOW = datetime(2026, 8, 6, 10, 0, 0, tzinfo=timezone.utc)


def _machine(**overrides: object) -> VehicleStateMachine:
    base = get_preset("parked_ready", state_version=1, timestamp=_NOW)
    if overrides:
        base = replace(base, **overrides)
    return VehicleStateMachine(base)


class TestMakeMonitoredActiveActionHandler:
    def test_rejects_intents_outside_autopark_campmode_scope(self):
        config = get_behavior_config("activate_hda")
        with pytest.raises(ValueError, match="only supports"):
            make_monitored_active_action_handler(config, _machine(), ActiveActionRegistry())

    def test_start_campmode_registers_record_and_sets_camp_mode_active(self):
        config = get_behavior_config("activate_campmode")
        machine = _machine()
        registry = ActiveActionRegistry()
        handler = make_monitored_active_action_handler(config, machine, registry)

        handler(
            {
                "proposal_id": "prop-1",
                "session_id": "sess-1",
                "source_turn_id": "turn-1",
                "arguments": {},
            }
        )

        running = registry.get_active_actions(session_id="sess-1")
        assert len(running) == 1
        assert running[0].intent == "activate_campmode"
        assert running[0].active_action_name == "camp_mode"
        assert running[0].phase == ActiveActionPhase.STARTED

        # Unlike autopark's enum field, ActiveActionHandler sets camp_mode_active
        # directly (BehaviorConfig declares target_substate/target_field for it).
        assert machine.snapshot().modes.camp_mode_active is True

    def test_start_autopark_registers_record_without_touching_autopark_state(self):
        """`autopark_state` is an AutoparkState enum the catalog intentionally leaves
        for vehicle/monitor telemetry feedback to set — mirroring HDA/AAC's enum
        fields (see catalog.py's ADAS section comments)."""
        config = get_behavior_config("activate_autopark")
        machine = _machine()
        registry = ActiveActionRegistry()
        handler = make_monitored_active_action_handler(config, machine, registry)

        handler({"proposal_id": "prop-1", "session_id": "sess-1", "arguments": {}})

        running = registry.get_active_actions(session_id="sess-1")
        assert len(running) == 1
        assert running[0].intent == "activate_autopark"
        assert running[0].active_action_name == "autopark"
        assert machine.snapshot().adas.autopark_state == AutoparkState.OFF

    def test_second_start_supersedes_first_for_same_session(self):
        config = get_behavior_config("activate_autopark")
        machine = _machine()
        registry = ActiveActionRegistry()
        handler = make_monitored_active_action_handler(config, machine, registry)

        handler({"proposal_id": "prop-1", "session_id": "sess-1", "arguments": {}})
        handler({"proposal_id": "prop-2", "session_id": "sess-1", "arguments": {}})

        running = registry.get_active_actions(session_id="sess-1")
        assert len(running) == 1
        assert running[0].proposal_id == "prop-2"
        all_records = registry.list_all()
        assert len(all_records) == 2
        assert all_records[0].phase == ActiveActionPhase.STOPPED
        assert all_records[0].stop_reason == "superseded_by_new_start"


class TestAutoparkCampmodeStopHandlers:
    def test_autopark_stop_turns_off_autopark_state_and_clears_active_action(self):
        machine = _machine(adas=AdasState(autopark_state=AutoparkState.ACTIVE))
        registry = ActiveActionRegistry()
        register_autopark_campmode_stop_handlers(registry, machine)
        handler = make_monitored_active_action_handler(
            get_behavior_config("activate_autopark"), machine, registry
        )
        handler({"proposal_id": "prop-1", "session_id": "sess-1", "arguments": {}})

        record = registry.get_active_actions(session_id="sess-1")[0]
        registry.stop_action(record.action_id, reason="monitor_stop:TEST")

        snapshot = machine.snapshot()
        assert snapshot.adas.autopark_state == AutoparkState.OFF
        assert all(a.action_id != record.action_id for a in snapshot.active_actions)

    def test_campmode_stop_turns_off_camp_mode_active_and_clears_active_action(self):
        machine = _machine()
        registry = ActiveActionRegistry()
        register_autopark_campmode_stop_handlers(registry, machine)
        handler = make_monitored_active_action_handler(
            get_behavior_config("activate_campmode"), machine, registry
        )
        handler({"proposal_id": "prop-1", "session_id": "sess-1", "arguments": {}})
        assert machine.snapshot().modes.camp_mode_active is True  # set on start

        record = registry.get_active_actions(session_id="sess-1")[0]
        registry.stop_action(record.action_id, reason="monitor_stop:LOW_BATTERY")

        snapshot = machine.snapshot()
        assert snapshot.modes.camp_mode_active is False
        assert all(a.action_id != record.action_id for a in snapshot.active_actions)

    def test_superseded_restart_does_not_touch_real_autopark_state(self):
        """A same-session restart must not force-disengage state a fresh run now owns."""
        machine = _machine(adas=AdasState(autopark_state=AutoparkState.ACTIVE))
        registry = ActiveActionRegistry()
        register_autopark_campmode_stop_handlers(registry, machine)
        handler = make_monitored_active_action_handler(
            get_behavior_config("activate_autopark"), machine, registry
        )

        handler({"proposal_id": "prop-1", "session_id": "sess-1", "arguments": {}})
        version_after_first_start = machine.snapshot().state_version
        handler({"proposal_id": "prop-2", "session_id": "sess-1", "arguments": {}})

        # The supersede-triggered stop handler must be a no-op on real state —
        # only the second activate_autopark's own active_action bookkeeping changed.
        assert machine.snapshot().adas.autopark_state == AutoparkState.ACTIVE
        assert machine.snapshot().state_version == version_after_first_start + 1

    def test_stop_is_idempotent_when_already_off(self):
        """Calling the stop handler when the field is already off must not raise
        or emit a spurious extra transition."""
        machine = _machine()
        registry = ActiveActionRegistry()
        register_autopark_campmode_stop_handlers(registry, machine)
        record = registry.start_action(intent="activate_campmode", session_id="sess-1")
        version_before = machine.snapshot().state_version

        registry.stop_action(record.action_id, reason="manual_stop")

        # camp_mode_active was already False and no matching active_action entry
        # exists (start_action bypasses the real ActiveActionHandler patch in
        # this unit test) — the no-op guard must skip the transition entirely,
        # not just avoid crashing.
        assert machine.snapshot().state_version == version_before


class TestResetClearsCompoundState:
    """Acceptance criterion: reset must not leave an invalid compound state."""

    def test_reset_and_cleanup_turns_off_camp_mode_and_autopark(self):
        machine = _machine()
        registry = ActiveActionRegistry()
        register_autopark_campmode_stop_handlers(registry, machine)
        camp_handler = make_monitored_active_action_handler(
            get_behavior_config("activate_campmode"), machine, registry
        )
        camp_handler({"proposal_id": "prop-camp", "session_id": "sess-1", "arguments": {}})
        assert machine.snapshot().modes.camp_mode_active is True

        registry.reset_and_cleanup(reason="agent_restart")

        snapshot = machine.snapshot()
        assert snapshot.modes.camp_mode_active is False
        assert snapshot.active_actions == ()
        assert registry.get_active_actions(session_id="sess-1") == []


class TestAutoparkCampmodeMonitorHeroBehaviorHasNoLocalPolicy:
    def test_evaluate_signature_never_accepts_vehicle_state(self):
        """Structural guard: the method must only take the monitor result dict —
        it must be impossible to hand it a VehicleState/battery_pct value."""
        params = list(
            inspect.signature(AutoparkCampmodeMonitorHeroBehavior.evaluate_monitor_result).parameters
        )
        assert params == ["monitor_result"]

    def test_rejects_intent_outside_scope(self):
        with pytest.raises(ValueError, match="only handles"):
            AutoparkCampmodeMonitorHeroBehavior.evaluate_monitor_result({"intent": "activate_hda"})

    def test_low_battery_self_cancel_is_relayed_not_inferred(self):
        """Camp mode's real self-cancel condition is battery_pct < MODE_BATTERY_ABORT_PCT
        — a Guardrail policy threshold. This monitor_result carries no battery
        field at all, proving the outcome comes purely from Guardrail's `outcome`."""
        monitor_result = {
            "action_id": "act-1",
            "intent": "activate_campmode",
            "outcome": "BLOCK_UNSAFE",
            "stopped": True,
            "reason_code": "LOW_BATTERY",
            "rule_id": "R_CAMP_BATTERY",
        }
        outcome = AutoparkCampmodeMonitorHeroBehavior.evaluate_monitor_result(monitor_result)
        assert outcome.stopped is True
        assert outcome.reason_code == "LOW_BATTERY"


class TestGroundedMessages:
    def test_stop_message_cites_only_given_reason_and_rule(self):
        registry = ActiveActionRegistry()
        record = registry.start_action(intent="activate_autopark", session_id="sess-1")
        monitor_result = {
            "action_id": record.action_id,
            "intent": "activate_autopark",
            "outcome": "BLOCK_UNSAFE",
            "stopped": True,
            "reason_code": "PARKING_SPACE_LOST",
            "rule_id": "R048",
        }
        message = AutoparkCampmodeMonitorHeroBehavior.build_stop_message(record, monitor_result)
        assert "PARKING_SPACE_LOST" in message
        assert "R048" in message
        assert "Autopark" in message

    def test_fail_message_cites_given_error_verbatim(self):
        registry = ActiveActionRegistry()
        record = registry.start_action(intent="activate_campmode", session_id="sess-1")
        message = AutoparkCampmodeMonitorHeroBehavior.build_fail_message(record, "guardrail_timeout")
        assert "guardrail_timeout" in message
        assert "Chế độ cắm trại" in message
