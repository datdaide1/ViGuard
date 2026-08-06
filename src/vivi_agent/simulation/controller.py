"""Simulation Controller — operator-facing state mutation API (SIM-01).

``SimulationController`` is the single entry point for demo/simulation UI to
manipulate vehicle state.  Every mutation:

1. Goes through ``VehicleStateMachine.apply()`` with ``ActorKind.OPERATOR``
   (never ``AGENT``), ensuring operator events are never recorded as agent
   execution.
2. Triggers ``GuardrailMonitorAdapter.on_state_changed()`` if a monitor
   adapter is attached, so continuous active actions are re-evaluated against
   the new state.
3. Returns a ``SimulationResult`` with the committed snapshot, event ID, and
   monitor evaluation results.

This module is **NOT** registered in the Agent's tool registry.  The model
must never see these controls.

Design notes
------------
* Individual field setters (``set_power``, ``set_gear``, …) are thin wrappers
  around ``_apply_patch`` that build the appropriate ``dataclasses.replace``
  patch function.
* ``apply_controls`` batches multiple field mutations into a single atomic
  transition — the patch function composes all field changes before handing
  the candidate to ``VehicleStateMachine``.
* ``apply_preset`` uses ``get_simulation_preset`` to materialise a
  deterministic state, then replaces the machine's state atomically.
* ``reset`` delegates to ``VehicleStateMachine.reset("parked_powered_off")``
  which uses ``ActorKind.SYSTEM``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from typing import Any

from vivi_agent.vehicle.state.events import ActorKind
from vivi_agent.vehicle.state.machine import (
    TransitionError,
    VehicleStateMachine,
    VersionConflictError,
)
from vivi_agent.vehicle.state.model import (
    AmbientLight,
    Gear,
    MotionPhase,
    MotionState,
    VehicleState,
    VehicleStateValidationError,
)

from .models import (
    SimulationControl,
    SimulationControlField,
    SimulationPresetId,
    SimulationResult,
)
from .presets import get_simulation_preset

logger = logging.getLogger(__name__)


class SimulationController:
    """Operator-facing API for manipulating vehicle state in demo/simulation.

    Parameters
    ----------
    machine:
        The shared ``VehicleStateMachine`` instance.
    monitor_adapter:
        Optional ``GuardrailMonitorAdapter``.  When provided, every state
        change triggers a monitor re-evaluation of active actions.
    """

    def __init__(
        self,
        machine: VehicleStateMachine,
        monitor_adapter: Any | None = None,
    ) -> None:
        self._machine = machine
        self._monitor = monitor_adapter

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    @property
    def machine(self) -> VehicleStateMachine:
        """The underlying ``VehicleStateMachine``."""
        return self._machine

    def snapshot(self) -> VehicleState:
        """Return the current vehicle state snapshot."""
        return self._machine.snapshot()

    # ------------------------------------------------------------------
    # Individual field controls
    # ------------------------------------------------------------------

    def set_power(
        self,
        powered_on: bool,
        *,
        operator_id: str = "operator",
        correlation_id: str | None = None,
    ) -> SimulationResult:
        """Set vehicle power state."""

        def _patch(state: VehicleState) -> VehicleState:
            return replace(state, power=replace(state.power, powered_on=powered_on))

        return self._apply_patch(
            _patch, operator_id=operator_id, correlation_id=correlation_id
        )

    def set_gear(
        self,
        gear: str | Gear,
        *,
        operator_id: str = "operator",
        correlation_id: str | None = None,
    ) -> SimulationResult:
        """Set transmission gear (P, R, N, D)."""

        def _patch(state: VehicleState) -> VehicleState:
            gear_enum = Gear(gear) if isinstance(gear, str) else gear
            return replace(
                state,
                transmission=replace(state.transmission, gear=gear_enum),
            )

        return self._apply_patch(
            _patch, operator_id=operator_id, correlation_id=correlation_id
        )

    def set_speed(
        self,
        speed_kph: float,
        *,
        operator_id: str = "operator",
        correlation_id: str | None = None,
    ) -> SimulationResult:
        """Set vehicle speed in km/h.

        Automatically adjusts motion phase (STOPPED/MOVING), gear (PARK→DRIVE
        when speed > 0), and EPB (disengage when moving).
        """

        def _patch(state: VehicleState) -> VehicleState:
            return _patch_speed(state, speed_kph)

        return self._apply_patch(
            _patch, operator_id=operator_id, correlation_id=correlation_id
        )

    def set_rain(
        self,
        raining: bool,
        *,
        operator_id: str = "operator",
        correlation_id: str | None = None,
    ) -> SimulationResult:
        """Set rain sensor state."""

        def _patch(state: VehicleState) -> VehicleState:
            return replace(
                state,
                environment=replace(state.environment, rain_sensor=raining),
            )

        return self._apply_patch(
            _patch, operator_id=operator_id, correlation_id=correlation_id
        )

    def set_ambient_light(
        self,
        light: str | AmbientLight,
        *,
        operator_id: str = "operator",
        correlation_id: str | None = None,
    ) -> SimulationResult:
        """Set ambient light condition (day/night)."""

        def _patch(state: VehicleState) -> VehicleState:
            light_enum = AmbientLight(light) if isinstance(light, str) else light
            return replace(
                state,
                environment=replace(state.environment, ambient_light=light_enum),
            )

        return self._apply_patch(
            _patch, operator_id=operator_id, correlation_id=correlation_id
        )

    def set_obstacle(
        self,
        detected: bool,
        *,
        operator_id: str = "operator",
        correlation_id: str | None = None,
    ) -> SimulationResult:
        """Set obstacle detection state."""

        def _patch(state: VehicleState) -> VehicleState:
            return replace(
                state,
                environment=replace(state.environment, obstacle_detected=detected),
            )

        return self._apply_patch(
            _patch, operator_id=operator_id, correlation_id=correlation_id
        )

    def set_driver_attention(
        self,
        hand_on_wheel: bool,
        *,
        driver_present: bool = True,
        operator_id: str = "operator",
        correlation_id: str | None = None,
    ) -> SimulationResult:
        """Set driver attention indicators."""

        def _patch(state: VehicleState) -> VehicleState:
            return replace(
                state,
                adas=replace(state.adas, hand_on_steeringwheel=hand_on_wheel),
                environment=replace(state.environment, driver_present=driver_present),
            )

        return self._apply_patch(
            _patch, operator_id=operator_id, correlation_id=correlation_id
        )

    # ------------------------------------------------------------------
    # Preset application
    # ------------------------------------------------------------------

    def apply_preset(
        self,
        preset_id: SimulationPresetId | str,
        *,
        operator_id: str = "operator",
        correlation_id: str | None = None,
        seed: int | None = None,
    ) -> SimulationResult:
        """Replace the full vehicle state with a named simulation preset.

        Parameters
        ----------
        preset_id:
            Preset to apply.  Accepts ``SimulationPresetId`` or its string
            value.
        seed:
            Deterministic seed for reproducible state.  Currently reserved.
        """
        corr_id = correlation_id or f"sim-preset-{uuid.uuid4().hex[:8]}"

        def _patch(state: VehicleState) -> VehicleState:
            # Build the preset state; version and timestamp will be stamped
            # by VehicleStateMachine.apply() so we pass placeholder values.
            resolved_id = (
                SimulationPresetId(preset_id)
                if isinstance(preset_id, str)
                else preset_id
            )
            preset_state = get_simulation_preset(
                resolved_id,
                state_version=state.state_version,
                timestamp=state.timestamp,
                seed=seed,
            )
            return preset_state

        return self._apply_patch(
            _patch, operator_id=operator_id, correlation_id=corr_id
        )

    # ------------------------------------------------------------------
    # Batch control
    # ------------------------------------------------------------------

    def apply_controls(
        self,
        controls: list[SimulationControl],
        *,
        operator_id: str = "operator",
        correlation_id: str | None = None,
    ) -> SimulationResult:
        """Apply multiple control mutations in a single atomic transition.

        All controls are composed into one patch function.  If any individual
        control would produce an invalid state, the entire batch is rejected.
        """
        if not controls:
            return SimulationResult(
                success=True,
                state_version=self._machine.snapshot().state_version,
                error=None,
            )

        def _patch(state: VehicleState) -> VehicleState:
            result = state
            for ctrl in controls:
                result = _apply_single_control(result, ctrl)
            return result

        return self._apply_patch(
            _patch,
            operator_id=operator_id,
            correlation_id=correlation_id,
        )

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(
        self,
        *,
        operator_id: str = "operator",
        correlation_id: str | None = None,
    ) -> SimulationResult:
        """Reset vehicle state to the default parked preset.

        Uses ``VehicleStateMachine.reset()`` with ``ActorKind.SYSTEM``.
        """
        corr_id = correlation_id or f"sim-reset-{uuid.uuid4().hex[:8]}"

        try:
            event = self._machine.reset(
                "parked_powered_off",
                actor_id=operator_id,
                correlation_id=corr_id,
            )
            monitor_results = self._trigger_monitor(event.snapshot)
            return SimulationResult(
                success=True,
                state_version=event.next_version,
                event_id=event.event_id,
                monitor_results=tuple(monitor_results),
            )
        except (KeyError, ValueError, VehicleStateValidationError) as exc:
            logger.warning("Simulation reset failed: %s", exc)
            return SimulationResult(
                success=False,
                state_version=self._machine.snapshot().state_version,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_patch(
        self,
        patch_fn: Any,
        *,
        operator_id: str,
        correlation_id: str | None,
    ) -> SimulationResult:
        """Apply a patch function through the state machine with OPERATOR actor."""
        corr_id = correlation_id or f"sim-ctrl-{uuid.uuid4().hex[:8]}"

        try:
            event = self._machine.apply(
                patch_fn,
                actor_kind=ActorKind.OPERATOR,
                actor_id=operator_id,
                correlation_id=corr_id,
            )
            monitor_results = self._trigger_monitor(event.snapshot)
            return SimulationResult(
                success=True,
                state_version=event.next_version,
                event_id=event.event_id,
                monitor_results=tuple(monitor_results),
            )
        except (
            VehicleStateValidationError,
            TransitionError,
            VersionConflictError,
            ValueError,
            KeyError,
        ) as exc:
            logger.warning("Simulation control failed: %s", exc)
            return SimulationResult(
                success=False,
                state_version=self._machine.snapshot().state_version,
                error=str(exc),
            )

    def _trigger_monitor(self, new_state: VehicleState) -> list[dict[str, Any]]:
        """Trigger monitor re-evaluation after a state change."""
        if self._monitor is None:
            return []
        try:
            return self._monitor.on_state_changed(new_state)
        except Exception as exc:
            logger.warning("Monitor evaluation failed after simulation control: %s", exc)
            return []


# ---------------------------------------------------------------------------
# Shared patch logic
# ---------------------------------------------------------------------------

def _patch_speed(state: VehicleState, speed_kph: float) -> VehicleState:
    """Apply a speed change with gear/EPB auto-adjustment for physical consistency.

    Shared by ``SimulationController.set_speed`` and the batch
    ``SimulationControlField.SPEED`` handler in ``_apply_single_control`` so
    the auto-adjust rule (PARK→DRIVE, EPB disengage when moving) lives in
    exactly one place.
    """
    phase = MotionPhase.MOVING if speed_kph > 0 else MotionPhase.STOPPED
    new_motion = MotionState(speed_kph=float(speed_kph), phase=phase)

    new_transmission = state.transmission
    if speed_kph > 0:
        if state.transmission.gear is Gear.PARK:
            new_transmission = replace(
                state.transmission, gear=Gear.DRIVE, epb_engaged=False
            )
        elif state.transmission.epb_engaged:
            new_transmission = replace(state.transmission, epb_engaged=False)

    return replace(state, motion=new_motion, transmission=new_transmission)


# ---------------------------------------------------------------------------
# Batch control field application
# ---------------------------------------------------------------------------

def _apply_single_control(state: VehicleState, ctrl: SimulationControl) -> VehicleState:
    """Apply a single ``SimulationControl`` to a ``VehicleState`` snapshot.

    This is a pure function: it returns a new snapshot without mutating the
    input.  It does NOT go through the state machine — callers must feed
    the final composed state to ``VehicleStateMachine.apply()``.
    """
    f = ctrl.field
    v = ctrl.value

    if f is SimulationControlField.POWER:
        return replace(state, power=replace(state.power, powered_on=v))

    if f is SimulationControlField.GEAR:
        gear_enum = Gear(v)
        return replace(
            state, transmission=replace(state.transmission, gear=gear_enum)
        )

    if f is SimulationControlField.SPEED:
        return _patch_speed(state, v)

    if f is SimulationControlField.RAIN:
        return replace(
            state, environment=replace(state.environment, rain_sensor=v)
        )

    if f is SimulationControlField.AMBIENT_LIGHT:
        light_enum = AmbientLight(v)
        return replace(
            state, environment=replace(state.environment, ambient_light=light_enum)
        )

    if f is SimulationControlField.OBSTACLE:
        return replace(
            state, environment=replace(state.environment, obstacle_detected=v)
        )

    if f is SimulationControlField.DRIVER_ATTENTION:
        hand = v["hand_on_wheel"]
        present = v.get("driver_present", True)
        return replace(
            state,
            adas=replace(state.adas, hand_on_steeringwheel=hand),
            environment=replace(state.environment, driver_present=present),
        )

    raise ValueError(f"Unknown control field: {f}")  # pragma: no cover
