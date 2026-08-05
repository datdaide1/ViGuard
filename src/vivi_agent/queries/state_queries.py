"""Vehicle State Query Responders.

This module implements the 5 state query responders for ViVi vehicle agent:
    - get_current_speed
    - get_battery_pct
    - get_gear
    - get_door_lock_status
    - get_avh_status

All responders verify PIP field availability in provenance. If a field is
marked unavailable, the responder returns QueryStatus.UNKNOWN without guessing.
None of these responders mutate VehicleState (Zero-actuator principle).
"""

from __future__ import annotations

from typing import Any, Mapping

from vivi_agent.queries.models import QueryResult, QueryResultSource, QueryStatus
from vivi_agent.vehicle.state.model import Gear, LockState, VehicleState


def _is_field_available(state: VehicleState, field_name: str) -> bool:
    """Helper checking whether a PIP field is marked available in provenance."""
    if not hasattr(state, "pip_field_provenance"):
        return True
    for item in state.pip_field_provenance:
        if item.field_name == field_name:
            return item.available
    return True


class SpeedQueryResponder:
    """Responder for `get_current_speed` query intent."""

    intent_id = "get_current_speed"

    def __call__(self, proposal: Mapping[str, Any], state: VehicleState) -> QueryResult:
        if not _is_field_available(state, "speed"):
            return QueryResult(
                intent_id=self.intent_id,
                status=QueryStatus.UNKNOWN,
                facts={"available": False},
                response_text="Hiện không có dữ liệu vận tốc xe.",
                source=QueryResultSource.VEHICLE_STATE,
                observed_at=state.timestamp,
            )

        speed = state.motion.speed_kph
        phase = state.motion.phase.value
        response = f"Xe đang chạy với tốc độ {speed} km/h." if speed > 0 else "Xe đang dừng hẳn (0 km/h)."

        return QueryResult(
            intent_id=self.intent_id,
            status=QueryStatus.ANSWER,
            facts={"speed_kph": speed, "phase": phase, "unit": "km/h"},
            response_text=response,
            source=QueryResultSource.VEHICLE_STATE,
            observed_at=state.timestamp,
        )


class BatteryQueryResponder:
    """Responder for `get_battery_pct` query intent."""

    intent_id = "get_battery_pct"

    def __call__(self, proposal: Mapping[str, Any], state: VehicleState) -> QueryResult:
        if not _is_field_available(state, "battery_pct"):
            return QueryResult(
                intent_id=self.intent_id,
                status=QueryStatus.UNKNOWN,
                facts={"available": False},
                response_text="Hiện không có dữ liệu dung lượng pin.",
                source=QueryResultSource.VEHICLE_STATE,
                observed_at=state.timestamp,
            )

        pct = state.power.battery_pct
        charging = state.power.charging
        status_str = " (đang sạc)" if charging else ""
        response = f"Dung lượng pin hiện tại là {pct}%{status_str}."

        return QueryResult(
            intent_id=self.intent_id,
            status=QueryStatus.ANSWER,
            facts={"battery_pct": pct, "charging": charging},
            response_text=response,
            source=QueryResultSource.VEHICLE_STATE,
            observed_at=state.timestamp,
        )


class GearQueryResponder:
    """Responder for `get_gear` query intent."""

    intent_id = "get_gear"

    _GEAR_NAMES = {
        Gear.PARK: "P (Đỗ)",
        Gear.REVERSE: "R (Lùi)",
        Gear.NEUTRAL: "N (Mo)",
        Gear.DRIVE: "D (Tiến)",
    }

    def __call__(self, proposal: Mapping[str, Any], state: VehicleState) -> QueryResult:
        if not _is_field_available(state, "gear"):
            return QueryResult(
                intent_id=self.intent_id,
                status=QueryStatus.UNKNOWN,
                facts={"available": False},
                response_text="Hiện không có dữ liệu vị trí số xe.",
                source=QueryResultSource.VEHICLE_STATE,
                observed_at=state.timestamp,
            )

        gear_enum = state.transmission.gear
        gear_str = gear_enum.value
        gear_name = self._GEAR_NAMES.get(gear_enum, gear_str)

        return QueryResult(
            intent_id=self.intent_id,
            status=QueryStatus.ANSWER,
            facts={"gear": gear_str, "gear_name": gear_name},
            response_text=f"Xe đang ở số {gear_name}.",
            source=QueryResultSource.VEHICLE_STATE,
            observed_at=state.timestamp,
        )


class DoorLockQueryResponder:
    """Responder for `get_door_lock_status` query intent."""

    intent_id = "get_door_lock_status"

    def __call__(self, proposal: Mapping[str, Any], state: VehicleState) -> QueryResult:
        if not _is_field_available(state, "door_lock_state"):
            return QueryResult(
                intent_id=self.intent_id,
                status=QueryStatus.UNKNOWN,
                facts={"available": False},
                response_text="Hiện không có dữ liệu trạng thái khóa cửa.",
                source=QueryResultSource.VEHICLE_STATE,
                observed_at=state.timestamp,
            )

        overall_lock = state.access.door_lock_state
        is_locked = overall_lock == LockState.LOCKED
        doors_info = {door.door_id: door.lock.value for door in state.access.doors}

        response = "Tất cả các cửa xe đang ở trạng thái Khóa." if is_locked else "Cửa xe đang ở trạng thái Mở khóa."

        return QueryResult(
            intent_id=self.intent_id,
            status=QueryStatus.ANSWER,
            facts={
                "overall_lock": overall_lock.value,
                "is_all_locked": is_locked,
                "doors": doors_info,
            },
            response_text=response,
            source=QueryResultSource.VEHICLE_STATE,
            observed_at=state.timestamp,
        )


class AvhQueryResponder:
    """Responder for `get_avh_status` query intent."""

    intent_id = "get_avh_status"

    def __call__(self, proposal: Mapping[str, Any], state: VehicleState) -> QueryResult:
        if not _is_field_available(state, "avh"):
            return QueryResult(
                intent_id=self.intent_id,
                status=QueryStatus.UNKNOWN,
                facts={"available": False},
                response_text="Hiện không có dữ liệu trạng thái giữ phanh tự động (AVH).",
                source=QueryResultSource.VEHICLE_STATE,
                observed_at=state.timestamp,
            )

        avh_active = state.adas.avh_active
        status_text = "đang bật" if avh_active else "đang tắt"

        return QueryResult(
            intent_id=self.intent_id,
            status=QueryStatus.ANSWER,
            facts={"avh_active": avh_active},
            response_text=f"Tính năng giữ phanh tự động (AVH) {status_text}.",
            source=QueryResultSource.VEHICLE_STATE,
            observed_at=state.timestamp,
        )
