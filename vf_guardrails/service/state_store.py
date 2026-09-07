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
