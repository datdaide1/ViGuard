"""Simulation preset catalog (SIM-01).

Defines the five required simulation presets that produce deterministic
``VehicleState`` snapshots.  Each preset builds its state via
``dataclasses.replace()`` on ``DEFAULT_VEHICLE_STATE`` with
``StateSource.PRESET`` provenance, consistent with the VEH-01 preset pattern.

The ``seed`` parameter is accepted for future extensibility (e.g. randomised
environment variations) but currently has no effect — all presets are fully
deterministic regardless of seed.

Design notes
------------
* Presets are stored in a ``MappingProxyType`` keyed by ``SimulationPresetId``
  for O(1) lookup and immutability.
* Each preset's ``VehicleState`` passes all invariant validation at module load
  time — an invalid preset definition is a startup crash, not a runtime
  surprise.
* Highway/HDA preset requires ``acc_state=ACTIVE`` because VehicleState
  enforces ``HDA_REQUIRES_ACTIVE_ACC``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from types import MappingProxyType

from vehicle_agent.vehicle.state.model import (
    DEFAULT_VEHICLE_STATE,
    AccState,
    AdasState,
    Gear,
    ModeState,
    MotionPhase,
    MotionState,
    PowerState,
    StateSource,
    TransmissionState,
    VehicleState,
    pip_provenance,
)

from .models import SimulationPresetId


@dataclass(frozen=True)
class SimulationPreset:
    """A named, deterministic vehicle state configuration for simulation."""

    preset_id: SimulationPresetId
    description: str
    state: VehicleState


# ---------------------------------------------------------------------------
# Preset definitions
# ---------------------------------------------------------------------------

_PRESET_DEFINITIONS: tuple[SimulationPreset, ...] = (
    SimulationPreset(
        preset_id=SimulationPresetId.PARKED,
        description="Default parked vehicle, powered off, gear P, speed 0, EPB engaged.",
        state=DEFAULT_VEHICLE_STATE,
    ),
    SimulationPreset(
        preset_id=SimulationPresetId.DRIVING,
        description="Normal city driving: powered on, gear D, 30 km/h, EPB off.",
        state=replace(
            DEFAULT_VEHICLE_STATE,
            power=PowerState(powered_on=True),
            motion=MotionState(speed_kph=30.0, phase=MotionPhase.MOVING),
            transmission=TransmissionState(gear=Gear.DRIVE, epb_engaged=False),
        ),
    ),
    SimulationPreset(
        preset_id=SimulationPresetId.HIGHWAY_HDA,
        description=(
            "Highway driving with HDA active: powered on, gear D, 100 km/h, "
            "ACC active, HDA on, EPB off."
        ),
        state=replace(
            DEFAULT_VEHICLE_STATE,
            power=PowerState(powered_on=True),
            motion=MotionState(speed_kph=100.0, phase=MotionPhase.MOVING),
            transmission=TransmissionState(gear=Gear.DRIVE, epb_engaged=False),
            adas=AdasState(acc_state=AccState.ACTIVE, hda_active=True),
        ),
    ),
    SimulationPreset(
        preset_id=SimulationPresetId.CHARGING,
        description="Parked vehicle charging: powered on, charging true, gear P.",
        state=replace(
            DEFAULT_VEHICLE_STATE,
            power=PowerState(powered_on=True, charging=True),
        ),
    ),
    SimulationPreset(
        preset_id=SimulationPresetId.CAMP,
        description="Camp mode active: powered on, gear P, camp_mode on.",
        state=replace(
            DEFAULT_VEHICLE_STATE,
            power=PowerState(powered_on=True),
            modes=ModeState(camp_mode_active=True),
        ),
    ),
)

# Immutable lookup by SimulationPresetId
SIMULATION_PRESETS: MappingProxyType[SimulationPresetId, SimulationPreset] = (
    MappingProxyType({p.preset_id: p for p in _PRESET_DEFINITIONS})
)
if len(SIMULATION_PRESETS) != len(_PRESET_DEFINITIONS):
    raise RuntimeError("Simulation preset IDs must be unique")


def get_simulation_preset(
    preset_id: SimulationPresetId | str,
    *,
    state_version: int,
    timestamp: datetime,
    seed: int | None = None,
) -> VehicleState:
    """Materialise a simulation preset with caller-owned version and timestamp.

    Parameters
    ----------
    preset_id:
        Which preset to materialise (SimulationPresetId enum or string).
    state_version:
        The version number to stamp on the snapshot.
    timestamp:
        The observation timestamp (must be timezone-aware UTC).
    seed:
        Reserved for future randomised environment variations.  Currently
        ignored — all presets are fully deterministic.

    Returns
    -------
    VehicleState
        A fully validated, immutable snapshot.

    Raises
    ------
    KeyError
        Unknown ``preset_id``.
    """
    try:
        resolved_id = (
            SimulationPresetId(preset_id)
            if isinstance(preset_id, str)
            else preset_id
        )
        preset = SIMULATION_PRESETS[resolved_id]
    except (KeyError, ValueError) as exc:
        raise KeyError(f"Unknown simulation preset: {preset_id!r}") from exc

    return replace(
        preset.state,
        state_version=state_version,
        timestamp=timestamp,
        pip_field_provenance=pip_provenance(StateSource.PRESET, timestamp),
    )
