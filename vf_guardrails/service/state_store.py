"""Guardrail-owned Vehicle State Mock (P2-D2).

On the action path the Agent does **not** send vehicle state -- the Guardrail
owns it. ``state_version`` is a monotonic ``int`` that increments on every
mutation; each request reads one immutable snapshot ``(VehicleState,
state_version)`` so a concurrent mutation can never tear a single evaluation.

Presets exist so tests / demos can put the car into a known situation
(``parked_safe`` / ``driving`` / ``rainy`` / ``low_battery``) in one call.

(The monitor path is different: there the Agent *does* send a ``vehicle_state``
snapshot. That branch is handled separately in the HTTP layer -- see
PHASE2_PLAN.md 2'.3 -- and does not touch this store.)
"""
from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any

from policy import VehicleState

# JSON-type expectations per VehicleState field, for validating an agent-supplied
# ``vehicle_state`` snapshot off the wire (monitor path) before it reaches the
# engine -- an int/float rule comparison against a string would otherwise raise
# deep inside condition evaluation and escape as a transport failure.
_BOOL_FIELDS = frozenset(
    {"rain_sensor", "avh", "epb", "camp_mode_active", "pet_mode_active",
     "valet_mode_active", "fog_light", "hazard_light", "esc"}
)
_NUMERIC_FIELDS = frozenset({"speed", "battery_pct", "hand_off_wheel_duration_seconds"})
_STRING_FIELDS = frozenset(
    {"gear", "ambient_light", "profile", "autopark_state", "acc_state",
     "lowbeam_mode", "door_lock_state"}
)
_NULLABLE_FIELDS = frozenset({"rain_sensor", "avh", "battery_pct", "door_lock_state"})


def validate_wire_vehicle_state(raw: dict[str, Any]) -> VehicleState:
    """Type-check an agent-supplied snapshot, then complete it onto the defaults.

    Raises ``ValueError`` (mapped to ``INVALID_VEHICLE_STATE`` by the HTTP layer)
    on an unknown field or a value whose JSON type is wrong for that field.
    """

    for key, value in raw.items():
        if key in _NULLABLE_FIELDS and value is None:
            continue
        if key in _BOOL_FIELDS:
            if not isinstance(value, bool):
                raise ValueError(f"vehicle_state.{key} must be a boolean")
        elif key in _NUMERIC_FIELDS:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"vehicle_state.{key} must be a number")
        elif key in _STRING_FIELDS:
            if not isinstance(value, str):
                raise ValueError(f"vehicle_state.{key} must be a string")
        # unknown keys are rejected by VehicleState.from_partial below
    return VehicleState.from_partial(raw)

# Named starting situations. Each is a full snapshot completed onto the Phase 1
# _STATE_DEFAULTS ("parked, safe, daytime, healthy").
PRESETS: dict[str, dict[str, Any]] = {
    "parked_safe": {},  # the defaults as-is
    "driving": {"gear": "D", "speed": 50},
    "rainy": {"gear": "D", "speed": 40, "rain_sensor": True, "lowbeam_mode": "On"},
    "low_battery": {"gear": "P", "speed": 0, "battery_pct": 8},
}


class VehicleStateStore:
    """Mutable holder around an immutable :class:`VehicleState` snapshot."""

    def __init__(
        self, state: VehicleState | None = None, *, state_version: int = 1
    ) -> None:
        if state_version < 1:
            raise ValueError("state_version must start at >= 1")
        self._lock = threading.Lock()
        self._state = state or VehicleState()
        self._version = state_version

    def snapshot(self) -> tuple[VehicleState, int]:
        """Return the current immutable state and its version, read atomically."""

        with self._lock:
            return self._state, self._version

    @property
    def state_version(self) -> int:
        with self._lock:
            return self._version

    def mutate(self, **overrides: Any) -> tuple[VehicleState, int]:
        """Apply field overrides, bump the version, return the new snapshot."""

        if not overrides:
            raise ValueError("mutate() requires at least one field override")
        unknown = set(overrides) - {f for f in VehicleState().as_condition_values()}
        if unknown:
            raise ValueError(f"unknown vehicle_state fields: {sorted(unknown)}")
        with self._lock:
            self._state = replace(self._state, **overrides)
            self._version += 1
            return self._state, self._version

    def apply_preset(self, name: str) -> tuple[VehicleState, int]:
        """Reset the state to a named preset and bump the version."""

        if name not in PRESETS:
            raise KeyError(f"unknown preset {name!r}; choose from {sorted(PRESETS)}")
        with self._lock:
            self._state = VehicleState(**PRESETS[name])
            self._version += 1
            return self._state, self._version
