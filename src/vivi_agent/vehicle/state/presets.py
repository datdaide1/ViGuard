"""Deterministic Vehicle State preset schema.

Presets describe valid initial conditions only.  Applying a preset and emitting
events is a VEH-02/SIM-01 responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType

from .model import (
    DEFAULT_VEHICLE_STATE,
    AdasState,
    Gear,
    MotionPhase,
    MotionState,
    PowerState,
    StateSource,
    TransmissionState,
    VehicleState,
    pip_provenance,
)


@dataclass(frozen=True)
class VehicleStatePreset:
    preset_id: str
    description: str
    state: VehicleState


_PRESET_DEFINITIONS = (
    VehicleStatePreset(
        preset_id="parked_powered_off",
        description="Default locked vehicle, parked and powered off.",
        state=DEFAULT_VEHICLE_STATE,
    ),
    VehicleStatePreset(
        preset_id="parked_ready",
        description="Powered-on vehicle safely parked with EPB engaged.",
        state=replace(DEFAULT_VEHICLE_STATE, power=PowerState(powered_on=True)),
    ),
    VehicleStatePreset(
        preset_id="charging",
        description="Parked vehicle charging with cabin/accessory power available.",
        state=replace(
            DEFAULT_VEHICLE_STATE,
            power=PowerState(powered_on=True, charging=True),
        ),
    ),
    VehicleStatePreset(
        preset_id="moving_drive",
        description="Powered-on vehicle moving in Drive at a synthetic demo speed.",
        state=replace(
            DEFAULT_VEHICLE_STATE,
            power=PowerState(powered_on=True),
            motion=MotionState(speed_kph=30.0, phase=MotionPhase.MOVING),
            transmission=TransmissionState(gear=Gear.DRIVE, epb_engaged=False),
            adas=AdasState(),
        ),
    ),
)

PRESETS = MappingProxyType(
    {preset.preset_id: preset for preset in _PRESET_DEFINITIONS}
)
if len(PRESETS) != len(_PRESET_DEFINITIONS):
    raise RuntimeError("Vehicle preset IDs must be unique")


def get_preset(preset_id: str, *, state_version: int, timestamp: datetime) -> VehicleState:
    """Materialize a preset with caller-owned version and observation time."""

    try:
        preset = PRESETS[preset_id]
    except KeyError as exc:
        raise KeyError(f"Unknown vehicle preset: {preset_id!r}") from exc
    return replace(
        preset.state,
        state_version=state_version,
        timestamp=timestamp,
        pip_field_provenance=pip_provenance(StateSource.PRESET, timestamp),
    )
