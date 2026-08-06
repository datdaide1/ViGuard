"""Simulation Control API package (SIM-01).

Provides operator-facing controls for manipulating vehicle state in demo and
simulation scenarios.  This package is **NOT** part of the Agent's tool
registry — the LLM model must never see these controls.
"""

from .controller import SimulationController
from .models import (
    SimulationControl,
    SimulationControlField,
    SimulationPresetId,
    SimulationResult,
)
from .presets import (
    SIMULATION_PRESETS,
    SimulationPreset,
    get_simulation_preset,
)

__all__ = [
    "SIMULATION_PRESETS",
    "SimulationControl",
    "SimulationControlField",
    "SimulationController",
    "SimulationPreset",
    "SimulationPresetId",
    "SimulationResult",
    "get_simulation_preset",
]
