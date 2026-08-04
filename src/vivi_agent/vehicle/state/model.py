"""Immutable Vehicle State Model and cross-domain invariants.

The model contains simulator facts, not policy thresholds.  Invalid combinations
are rejected at construction time so downstream Guardrail and UI consumers never
observe a partially coherent snapshot.  State transitions and version increments
belong to VEH-02; this module only defines their typed boundary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

VEHICLE_STATE_SCHEMA_VERSION = "1.0.0"
REQUIRED_DOOR_IDS = frozenset(
    {"driver_door", "front_passenger_door", "rear_left_door", "rear_right_door"}
)
PIP_FIELD_NAMES = frozenset(
    {
        "speed",
        "gear",
        "epb",
        "battery_pct",
        "acc_state",
        "hand_on_steeringwheel",
        "profile",
        "esc",
        "avh",
        "fog_light",
        "hazard_light",
        "highbeam_mode",
        "lowbeam_mode",
        "door_lock_state",
        "rain_sensor",
        "ambient_light",
        "camp_mode_active",
        "pet_mode_active",
        "valet_mode_active",
        "autopark_state",
    }
)


class VehicleStateValidationError(ValueError):
    """A state snapshot violates the closed Vehicle State schema or invariants."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class _StringEnum(str, Enum):
    pass


class Gear(_StringEnum):
    PARK = "P"
    REVERSE = "R"
    NEUTRAL = "N"
    DRIVE = "D"


class MotionPhase(_StringEnum):
    STOPPED = "STOPPED"
    MOVING = "MOVING"


class LockState(_StringEnum):
    LOCKED = "Locked"
    UNLOCKED = "Unlocked"


class DoorPosition(_StringEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"


class LightMode(_StringEnum):
    OFF = "Off"
    ON = "On"


class AccState(_StringEnum):
    OFF = "OFF"
    STANDBY = "STANDBY"
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    FAULT = "FAULT"


class AutoparkState(_StringEnum):
    OFF = "OFF"
    ACTIVE = "ACTIVE"


class AmbientLight(_StringEnum):
    DAY = "day"
    NIGHT = "night"


class Profile(_StringEnum):
    OWNER = "Chủ xe"
    GUEST = "Khách"
    STRANGER = "Người lạ"


class DriveMode(_StringEnum):
    ECO = "ECO"
    NORMAL = "NORMAL"
    SPORT = "SPORT"


class ActiveActionPhase(_StringEnum):
    STARTED = "started"
    PROGRESS = "progress"
    STOPPED = "stopped"
    FAILED = "failed"
    COMPLETED = "completed"


class StateSource(_StringEnum):
    PRESET = "PRESET"
    SIMULATOR = "SIMULATOR"
    OPERATOR = "OPERATOR"
    VEHICLE_HANDLER = "VEHICLE_HANDLER"


@dataclass(frozen=True)
class StateFieldProvenance:
    """Availability and origin of one PIP field in this snapshot."""

    field_name: str
    source: StateSource
    observed_at: datetime
    available: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.field_name, str) or self.field_name not in PIP_FIELD_NAMES:
            raise VehicleStateValidationError(
                "INVALID_PROVENANCE_FIELD", f"unsupported PIP field {self.field_name!r}"
            )
        _require_enum(self.source, StateSource, "provenance.source")
        _require_aware_datetime(self.observed_at, "provenance.observed_at")
        _require_bool(self.available, "provenance.available")


def pip_provenance(
    source: StateSource,
    observed_at: datetime,
    *,
    unavailable_fields: frozenset[str] = frozenset(),
) -> tuple[StateFieldProvenance, ...]:
    """Build complete per-field PIP provenance for a snapshot.

    A caller must explicitly mark unavailable readings. Their retained values are
    treated as stale diagnostics and are never exported to Guardrail.
    """

    _require_enum(source, StateSource, "provenance.source")
    _require_aware_datetime(observed_at, "provenance.observed_at")
    unknown = unavailable_fields - PIP_FIELD_NAMES
    if unknown:
        raise VehicleStateValidationError(
            "INVALID_PROVENANCE_FIELD",
            f"unsupported unavailable fields: {', '.join(sorted(unknown))}",
        )
    return tuple(
        StateFieldProvenance(
            field_name=field_name,
            source=source,
            observed_at=observed_at,
            available=field_name not in unavailable_fields,
        )
        for field_name in sorted(PIP_FIELD_NAMES)
    )


@dataclass(frozen=True)
class PowerState:
    powered_on: bool = False
    charging: bool = False
    battery_pct: float = 100.0

    def __post_init__(self) -> None:
        _require_bool(self.powered_on, "power.powered_on")
        _require_bool(self.charging, "power.charging")
        _finite_range(self.battery_pct, "power.battery_pct", 0.0, 100.0)


@dataclass(frozen=True)
class MotionState:
    speed_kph: float = 0.0
    phase: MotionPhase = MotionPhase.STOPPED

    def __post_init__(self) -> None:
        _require_enum(self.phase, MotionPhase, "motion.phase")
        _finite_range(self.speed_kph, "motion.speed_kph", 0.0, None)
        expected = MotionPhase.MOVING if self.speed_kph > 0 else MotionPhase.STOPPED
        if self.phase is not expected:
            raise VehicleStateValidationError(
                "MOTION_PHASE_MISMATCH",
                f"speed_kph={self.speed_kph} requires phase={expected.value}",
            )


@dataclass(frozen=True)
class TransmissionState:
    gear: Gear = Gear.PARK
    epb_engaged: bool = True

    def __post_init__(self) -> None:
        _require_enum(self.gear, Gear, "transmission.gear")
        _require_bool(self.epb_engaged, "transmission.epb_engaged")


@dataclass(frozen=True)
class DoorState:
    door_id: str
    position: DoorPosition = DoorPosition.CLOSED
    lock: LockState = LockState.LOCKED

    def __post_init__(self) -> None:
        _require_enum(self.position, DoorPosition, "access.door.position")
        _require_enum(self.lock, LockState, "access.door.lock")
        if not self.door_id:
            raise VehicleStateValidationError("INVALID_DOOR_ID", "door_id cannot be empty")
        if self.position is DoorPosition.OPEN and self.lock is LockState.LOCKED:
            raise VehicleStateValidationError(
                "OPEN_DOOR_LOCKED", f"open door {self.door_id!r} cannot be locked"
            )


def _default_doors() -> tuple[DoorState, ...]:
    return tuple(
        DoorState(door_id)
        for door_id in sorted(REQUIRED_DOOR_IDS)
    )


@dataclass(frozen=True)
class AccessState:
    doors: tuple[DoorState, ...] = field(default_factory=_default_doors)
    trunk_open: bool = False
    bonnet_open: bool = False
    charge_port_open: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.doors, tuple) or not all(
            isinstance(door, DoorState) for door in self.doors
        ):
            raise VehicleStateValidationError(
                "INVALID_DOORS", "access.doors must be a tuple of DoorState"
            )
        for field_name in ("trunk_open", "bonnet_open", "charge_port_open"):
            _require_bool(getattr(self, field_name), f"access.{field_name}")
        ids = tuple(door.door_id for door in self.doors)
        if len(ids) != len(set(ids)):
            raise VehicleStateValidationError("DUPLICATE_DOOR", "door IDs must be unique")
        if set(ids) != REQUIRED_DOOR_IDS:
            missing = sorted(REQUIRED_DOOR_IDS - set(ids))
            extra = sorted(set(ids) - REQUIRED_DOOR_IDS)
            raise VehicleStateValidationError(
                "INVALID_DOOR_COVERAGE",
                f"door coverage mismatch; missing={missing}, extra={extra}",
            )

    @property
    def door_lock_state(self) -> LockState:
        return (
            LockState.LOCKED
            if all(door.lock is LockState.LOCKED for door in self.doors)
            else LockState.UNLOCKED
        )


@dataclass(frozen=True)
class LightingState:
    lowbeam: LightMode = LightMode.OFF
    highbeam: LightMode = LightMode.OFF
    fog_light: bool = False
    hazard_light: bool = False
    left_turn_signal: bool = False
    right_turn_signal: bool = False
    cornering_light: bool = False
    interior_light: bool = False

    def __post_init__(self) -> None:
        _require_enum(self.lowbeam, LightMode, "lighting.lowbeam")
        _require_enum(self.highbeam, LightMode, "lighting.highbeam")
        for field_name in (
            "fog_light", "hazard_light", "left_turn_signal", "right_turn_signal",
            "cornering_light", "interior_light",
        ):
            _require_bool(getattr(self, field_name), f"lighting.{field_name}")


@dataclass(frozen=True)
class CabinState:
    profile: Profile = Profile.OWNER
    driver_seat_position: float = 0.5
    driver_seat_angle: float = 0.5
    rear_seat_folded: bool = False
    windows_open: bool = False
    sunroof_open: bool = False
    mirrors_folded: bool = False
    hud_active: bool = True

    def __post_init__(self) -> None:
        _require_enum(self.profile, Profile, "cabin.profile")
        for field_name in (
            "rear_seat_folded", "windows_open", "sunroof_open", "mirrors_folded", "hud_active"
        ):
            _require_bool(getattr(self, field_name), f"cabin.{field_name}")
        _finite_range(self.driver_seat_position, "cabin.driver_seat_position", 0.0, 1.0)
        _finite_range(self.driver_seat_angle, "cabin.driver_seat_angle", 0.0, 1.0)


@dataclass(frozen=True)
class AdasState:
    acc_state: AccState = AccState.OFF
    hda_active: bool = False
    autopark_state: AutoparkState = AutoparkState.OFF
    lane_keep_assist_active: bool = False
    auto_highbeam_active: bool = False
    tcs_active: bool = True
    esc_active: bool = True
    avh_active: bool = False
    hand_on_steeringwheel: bool = True

    def __post_init__(self) -> None:
        _require_enum(self.acc_state, AccState, "adas.acc_state")
        _require_enum(self.autopark_state, AutoparkState, "adas.autopark_state")
        for field_name in (
            "hda_active", "lane_keep_assist_active",
            "auto_highbeam_active", "tcs_active", "esc_active", "avh_active",
            "hand_on_steeringwheel",
        ):
            _require_bool(getattr(self, field_name), f"adas.{field_name}")
        if self.hda_active and self.acc_state is not AccState.ACTIVE:
            raise VehicleStateValidationError(
                "HDA_REQUIRES_ACTIVE_ACC", "hda_active requires acc_state=ACTIVE"
            )
        if self.tcs_active and not self.esc_active:
            raise VehicleStateValidationError(
                "TCS_REQUIRES_ESC", "tcs_active requires esc_active"
            )


@dataclass(frozen=True)
class ModeState:
    drive_mode: DriveMode = DriveMode.NORMAL
    creep_mode_active: bool = False
    camp_mode_active: bool = False
    pet_mode_active: bool = False
    valet_mode_active: bool = False

    def __post_init__(self) -> None:
        _require_enum(self.drive_mode, DriveMode, "modes.drive_mode")
        for field_name in (
            "creep_mode_active", "camp_mode_active", "pet_mode_active", "valet_mode_active"
        ):
            _require_bool(getattr(self, field_name), f"modes.{field_name}")
        special_modes = (self.camp_mode_active, self.pet_mode_active, self.valet_mode_active)
        if sum(special_modes) > 1:
            raise VehicleStateValidationError(
                "SPECIAL_MODE_CONFLICT", "camp, pet and valet modes are mutually exclusive"
            )


@dataclass(frozen=True)
class EnvironmentState:
    rain_sensor: bool | None = False
    ambient_light: AmbientLight = AmbientLight.DAY
    obstacle_detected: bool = False
    driver_present: bool = True
    passenger_count: int = 0

    def __post_init__(self) -> None:
        if self.rain_sensor is not None:
            _require_bool(self.rain_sensor, "environment.rain_sensor")
        _require_enum(self.ambient_light, AmbientLight, "environment.ambient_light")
        for field_name in ("obstacle_detected", "driver_present"):
            _require_bool(getattr(self, field_name), f"environment.{field_name}")
        if (
            isinstance(self.passenger_count, bool)
            or not isinstance(self.passenger_count, int)
            or self.passenger_count < 0
        ):
            raise VehicleStateValidationError(
                "INVALID_PASSENGER_COUNT", "passenger_count must be a non-negative integer"
            )


@dataclass(frozen=True)
class UiState:
    notification_center_open: bool = False

    def __post_init__(self) -> None:
        _require_bool(self.notification_center_open, "ui.notification_center_open")


@dataclass(frozen=True)
class ActiveAction:
    action_id: str
    intent: str
    phase: ActiveActionPhase = ActiveActionPhase.STARTED
    progress: float = 0.0

    def __post_init__(self) -> None:
        _require_enum(self.phase, ActiveActionPhase, "active_action.phase")
        if not self.action_id or not self.intent:
            raise VehicleStateValidationError(
                "INVALID_ACTIVE_ACTION", "action_id and intent must be non-empty"
            )
        _finite_range(self.progress, "active_action.progress", 0.0, 1.0)


@dataclass(frozen=True)
class VehicleState:
    state_version: int
    timestamp: datetime
    pip_field_provenance: tuple[StateFieldProvenance, ...]
    power: PowerState = field(default_factory=PowerState)
    motion: MotionState = field(default_factory=MotionState)
    transmission: TransmissionState = field(default_factory=TransmissionState)
    access: AccessState = field(default_factory=AccessState)
    lighting: LightingState = field(default_factory=LightingState)
    cabin: CabinState = field(default_factory=CabinState)
    adas: AdasState = field(default_factory=AdasState)
    modes: ModeState = field(default_factory=ModeState)
    environment: EnvironmentState = field(default_factory=EnvironmentState)
    ui: UiState = field(default_factory=UiState)
    active_actions: tuple[ActiveAction, ...] = ()

    def __post_init__(self) -> None:
        if (
            isinstance(self.state_version, bool)
            or not isinstance(self.state_version, int)
            or self.state_version < 0
        ):
            raise VehicleStateValidationError(
                "INVALID_STATE_VERSION", "state_version must be a non-negative integer"
            )
        _require_aware_datetime(self.timestamp, "timestamp")
        if not isinstance(self.pip_field_provenance, tuple) or not all(
            isinstance(item, StateFieldProvenance) for item in self.pip_field_provenance
        ):
            raise VehicleStateValidationError(
                "INVALID_PIP_PROVENANCE",
                "pip_field_provenance must be a tuple of StateFieldProvenance",
            )
        provenance_names = tuple(item.field_name for item in self.pip_field_provenance)
        if len(provenance_names) != len(set(provenance_names)) or set(provenance_names) != PIP_FIELD_NAMES:
            raise VehicleStateValidationError(
                "INCOMPLETE_PIP_PROVENANCE",
                "pip_field_provenance must contain every PIP field exactly once",
            )
        if any(item.observed_at > self.timestamp for item in self.pip_field_provenance):
            raise VehicleStateValidationError(
                "FUTURE_FIELD_OBSERVATION",
                "field observed_at cannot be later than snapshot timestamp",
            )
        expected_groups = {
            "power": PowerState,
            "motion": MotionState,
            "transmission": TransmissionState,
            "access": AccessState,
            "lighting": LightingState,
            "cabin": CabinState,
            "adas": AdasState,
            "modes": ModeState,
            "environment": EnvironmentState,
            "ui": UiState,
        }
        for field_name, expected_type in expected_groups.items():
            if not isinstance(getattr(self, field_name), expected_type):
                raise VehicleStateValidationError(
                    "INVALID_STATE_GROUP", f"{field_name} must be {expected_type.__name__}"
                )
        if not isinstance(self.active_actions, tuple) or not all(
            isinstance(action, ActiveAction) for action in self.active_actions
        ):
            raise VehicleStateValidationError(
                "INVALID_ACTIVE_ACTIONS", "active_actions must be a tuple of ActiveAction"
            )
        if self.transmission.gear is Gear.PARK and self.motion.speed_kph != 0:
            raise VehicleStateValidationError(
                "PARK_REQUIRES_STOPPED", "gear=P requires speed_kph=0"
            )
        if not self.power.powered_on:
            running_adas = (
                self.adas.acc_state is AccState.ACTIVE
                or self.adas.hda_active
                or self.adas.autopark_state is AutoparkState.ACTIVE
            )
            running_intents = {"activate_aac", "activate_hda", "activate_autopark"}
            if running_adas or any(action.intent in running_intents for action in self.active_actions):
                raise VehicleStateValidationError(
                    "POWER_OFF_ACTIVE_ADAS",
                    "powered-off vehicle cannot keep AAC, HDA or autopark active",
                )
        action_ids = tuple(action.action_id for action in self.active_actions)
        if len(action_ids) != len(set(action_ids)):
            raise VehicleStateValidationError(
                "DUPLICATE_ACTIVE_ACTION", "active action IDs must be unique"
            )

    def to_guardrail_snapshot(self) -> dict[str, Any]:
        """Return the closed JSON-ready PIP projection required by ViGuard.

        Source fields retain the ViGuard contract names.  Derived fields are
        calculated only from validated source groups and are not stored twice.
        """

        unavailable = sorted(
            item.field_name for item in self.pip_field_provenance if not item.available
        )
        if unavailable:
            raise VehicleStateValidationError(
                "INCOMPLETE_GUARDRAIL_SNAPSHOT",
                f"unavailable PIP fields: {', '.join(unavailable)}",
            )
        return {
            "schema_version": VEHICLE_STATE_SCHEMA_VERSION,
            "state_version": self.state_version,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "speed": self.motion.speed_kph,
            "gear": self.transmission.gear.value,
            "epb": self.transmission.epb_engaged,
            "battery_pct": self.power.battery_pct,
            "acc_state": self.adas.acc_state.value,
            "hand_on_steeringwheel": self.adas.hand_on_steeringwheel,
            "profile": self.cabin.profile.value,
            "esc": self.adas.esc_active,
            "avh": self.adas.avh_active,
            "fog_light": self.lighting.fog_light,
            "hazard_light": self.lighting.hazard_light,
            "highbeam_mode": self.lighting.highbeam.value,
            "lowbeam_mode": self.lighting.lowbeam.value,
            "door_lock_state": self.access.door_lock_state.value,
            "rain_sensor": self.environment.rain_sensor,
            "ambient_light": self.environment.ambient_light.value,
            "camp_mode_active": self.modes.camp_mode_active,
            "pet_mode_active": self.modes.pet_mode_active,
            "valet_mode_active": self.modes.valet_mode_active,
            "autopark_state": self.adas.autopark_state.value,
        }


def _finite_range(value: float, field_name: str, minimum: float, maximum: float | None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise VehicleStateValidationError(
            "INVALID_NUMERIC_FIELD", f"{field_name} must be a finite number"
        )
    if value < minimum or (maximum is not None and value > maximum):
        upper = "infinity" if maximum is None else str(maximum)
        raise VehicleStateValidationError(
            "NUMERIC_FIELD_OUT_OF_RANGE",
            f"{field_name} must be in [{minimum}, {upper}]",
        )


def _require_bool(value: object, field_name: str) -> None:
    if not isinstance(value, bool):
        raise VehicleStateValidationError(
            "INVALID_BOOLEAN_FIELD", f"{field_name} must be boolean"
        )


def _require_enum(value: object, enum_type: type[Enum], field_name: str) -> None:
    if not isinstance(value, enum_type):
        raise VehicleStateValidationError(
            "INVALID_ENUM_FIELD", f"{field_name} must be {enum_type.__name__}"
        )


def _require_aware_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise VehicleStateValidationError(
            "INVALID_TIMESTAMP", f"{field_name} must be a datetime"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise VehicleStateValidationError(
            "NAIVE_TIMESTAMP", f"{field_name} must include a timezone"
        )


DEFAULT_VEHICLE_STATE = VehicleState(
    state_version=0,
    timestamp=datetime(1970, 1, 1, tzinfo=timezone.utc),
    pip_field_provenance=pip_provenance(
        StateSource.PRESET, datetime(1970, 1, 1, tzinfo=timezone.utc)
    ),
)
