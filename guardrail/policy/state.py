"""Canonical vehicle-state schema for constraint evaluation.

Field names and enum spellings follow the workbook ``condition`` column exactly
(via ``golden-dataset/.../tools/derive_witness_states.py`` ``DOMAINS``), which is
the source of truth per decision D3/D4:

  - ``speed``            not ``speed_kmh``
  - ``battery_pct``      not ``battery_level``
  - ``door_lock_state``  ("locked"/"unlocked"/None) not ``doors_locked`` bool
  - ``ambient_light``    lowercase "day"/"night"
  - ``profile``          "OWNER"/"GUEST"/"VALET"

The 109 rules reference exactly 21 condition variables. 19 are vehicle state;
2 are request parameters (``target_angle`` for seat intents, ``kb_has_feature``
for ``explain_feature``) supplied per request, not stored on the vehicle.

DEFAULTS below are a Phase 1 assumption (a "parked, safe, daytime, healthy"
snapshot) used to complete the partial states in the golden dataset and witness
files. Flagged for review — see docs/DECISIONS.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

# 19 vehicle-state condition variables + workbook-accurate defaults.
_STATE_DEFAULTS: dict[str, Any] = {
    "gear": "P",
    "speed": 0,
    "rain_sensor": False,
    "ambient_light": "day",
    "battery_pct": 100,
    "avh": True,
    "epb": True,
    "camp_mode_active": False,
    "pet_mode_active": False,
    "valet_mode_active": False,
    "profile": "OWNER",
    "autopark_state": "INACTIVE",
    "acc_state": "INACTIVE",
    "hand_off_wheel_duration_seconds": 0,
    "fog_light": False,
    "hazard_light": False,
    "lowbeam_mode": "Off",
    "esc": True,
    "door_lock_state": "locked",
}

# 2 request-parameter condition variables (no vehicle default — supplied per request).
REQUEST_PARAMS: frozenset[str] = frozenset({"target_angle", "kb_has_feature"})

# Every variable the 109 rules can reference.
CONDITION_VARIABLES: frozenset[str] = frozenset(_STATE_DEFAULTS) | REQUEST_PARAMS


@dataclass(frozen=True)
class VehicleState:
    """Immutable, complete vehicle-state snapshot."""

    gear: str = "P"
    speed: float = 0
    rain_sensor: bool | None = False
    ambient_light: str = "day"
    battery_pct: float | None = 100
    avh: bool | None = True
    epb: bool = True
    camp_mode_active: bool = False
    pet_mode_active: bool = False
    valet_mode_active: bool = False
    profile: str = "OWNER"
    autopark_state: str = "INACTIVE"
    acc_state: str = "INACTIVE"
    hand_off_wheel_duration_seconds: float = 0
    fog_light: bool = False
    hazard_light: bool = False
    lowbeam_mode: str = "Off"
    esc: bool = True
    door_lock_state: str | None = "locked"

    @classmethod
    def from_partial(cls, overrides: dict[str, Any] | None) -> "VehicleState":
        """Complete a partial state dict (golden-dataset / witness style) onto defaults."""
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in (overrides or {}).items() if k in known}
        unknown = set(overrides or {}) - known - REQUEST_PARAMS
        if unknown:
            raise ValueError(f"unknown vehicle_state keys: {sorted(unknown)}")
        return cls(**data)

    def as_condition_values(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}
