"""Tests for QRY-01 — Query Responder Registry 6/6.

Acceptance criteria verified:
    AC-1  Coverage 6/6 (all 6 manifest query intents registered).
    AC-2  Missing / unavailable PIP provenance fields return QueryStatus.UNKNOWN (no hallucination).
    AC-3  Zero-actuator execution (query evaluation never mutates VehicleState).
    AC-4  `explain_feature` knowledge provider supports all 14 vehicle features with deterministic responses.
    AC-5  Startup coverage gate fails fast if any query intent is missing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
import pytest

from vivi_agent.queries import (
    QUERY_RESPONDER_REGISTRY,
    QueryResult,
    QueryResultSource,
    QueryStatus,
    assert_query_coverage,
    lookup_feature_knowledge,
    validate_query_coverage,
)
from vivi_agent.queries.registry import QueryResponderRegistry, build_default_query_registry
from vivi_agent.vehicle.execution.errors import BehaviorReadinessError, HandlerNotFoundError
from vivi_agent.vehicle.state.model import (
    DEFAULT_VEHICLE_STATE,
    AccState,
    DoorPosition,
    DoorState,
    Gear,
    LockState,
    MotionPhase,
    StateSource,
    pip_provenance,
)


# ===========================================================================
# AC-1 & AC-5 — Coverage 6/6 & Startup Gate
# ===========================================================================

class TestQueryCoverage:
    def test_all_6_query_intents_covered(self):
        """Registry must cover all 6 query intents from manifest."""
        report = validate_query_coverage(QUERY_RESPONDER_REGISTRY)
        assert report.passed is True
        assert report.covered_query == 6
        assert report.total_query_intents == 6
        assert report.missing_query == []

    def test_no_action_intent_in_query_registry(self):
        """No action intent may be registered in QueryResponderRegistry."""
        report = validate_query_coverage(QUERY_RESPONDER_REGISTRY)
        assert report.action_in_query_registry == []

    def test_startup_gate_report_accessible(self):
        from vivi_agent.queries import STARTUP_QUERY_COVERAGE_REPORT
        assert STARTUP_QUERY_COVERAGE_REPORT.passed is True
        assert STARTUP_QUERY_COVERAGE_REPORT.covered_query == 6

    def test_assert_query_coverage_fails_on_missing(self):
        """assert_query_coverage raises BehaviorReadinessError if a query intent is missing."""
        incomplete = QueryResponderRegistry()
        incomplete.register("get_current_speed", QUERY_RESPONDER_REGISTRY.get("get_current_speed"))
        with pytest.raises(BehaviorReadinessError, match="missing query responders"):
            assert_query_coverage(incomplete)

    def test_assert_query_coverage_fails_on_action_pollution(self):
        """assert_query_coverage raises if an action intent is registered in query registry."""
        polluted = build_default_query_registry()
        polluted.register("open_door", lambda p, s: None)
        with pytest.raises(BehaviorReadinessError, match="non-query intents"):
            assert_query_coverage(polluted)


# ===========================================================================
# AC-2 — State Query Responders & Missing Data (UNKNOWN) handling
# ===========================================================================

class TestStateQueryResponders:
    def test_get_current_speed_moving(self):
        state = replace(
            DEFAULT_VEHICLE_STATE,
            motion=replace(DEFAULT_VEHICLE_STATE.motion, speed_kph=60.0, phase=MotionPhase.MOVING),
            transmission=replace(DEFAULT_VEHICLE_STATE.transmission, gear=Gear.DRIVE),
        )
        res = QUERY_RESPONDER_REGISTRY.execute({"intent": "get_current_speed"}, state)

        assert res.status == QueryStatus.ANSWER
        assert res.facts["speed_kph"] == 60.0
        assert "60.0 km/h" in res.response_text
        assert res.source == QueryResultSource.VEHICLE_STATE

    def test_get_current_speed_stopped(self):
        res = QUERY_RESPONDER_REGISTRY.execute({"intent": "get_current_speed"}, DEFAULT_VEHICLE_STATE)

        assert res.status == QueryStatus.ANSWER
        assert res.facts["speed_kph"] == 0.0
        assert "dừng hẳn" in res.response_text

    def test_get_current_speed_unavailable(self):
        """When PIP provenance marks speed unavailable, responder returns UNKNOWN."""
        ts = DEFAULT_VEHICLE_STATE.timestamp
        stale_provenance = pip_provenance(StateSource.PRESET, ts, unavailable_fields=frozenset({"speed"}))
        state = replace(DEFAULT_VEHICLE_STATE, pip_field_provenance=stale_provenance)

        res = QUERY_RESPONDER_REGISTRY.execute({"intent": "get_current_speed"}, state)

        assert res.status == QueryStatus.UNKNOWN
        assert res.facts["available"] is False
        assert "không có dữ liệu" in res.response_text

    def test_get_battery_pct(self):
        state = replace(
            DEFAULT_VEHICLE_STATE,
            power=replace(DEFAULT_VEHICLE_STATE.power, battery_pct=85.5, charging=False),
        )
        res = QUERY_RESPONDER_REGISTRY.execute({"intent": "get_battery_pct"}, state)

        assert res.status == QueryStatus.ANSWER
        assert res.facts["battery_pct"] == 85.5
        assert "85.5%" in res.response_text

    def test_get_battery_pct_unavailable(self):
        ts = DEFAULT_VEHICLE_STATE.timestamp
        stale_provenance = pip_provenance(StateSource.PRESET, ts, unavailable_fields=frozenset({"battery_pct"}))
        state = replace(DEFAULT_VEHICLE_STATE, pip_field_provenance=stale_provenance)

        res = QUERY_RESPONDER_REGISTRY.execute({"intent": "get_battery_pct"}, state)
        assert res.status == QueryStatus.UNKNOWN

    def test_get_gear(self):
        state = replace(
            DEFAULT_VEHICLE_STATE,
            transmission=replace(DEFAULT_VEHICLE_STATE.transmission, gear=Gear.DRIVE),
        )
        res = QUERY_RESPONDER_REGISTRY.execute({"intent": "get_gear"}, state)

        assert res.status == QueryStatus.ANSWER
        assert res.facts["gear"] == "D"
        assert "D (Tiến)" in res.response_text

    def test_get_gear_unavailable(self):
        ts = DEFAULT_VEHICLE_STATE.timestamp
        stale_provenance = pip_provenance(StateSource.PRESET, ts, unavailable_fields=frozenset({"gear"}))
        state = replace(DEFAULT_VEHICLE_STATE, pip_field_provenance=stale_provenance)

        res = QUERY_RESPONDER_REGISTRY.execute({"intent": "get_gear"}, state)
        assert res.status == QueryStatus.UNKNOWN

    def test_get_door_lock_status_locked(self):
        res = QUERY_RESPONDER_REGISTRY.execute({"intent": "get_door_lock_status"}, DEFAULT_VEHICLE_STATE)

        assert res.status == QueryStatus.ANSWER
        assert res.facts["is_all_locked"] is True
        assert "Khóa" in res.response_text

    def test_get_door_lock_status_unlocked(self):
        unlocked_doors = (
            DoorState("driver_door", position=DoorPosition.CLOSED, lock=LockState.UNLOCKED),
            DoorState("front_passenger_door", position=DoorPosition.CLOSED, lock=LockState.LOCKED),
            DoorState("rear_left_door", position=DoorPosition.CLOSED, lock=LockState.LOCKED),
            DoorState("rear_right_door", position=DoorPosition.CLOSED, lock=LockState.LOCKED),
        )
        state = replace(
            DEFAULT_VEHICLE_STATE,
            access=replace(DEFAULT_VEHICLE_STATE.access, doors=unlocked_doors),
        )
        res = QUERY_RESPONDER_REGISTRY.execute({"intent": "get_door_lock_status"}, state)

        assert res.status == QueryStatus.ANSWER
        assert res.facts["is_all_locked"] is False
        assert "Mở khóa" in res.response_text

    def test_get_avh_status_active(self):
        state = replace(
            DEFAULT_VEHICLE_STATE,
            adas=replace(DEFAULT_VEHICLE_STATE.adas, avh_active=True),
        )
        res = QUERY_RESPONDER_REGISTRY.execute({"intent": "get_avh_status"}, state)

        assert res.status == QueryStatus.ANSWER
        assert res.facts["avh_active"] is True
        assert "đang bật" in res.response_text

    def test_get_avh_status_inactive(self):
        res = QUERY_RESPONDER_REGISTRY.execute({"intent": "get_avh_status"}, DEFAULT_VEHICLE_STATE)

        assert res.status == QueryStatus.ANSWER
        assert res.facts["avh_active"] is False
        assert "đang tắt" in res.response_text

    def test_state_queries_handle_none_state(self):
        """State queries executed with state=None gracefully return UNKNOWN."""
        for intent_id in ["get_current_speed", "get_battery_pct", "get_gear", "get_door_lock_status", "get_avh_status"]:
            res = QUERY_RESPONDER_REGISTRY.execute({"intent": intent_id}, None)
            assert res.status == QueryStatus.UNKNOWN
            assert res.facts["available"] is False


# ===========================================================================
# AC-4 — Knowledge Query (explain_feature)
# ===========================================================================

class TestExplainFeatureResponder:
    @pytest.mark.parametrize("feature_key", [
        "adaptive_cruise_control", "aac",
        "auto_park", "autopark",
        "auto_vehicle_hold", "avh",
        "automatic_high_beam", "ahb",
        "camp_mode", "creep_mode",
        "electronic_parking_brake", "epb",
        "electronic_stability_control", "esc",
        "head_up_display", "hud",
        "highway_drive_assist", "hda",
        "lane_keeping_assist", "lka",
        "pet_mode", "traction_control", "tcs",
        "valet_mode",
    ])
    def test_explain_feature_known_features(self, feature_key: str):
        res = QUERY_RESPONDER_REGISTRY.execute(
            {"intent": "explain_feature", "parameters": {"feature": feature_key}},
            DEFAULT_VEHICLE_STATE,
        )

        assert res.status == QueryStatus.ANSWER
        assert res.source == QueryResultSource.KNOWLEDGE_BASE
        assert "canonical_id" in res.facts
        assert len(res.response_text) > 0

    def test_explain_feature_missing_target(self):
        res = QUERY_RESPONDER_REGISTRY.execute({"intent": "explain_feature"}, DEFAULT_VEHICLE_STATE)

        assert res.status == QueryStatus.UNKNOWN
        assert res.facts["error"] == "MISSING_FEATURE_PARAMETER"
        assert "cung cấp tên tính năng" in res.response_text

    def test_explain_feature_unknown_feature(self):
        res = QUERY_RESPONDER_REGISTRY.execute(
            {"intent": "explain_feature", "parameters": {"feature": "flying_mode"}},
            DEFAULT_VEHICLE_STATE,
        )

        assert res.status == QueryStatus.UNKNOWN
        assert res.facts["found"] is False
        assert "chưa có thông tin" in res.response_text


# ===========================================================================
# AC-3 — Zero-Actuator Assertion
# ===========================================================================

class TestZeroActuatorPrinciple:
    def test_queries_do_not_mutate_vehicle_state(self):
        """Executing any of the 6 query responders must leave VehicleState completely untouched."""
        initial_state = DEFAULT_VEHICLE_STATE
        initial_version = initial_state.state_version

        for intent_id in ["get_current_speed", "get_battery_pct", "get_gear", "get_door_lock_status", "get_avh_status"]:
            res = QUERY_RESPONDER_REGISTRY.execute({"intent": intent_id}, initial_state)
            assert res is not None

        # Execute knowledge query
        res_know = QUERY_RESPONDER_REGISTRY.execute(
            {"intent": "explain_feature", "parameters": {"feature": "hda"}},
            initial_state,
        )
        assert res_know is not None

        # State object and version must be 100% identical
        assert initial_state.state_version == initial_version
        assert initial_state == DEFAULT_VEHICLE_STATE

    def test_unregistered_query_raises_not_found(self):
        with pytest.raises(HandlerNotFoundError):
            QUERY_RESPONDER_REGISTRY.execute({"intent": "nonexistent_query"}, DEFAULT_VEHICLE_STATE)
