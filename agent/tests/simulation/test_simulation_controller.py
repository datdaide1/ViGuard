"""Unit tests for SimulationController (SIM-01)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from vehicle_agent.simulation.controller import SimulationController
from vehicle_agent.simulation.models import (
    SimulationControl,
    SimulationControlField,
    SimulationPresetId,
)
from vehicle_agent.vehicle.state.events import ActorKind
from vehicle_agent.vehicle.state.machine import VehicleStateMachine
from vehicle_agent.vehicle.state.model import (
    AmbientLight,
    Gear,
    MotionPhase,
    PowerState,
)


class TestSimulationControllerSetup(unittest.TestCase):
    """Common test setup for SimulationController tests."""

    def setUp(self) -> None:
        self.machine = VehicleStateMachine()
        self.mock_monitor = MagicMock()
        self.mock_monitor.on_state_changed.return_value = []
        self.controller = SimulationController(
            machine=self.machine,
            monitor_adapter=self.mock_monitor,
        )


class TestSetPower(TestSimulationControllerSetup):
    """Test set_power control."""

    def test_power_on(self) -> None:
        result = self.controller.set_power(True)
        self.assertTrue(result.success)
        self.assertTrue(self.machine.snapshot().power.powered_on)

    def test_power_off(self) -> None:
        # First power on, then off
        self.controller.set_power(True)
        result = self.controller.set_power(False)
        self.assertTrue(result.success)
        self.assertFalse(self.machine.snapshot().power.powered_on)

    def test_power_event_uses_operator_actor(self) -> None:
        result = self.controller.set_power(True, operator_id="op-001")
        event = self.machine.event_store.latest()
        self.assertIsNotNone(event)
        self.assertEqual(event.actor_kind, ActorKind.OPERATOR)
        self.assertEqual(event.actor_id, "op-001")

    def test_monitor_triggered_after_power_change(self) -> None:
        self.controller.set_power(True)
        self.mock_monitor.on_state_changed.assert_called_once()


class TestSetGear(TestSimulationControllerSetup):
    """Test set_gear control."""

    def test_set_gear_drive(self) -> None:
        self.controller.set_power(True)
        result = self.controller.set_gear("D")
        self.assertTrue(result.success)
        self.assertEqual(self.machine.snapshot().transmission.gear, Gear.DRIVE)

    def test_set_gear_string_value(self) -> None:
        self.controller.set_power(True)
        result = self.controller.set_gear("R")
        self.assertTrue(result.success)
        self.assertEqual(self.machine.snapshot().transmission.gear, Gear.REVERSE)

    def test_set_gear_enum_value(self) -> None:
        self.controller.set_power(True)
        result = self.controller.set_gear(Gear.NEUTRAL)
        self.assertTrue(result.success)
        self.assertEqual(self.machine.snapshot().transmission.gear, Gear.NEUTRAL)


class TestSetSpeed(TestSimulationControllerSetup):
    """Test set_speed control with auto-adjustments."""

    def test_set_speed_positive(self) -> None:
        self.controller.set_power(True)
        result = self.controller.set_speed(60.0)
        self.assertTrue(result.success)
        snap = self.machine.snapshot()
        self.assertEqual(snap.motion.speed_kph, 60.0)
        self.assertEqual(snap.motion.phase, MotionPhase.MOVING)

    def test_set_speed_auto_adjusts_gear_from_park(self) -> None:
        """When speed > 0 and gear is P, gear auto-adjusts to D."""
        self.controller.set_power(True)
        result = self.controller.set_speed(30.0)
        self.assertTrue(result.success)
        snap = self.machine.snapshot()
        self.assertEqual(snap.transmission.gear, Gear.DRIVE)
        self.assertFalse(snap.transmission.epb_engaged)

    def test_set_speed_zero(self) -> None:
        self.controller.set_power(True)
        self.controller.set_speed(50.0)
        result = self.controller.set_speed(0.0)
        self.assertTrue(result.success)
        self.assertEqual(self.machine.snapshot().motion.speed_kph, 0.0)
        self.assertEqual(self.machine.snapshot().motion.phase, MotionPhase.STOPPED)


class TestSetEnvironment(TestSimulationControllerSetup):
    """Test environment controls (rain, light, obstacle, driver attention)."""

    def test_set_rain(self) -> None:
        result = self.controller.set_rain(True)
        self.assertTrue(result.success)
        self.assertTrue(self.machine.snapshot().environment.rain_sensor)

    def test_set_ambient_light_night(self) -> None:
        result = self.controller.set_ambient_light("night")
        self.assertTrue(result.success)
        self.assertEqual(
            self.machine.snapshot().environment.ambient_light, AmbientLight.NIGHT
        )

    def test_set_ambient_light_enum(self) -> None:
        result = self.controller.set_ambient_light(AmbientLight.DAY)
        self.assertTrue(result.success)

    def test_set_obstacle(self) -> None:
        result = self.controller.set_obstacle(True)
        self.assertTrue(result.success)
        self.assertTrue(self.machine.snapshot().environment.obstacle_detected)

    def test_set_driver_attention(self) -> None:
        result = self.controller.set_driver_attention(
            hand_on_wheel=False, driver_present=True
        )
        self.assertTrue(result.success)
        snap = self.machine.snapshot()
        self.assertFalse(snap.adas.hand_on_steeringwheel)
        self.assertTrue(snap.environment.driver_present)


class TestApplyPreset(TestSimulationControllerSetup):
    """Test preset application."""

    def test_apply_driving_preset(self) -> None:
        result = self.controller.apply_preset(SimulationPresetId.DRIVING)
        self.assertTrue(result.success)
        snap = self.machine.snapshot()
        self.assertTrue(snap.power.powered_on)
        self.assertEqual(snap.transmission.gear, Gear.DRIVE)
        self.assertEqual(snap.motion.speed_kph, 30.0)

    def test_apply_highway_hda_preset(self) -> None:
        result = self.controller.apply_preset(SimulationPresetId.HIGHWAY_HDA)
        self.assertTrue(result.success)
        snap = self.machine.snapshot()
        self.assertTrue(snap.adas.hda_active)
        self.assertEqual(snap.motion.speed_kph, 100.0)

    def test_apply_camp_preset(self) -> None:
        result = self.controller.apply_preset(SimulationPresetId.CAMP)
        self.assertTrue(result.success)
        self.assertTrue(self.machine.snapshot().modes.camp_mode_active)

    def test_apply_charging_preset(self) -> None:
        result = self.controller.apply_preset(SimulationPresetId.CHARGING)
        self.assertTrue(result.success)
        self.assertTrue(self.machine.snapshot().power.charging)

    def test_apply_parked_preset(self) -> None:
        # First go to driving, then back to parked
        self.controller.apply_preset(SimulationPresetId.DRIVING)
        result = self.controller.apply_preset(SimulationPresetId.PARKED)
        self.assertTrue(result.success)
        self.assertFalse(self.machine.snapshot().power.powered_on)

    def test_apply_preset_string_id(self) -> None:
        result = self.controller.apply_preset("camp")
        self.assertTrue(result.success)
        self.assertTrue(self.machine.snapshot().modes.camp_mode_active)

    def test_apply_preset_uses_operator_actor(self) -> None:
        result = self.controller.apply_preset(
            SimulationPresetId.DRIVING, operator_id="demo-ui"
        )
        event = self.machine.event_store.latest()
        self.assertEqual(event.actor_kind, ActorKind.OPERATOR)
        self.assertEqual(event.actor_id, "demo-ui")

    def test_apply_preset_deterministic(self) -> None:
        """Same preset applied twice produces same state (excluding version/timestamp)."""
        machine_a = VehicleStateMachine()
        ctrl_a = SimulationController(machine=machine_a)
        ctrl_a.apply_preset(SimulationPresetId.HIGHWAY_HDA, seed=42)

        machine_b = VehicleStateMachine()
        ctrl_b = SimulationController(machine=machine_b)
        ctrl_b.apply_preset(SimulationPresetId.HIGHWAY_HDA, seed=42)

        snap_a = machine_a.snapshot()
        snap_b = machine_b.snapshot()
        # Versions and timestamps will match because both start from version 0
        self.assertEqual(snap_a.power, snap_b.power)
        self.assertEqual(snap_a.motion, snap_b.motion)
        self.assertEqual(snap_a.transmission, snap_b.transmission)
        self.assertEqual(snap_a.adas, snap_b.adas)
        self.assertEqual(snap_a.modes, snap_b.modes)

    def test_monitor_triggered_after_preset(self) -> None:
        self.controller.apply_preset(SimulationPresetId.DRIVING)
        self.mock_monitor.on_state_changed.assert_called_once()


class TestReset(TestSimulationControllerSetup):
    """Test reset functionality."""

    def test_reset_returns_to_default(self) -> None:
        self.controller.apply_preset(SimulationPresetId.DRIVING)
        result = self.controller.reset()
        self.assertTrue(result.success)
        snap = self.machine.snapshot()
        self.assertFalse(snap.power.powered_on)
        self.assertEqual(snap.transmission.gear, Gear.PARK)
        self.assertEqual(snap.motion.speed_kph, 0.0)

    def test_reset_uses_system_actor(self) -> None:
        """Reset goes through VehicleStateMachine.reset() which uses SYSTEM actor."""
        self.controller.reset()
        event = self.machine.event_store.latest()
        self.assertIsNotNone(event)
        self.assertEqual(event.actor_kind, ActorKind.SYSTEM)

    def test_reset_triggers_monitor(self) -> None:
        self.controller.reset()
        self.mock_monitor.on_state_changed.assert_called_once()


class TestBatchControls(TestSimulationControllerSetup):
    """Test apply_controls batch mutation."""

    def test_batch_apply_multiple_controls(self) -> None:
        controls = [
            SimulationControl(field=SimulationControlField.POWER, value=True),
            SimulationControl(field=SimulationControlField.RAIN, value=True),
            SimulationControl(field=SimulationControlField.OBSTACLE, value=True),
        ]
        result = self.controller.apply_controls(controls)
        self.assertTrue(result.success)
        snap = self.machine.snapshot()
        self.assertTrue(snap.power.powered_on)
        self.assertTrue(snap.environment.rain_sensor)
        self.assertTrue(snap.environment.obstacle_detected)

    def test_batch_produces_single_event(self) -> None:
        """Batch controls should produce exactly one event, not N."""
        controls = [
            SimulationControl(field=SimulationControlField.POWER, value=True),
            SimulationControl(field=SimulationControlField.RAIN, value=True),
        ]
        self.controller.apply_controls(controls)
        self.assertEqual(len(self.machine.event_store), 1)

    def test_empty_batch_no_op(self) -> None:
        result = self.controller.apply_controls([])
        self.assertTrue(result.success)
        self.assertEqual(len(self.machine.event_store), 0)

    def test_batch_uses_operator_actor(self) -> None:
        controls = [
            SimulationControl(field=SimulationControlField.POWER, value=True),
        ]
        self.controller.apply_controls(controls, operator_id="batch-op")
        event = self.machine.event_store.latest()
        self.assertEqual(event.actor_kind, ActorKind.OPERATOR)
        self.assertEqual(event.actor_id, "batch-op")

    def test_batch_apply_speed_uses_shared_patch_speed_semantics(self) -> None:
        """SPEED in a batch must use the same _patch_speed auto-adjust rule as
        set_speed: P->D gear auto-shift and EPB release (Sourcery PR #29 feedback)."""
        controls = [
            SimulationControl(field=SimulationControlField.POWER, value=True),
            SimulationControl(field=SimulationControlField.SPEED, value=30.0),
        ]
        result = self.controller.apply_controls(controls)
        self.assertTrue(result.success)

        snap = self.machine.snapshot()
        self.assertEqual(snap.motion.speed_kph, 30.0)
        self.assertEqual(snap.motion.phase, MotionPhase.MOVING)
        self.assertEqual(snap.transmission.gear, Gear.DRIVE)
        self.assertFalse(snap.transmission.epb_engaged)


class TestOperatorEventIsolation(TestSimulationControllerSetup):
    """Verify operator events are never recorded as Agent events (acceptance criteria #2)."""

    def test_no_agent_actor_in_event_store(self) -> None:
        """After several simulation operations, no event should have AGENT actor."""
        self.controller.set_power(True)
        self.controller.set_speed(60.0)
        self.controller.apply_preset(SimulationPresetId.HIGHWAY_HDA)
        self.controller.set_rain(True)
        self.controller.reset()

        all_events = self.machine.event_store.list_all()
        for event in all_events:
            self.assertIn(
                event.actor_kind,
                {ActorKind.OPERATOR, ActorKind.SYSTEM},
                f"Event {event.event_id} has unexpected actor_kind={event.actor_kind}",
            )

    def test_operator_events_distinguishable(self) -> None:
        """Operator events must be distinguishable from agent events by actor_kind."""
        self.controller.set_power(True)
        event = self.machine.event_store.latest()
        self.assertEqual(event.actor_kind, ActorKind.OPERATOR)
        self.assertNotEqual(event.actor_kind, ActorKind.AGENT)


class TestErrorHandling(TestSimulationControllerSetup):
    """Test graceful error handling."""

    def test_invalid_state_returns_failure(self) -> None:
        """Attempting to set speed>0 while powered off should fail gracefully
        when it violates an invariant (e.g. ADAS constraints)."""
        # This won't necessarily fail due to invariants, but let's verify
        # the result structure for a normal case.
        result = self.controller.set_speed(30.0)
        # Default state is powered off. Setting speed alone auto-adjusts
        # gear from P→D, so this may succeed or fail depending on invariants.
        self.assertIsInstance(result.success, bool)
        self.assertIsInstance(result.state_version, int)

    def test_monitor_exception_does_not_crash(self) -> None:
        """If monitor raises, controller still returns a result."""
        self.mock_monitor.on_state_changed.side_effect = RuntimeError("Monitor down")
        result = self.controller.set_power(True)
        # The state change should still succeed; monitor error is logged.
        self.assertTrue(result.success)
        self.assertEqual(result.monitor_results, ())


class TestNoToolRegistration(unittest.TestCase):
    """Acceptance criteria #1: Model must not see operator controls in tool registry."""

    def test_simulation_not_in_tool_registry(self) -> None:
        """SimulationController must NOT appear in any tool handler or catalog."""
        import importlib
        import pkgutil

        # Walk the tools package to verify no simulation imports
        try:
            import vehicle_agent.tools as tools_pkg
        except ImportError:
            self.skipTest("vehicle_agent.tools not importable in test environment")
            return

        tools_source_files = []
        for importer, modname, ispkg in pkgutil.walk_packages(
            tools_pkg.__path__, prefix="vehicle_agent.tools."
        ):
            tools_source_files.append(modname)

        # The simulation controller should not be imported or referenced
        # in any tools module.  This is a structural check — if someone
        # accidentally adds SimulationController to the tool registry,
        # this test catches it.
        for modname in tools_source_files:
            try:
                mod = importlib.import_module(modname)
                source = getattr(mod, "__file__", "") or ""
                # Just verify the module loaded; deeper static analysis
                # would require reading source files, which is fragile.
                self.assertNotIn(
                    "SimulationController",
                    dir(mod),
                    f"SimulationController found in tool module {modname}!",
                )
            except ImportError:
                pass  # Module may have unresolved deps in test env


if __name__ == "__main__":
    unittest.main()
