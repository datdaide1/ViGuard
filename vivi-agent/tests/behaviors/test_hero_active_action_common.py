"""Unit tests for shared hero plumbing (_active_action_common.py).

Covers the mechanics extracted out of HERO-02/HERO-03's individual hero
modules: subset assertion, restart-supersede detection, and dropping an
ActiveAction entry by id. The hero modules' own test files cover these
indirectly through their public wrappers; this file tests them directly
since they now carry real logic of their own, not just re-exports.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from vivi_agent.active_actions.registry import SUPERSEDED_BY_NEW_START_REASON
from vivi_agent.behaviors.hero._active_action_common import (
    assert_subset_of_monitored_intents,
    drop_active_action,
    is_restart_supersede,
)
from vivi_agent.vehicle.state.model import ActiveAction
from vivi_agent.vehicle.state.presets import get_preset

_NOW = datetime(2026, 8, 6, 10, 0, 0, tzinfo=timezone.utc)


class TestAssertSubsetOfMonitoredIntents:
    def test_accepts_a_true_subset(self):
        assert_subset_of_monitored_intents(frozenset({"activate_hda"}), label="test")

    def test_rejects_an_intent_outside_monitored_intents(self):
        with pytest.raises(RuntimeError, match="is not a subset"):
            assert_subset_of_monitored_intents(frozenset({"open_door"}), label="BOGUS_INTENTS")


class TestIsRestartSupersede:
    def test_true_for_the_supersede_reason(self):
        assert is_restart_supersede(SUPERSEDED_BY_NEW_START_REASON) is True

    def test_false_for_any_other_reason(self):
        assert is_restart_supersede("monitor_stop:LOW_BATTERY") is False
        assert is_restart_supersede("") is False


class TestDropActiveAction:
    def _state(self, *action_ids: str):
        base = get_preset("parked_ready", state_version=1, timestamp=_NOW)
        actions = tuple(ActiveAction(action_id=aid, intent="activate_campmode") for aid in action_ids)
        return replace(base, active_actions=actions)

    def test_removes_the_matching_entry_only(self):
        state = self._state("act-1", "act-2")
        remaining = drop_active_action(state, "act-1")
        assert [a.action_id for a in remaining] == ["act-2"]

    def test_is_a_noop_when_action_id_is_absent(self):
        state = self._state("act-1")
        remaining = drop_active_action(state, "does-not-exist")
        assert remaining == state.active_actions
