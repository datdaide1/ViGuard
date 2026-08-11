"""Unit tests for HERO-02 — HDA/AAC active driving assist hero behaviors."""

from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from vivi_agent.active_actions.registry import ActiveActionRegistry
from vivi_agent.behaviors.catalog import get_behavior_config
from vivi_agent.behaviors.hero.active_driving_assist import (
    AdasMonitorHeroBehavior,
    make_monitored_active_action_handler,
    register_hda_aac_stop_handlers,
)
from vivi_agent.vehicle.state.machine import VehicleStateMachine
from vivi_agent.vehicle.state.model import AccState, ActiveActionPhase, AdasState
from vivi_agent.vehicle.state.presets import get_preset

_NOW = datetime(2026, 8, 6, 10, 0, 0, tzinfo=timezone.utc)


def _machine(**adas_kwargs) -> VehicleStateMachine:
    base = get_preset("parked_ready", state_version=1, timestamp=_NOW)
    state = replace(base, adas=AdasState(**adas_kwargs)) if adas_kwargs else base
    return VehicleStateMachine(state)


class TestMakeMonitoredActiveActionHandler:
    def test_rejects_intents_outside_hda_aac_scope(self):
        config = get_behavior_config("activate_campmode")
        with pytest.raises(ValueError, match="only supports"):
            make_monitored_active_action_handler(config, _machine(), ActiveActionRegistry())

    def test_start_registers_active_action_record(self):
        config = get_behavior_config("activate_hda")
        machine = _machine(acc_state=AccState.ACTIVE)
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
        assert running[0].intent == "activate_hda"
        assert running[0].active_action_name == "hda"
        assert running[0].phase == ActiveActionPhase.STARTED
        assert running[0].proposal_id == "prop-1"

    def test_second_start_supersedes_first_for_same_session(self):
        config = get_behavior_config("activate_aac")
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


class TestHdaAacStopHandlers:
    def test_hda_stop_turns_off_hda_active_and_clears_active_action(self):
        machine = _machine(acc_state=AccState.ACTIVE, hda_active=True)
        registry = ActiveActionRegistry()
        register_hda_aac_stop_handlers(registry, machine)
        handler = make_monitored_active_action_handler(get_behavior_config("activate_hda"), machine, registry)
        handler({"proposal_id": "prop-1", "session_id": "sess-1", "arguments": {}})

        record = registry.get_active_actions(session_id="sess-1")[0]
        registry.stop_action(record.action_id, reason="monitor_stop:TEST")

        snapshot = machine.snapshot()
        assert snapshot.adas.hda_active is False
        assert all(a.action_id != record.action_id for a in snapshot.active_actions)

    def test_aac_stop_cascades_hda_off_in_single_transition(self):
        """Stopping AAC while HDA is active must never pass through an
        intermediate state violating HDA_REQUIRES_ACTIVE_ACC."""
        machine = _machine(acc_state=AccState.ACTIVE, hda_active=True)
        registry = ActiveActionRegistry()
        register_hda_aac_stop_handlers(registry, machine)

        hda_handler = make_monitored_active_action_handler(get_behavior_config("activate_hda"), machine, registry)
        aac_handler = make_monitored_active_action_handler(get_behavior_config("activate_aac"), machine, registry)
        hda_handler({"proposal_id": "prop-hda", "session_id": "sess-1", "arguments": {}})
        aac_handler({"proposal_id": "prop-aac", "session_id": "sess-1", "arguments": {}})

        aac_record = next(r for r in registry.get_active_actions(session_id="sess-1") if r.intent == "activate_aac")
        registry.stop_action(aac_record.action_id, reason="monitor_stop:TEST")

        snapshot = machine.snapshot()
        assert snapshot.adas.acc_state == AccState.CANCELLED
        assert snapshot.adas.hda_active is False  # never left in an invalid intermediate state

        hda_record = next(r for r in registry.list_all() if r.intent == "activate_hda")
        assert hda_record.phase == ActiveActionPhase.STOPPED
        assert hda_record.stop_reason.startswith("cascaded_from_aac_stop")

    def test_aac_stop_without_hda_does_not_touch_hda_state(self):
        machine = _machine(acc_state=AccState.ACTIVE, hda_active=False)
        registry = ActiveActionRegistry()
        register_hda_aac_stop_handlers(registry, machine)
        handler = make_monitored_active_action_handler(get_behavior_config("activate_aac"), machine, registry)
        handler({"proposal_id": "prop-1", "session_id": "sess-1", "arguments": {}})

        record = registry.get_active_actions(session_id="sess-1")[0]
        version_before = machine.snapshot().state_version
        registry.stop_action(record.action_id, reason="monitor_stop:TEST")

        snapshot = machine.snapshot()
        assert snapshot.adas.acc_state == AccState.CANCELLED
        assert snapshot.adas.hda_active is False
        assert snapshot.state_version == version_before + 1  # exactly one transition, no cascade call


class TestAdasMonitorHeroBehaviorHasNoLocalPolicy:
    def test_evaluate_signature_never_accepts_vehicle_state(self):
        """Structural guard: the method must only take the monitor result dict —
        it must be impossible to hand it a VehicleState/speed/hands-off value."""
        params = list(inspect.signature(AdasMonitorHeroBehavior.evaluate_monitor_result).parameters)
        assert params == ["monitor_result"]

    def test_stop_and_go_hold_is_not_inferred_locally(self):
        """Guardrail ALLOW at speed=0 (Stop&Go Hold) must not be second-guessed —
        the monitor_result dict below carries no speed field at all, proving the
        outcome is decided purely by Guardrail's `outcome`, never by local state."""
        monitor_result = {
            "action_id": "act-1",
            "intent": "activate_aac",
            "outcome": "ALLOW",
            "stopped": False,
            "request_id": "req-1",
        }
        outcome = AdasMonitorHeroBehavior.evaluate_monitor_result(monitor_result)
        assert outcome.stopped is False
        assert outcome.outcome == "ALLOW"

    def test_rejects_intent_outside_scope(self):
        with pytest.raises(ValueError, match="only handles"):
            AdasMonitorHeroBehavior.evaluate_monitor_result({"intent": "activate_campmode"})


class TestGroundedMessages:
    def test_stop_message_cites_only_given_reason_and_rule(self):
        registry = ActiveActionRegistry()
        record = registry.start_action(intent="activate_hda", session_id="sess-1")
        monitor_result = {
            "action_id": record.action_id,
            "intent": "activate_hda",
            "outcome": "BLOCK_UNSAFE",
            "stopped": True,
            "reason_code": "HANDS_OFF_TIMEOUT",
            "rule_id": "R073",
        }
        message = AdasMonitorHeroBehavior.build_stop_message(record, monitor_result)
        assert "HANDS_OFF_TIMEOUT" in message
        assert "R073" in message
        assert "Hỗ trợ lái trên cao tốc" in message
        # no invented numeric threshold (e.g. a hardcoded seconds count) in the text
        assert not any(char.isdigit() for char in message.replace("R073", ""))

    def test_fail_message_cites_given_error_verbatim(self):
        registry = ActiveActionRegistry()
        record = registry.start_action(intent="activate_aac", session_id="sess-1")
        message = AdasMonitorHeroBehavior.build_fail_message(record, "guardrail_timeout")
        assert "guardrail_timeout" in message
        assert "Điều khiển hành trình thích ứng" in message
