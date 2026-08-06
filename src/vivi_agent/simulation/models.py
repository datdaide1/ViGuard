"""Simulation Control API data models (SIM-01).

Defines the typed boundary for operator-driven vehicle state manipulation.
These models are **not** exposed to the Agent's tool registry — they exist
solely for the simulation/demo UI layer.

Design notes
------------
* All dataclasses are frozen for thread-safety and immutability.
* ``SimulationControlField`` enumerates every axis the operator can tweak
  individually; batch mutations compose multiple fields atomically.
* ``SimulationResult`` carries both the committed state and any monitor
  evaluation results so the UI can display safety feedback inline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SimulationPresetId(str, Enum):
    """Identifiers for the five required simulation presets."""

    PARKED = "parked"
    DRIVING = "driving"
    HIGHWAY_HDA = "highway_hda"
    CHARGING = "charging"
    CAMP = "camp"


class SimulationControlField(str, Enum):
    """Operator-controllable state axes."""

    POWER = "power"
    GEAR = "gear"
    SPEED = "speed"
    RAIN = "rain"
    AMBIENT_LIGHT = "ambient_light"
    OBSTACLE = "obstacle"
    DRIVER_ATTENTION = "driver_attention"


# ---------------------------------------------------------------------------
# Control request
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SimulationControl:
    """A single operator control mutation request.

    Attributes
    ----------
    field:
        Which state axis to modify.
    value:
        The new value.  Type depends on ``field``:

        * POWER → bool (powered_on)
        * GEAR → str (Gear enum value: "P", "R", "N", "D")
        * SPEED → float (km/h, >= 0)
        * RAIN → bool
        * AMBIENT_LIGHT → str ("day" or "night")
        * OBSTACLE → bool
        * DRIVER_ATTENTION → dict with keys ``hand_on_wheel: bool``,
          optionally ``driver_present: bool``
    """

    field: SimulationControlField
    value: Any

    def __post_init__(self) -> None:
        if not isinstance(self.field, SimulationControlField):
            raise ValueError(f"field must be SimulationControlField, got {type(self.field).__name__}")
        _validate_control_value(self.field, self.value)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SimulationResult:
    """Outcome of a simulation control or preset application.

    Attributes
    ----------
    success:
        ``True`` if the state transition was committed.
    state_version:
        The ``state_version`` of the snapshot.
    event_id:
        UUID of the emitted ``StateChangedEvent``, or ``None`` on failure.
    monitor_results:
        Results from ``GuardrailMonitorAdapter.on_state_changed()``, or
        empty list if no monitor is attached.
    error:
        Human-readable error message on failure, or ``None`` on success.
    """

    success: bool
    state_version: int
    event_id: str | None = None
    monitor_results: tuple[dict[str, Any], ...] = ()
    error: str | None = None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_control_value(ctrl_field: SimulationControlField, value: Any) -> None:
    """Validate that ``value`` is acceptable for the given control field."""

    if ctrl_field is SimulationControlField.POWER:
        if not isinstance(value, bool):
            raise ValueError(f"POWER value must be bool, got {type(value).__name__}")

    elif ctrl_field is SimulationControlField.GEAR:
        valid_gears = {"P", "R", "N", "D"}
        if value not in valid_gears:
            raise ValueError(f"GEAR value must be one of {valid_gears}, got {value!r}")

    elif ctrl_field is SimulationControlField.SPEED:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"SPEED value must be a number, got {type(value).__name__}")
        if value < 0:
            raise ValueError(f"SPEED value must be >= 0, got {value}")

    elif ctrl_field is SimulationControlField.RAIN:
        if not isinstance(value, bool):
            raise ValueError(f"RAIN value must be bool, got {type(value).__name__}")

    elif ctrl_field is SimulationControlField.AMBIENT_LIGHT:
        valid_lights = {"day", "night"}
        if value not in valid_lights:
            raise ValueError(f"AMBIENT_LIGHT value must be one of {valid_lights}, got {value!r}")

    elif ctrl_field is SimulationControlField.OBSTACLE:
        if not isinstance(value, bool):
            raise ValueError(f"OBSTACLE value must be bool, got {type(value).__name__}")

    elif ctrl_field is SimulationControlField.DRIVER_ATTENTION:
        if not isinstance(value, dict):
            raise ValueError(
                f"DRIVER_ATTENTION value must be a dict, got {type(value).__name__}"
            )
        if "hand_on_wheel" not in value:
            raise ValueError("DRIVER_ATTENTION value must contain 'hand_on_wheel' key")
        if not isinstance(value["hand_on_wheel"], bool):
            raise ValueError("DRIVER_ATTENTION 'hand_on_wheel' must be bool")
        if "driver_present" in value and not isinstance(value["driver_present"], bool):
            raise ValueError("DRIVER_ATTENTION 'driver_present' must be bool")
