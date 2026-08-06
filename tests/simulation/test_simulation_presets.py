"""Unit tests for Simulation preset catalog (SIM-01)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from vivi_agent.simulation.models import SimulationPresetId
from vivi_agent.simulation.presets import (
    SIMULATION_PRESETS,
    SimulationPreset,
    get_simulation_preset,
)
from vivi_agent.vehicle.state.model import (
    AccState,
    Gear,
    MotionPhase,
    VehicleState,
)


class TestSimulationPresetsCoverage(unittest.TestCase):
    """Verify the preset catalog covers all required presets."""

    def test_all_five_presets_in_catalog(self) -> None:
        expected_ids = {p for p in SimulationPresetId}
        actual_ids = set(SIMULATION_PRESETS.keys())
        self.assertEqual(actual_ids, expected_ids)

    def test_preset_ids_are_unique(self) -> None:
        # MappingProxyType guarantees key uniqueness, but let's be explicit.
        self.assertEqual(len(SIMULATION_PRESETS), len(SimulationPresetId))

    def test_all_presets_are_simulation_preset_type(self) -> None:
        for preset in SIMULATION_PRESETS.values():
            self.assertIsInstance(preset, SimulationPreset)

    def test_all_presets_have_valid_vehicle_state(self) -> None:
        """Every preset's VehicleState must pass invariant validation."""
        for preset_id, preset in SIMULATION_PRESETS.items():
            with self.subTest(preset_id=preset_id.value):
                self.assertIsInstance(preset.state, VehicleState)


class TestSimulationPresetStates(unittest.TestCase):
    """Verify each preset's key state properties."""

    def test_parked_preset(self) -> None:
        preset = SIMULATION_PRESETS[SimulationPresetId.PARKED]
        state = preset.state
        self.assertFalse(state.power.powered_on)
        self.assertEqual(state.transmission.gear, Gear.PARK)
        self.assertEqual(state.motion.speed_kph, 0.0)
        self.assertTrue(state.transmission.epb_engaged)

    def test_driving_preset(self) -> None:
        preset = SIMULATION_PRESETS[SimulationPresetId.DRIVING]
        state = preset.state
        self.assertTrue(state.power.powered_on)
        self.assertEqual(state.transmission.gear, Gear.DRIVE)
        self.assertEqual(state.motion.speed_kph, 30.0)
        self.assertEqual(state.motion.phase, MotionPhase.MOVING)
        self.assertFalse(state.transmission.epb_engaged)

    def test_highway_hda_preset(self) -> None:
        preset = SIMULATION_PRESETS[SimulationPresetId.HIGHWAY_HDA]
        state = preset.state
        self.assertTrue(state.power.powered_on)
        self.assertEqual(state.transmission.gear, Gear.DRIVE)
        self.assertEqual(state.motion.speed_kph, 100.0)
        self.assertEqual(state.motion.phase, MotionPhase.MOVING)
        self.assertEqual(state.adas.acc_state, AccState.ACTIVE)
        self.assertTrue(state.adas.hda_active)
        self.assertFalse(state.transmission.epb_engaged)

    def test_charging_preset(self) -> None:
        preset = SIMULATION_PRESETS[SimulationPresetId.CHARGING]
        state = preset.state
        self.assertTrue(state.power.powered_on)
        self.assertTrue(state.power.charging)
        self.assertEqual(state.transmission.gear, Gear.PARK)

    def test_camp_preset(self) -> None:
        preset = SIMULATION_PRESETS[SimulationPresetId.CAMP]
        state = preset.state
        self.assertTrue(state.power.powered_on)
        self.assertTrue(state.modes.camp_mode_active)
        self.assertEqual(state.transmission.gear, Gear.PARK)


class TestGetSimulationPreset(unittest.TestCase):
    """Verify get_simulation_preset materialisation."""

    _TS = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_materialise_with_version_and_timestamp(self) -> None:
        state = get_simulation_preset(
            SimulationPresetId.DRIVING,
            state_version=42,
            timestamp=self._TS,
        )
        self.assertIsInstance(state, VehicleState)
        self.assertEqual(state.state_version, 42)
        self.assertEqual(state.timestamp, self._TS)

    def test_deterministic_same_seed(self) -> None:
        state_a = get_simulation_preset(
            SimulationPresetId.HIGHWAY_HDA,
            state_version=1,
            timestamp=self._TS,
            seed=12345,
        )
        state_b = get_simulation_preset(
            SimulationPresetId.HIGHWAY_HDA,
            state_version=1,
            timestamp=self._TS,
            seed=12345,
        )
        self.assertEqual(state_a, state_b)

    def test_deterministic_no_seed(self) -> None:
        state_a = get_simulation_preset(
            SimulationPresetId.CAMP,
            state_version=1,
            timestamp=self._TS,
        )
        state_b = get_simulation_preset(
            SimulationPresetId.CAMP,
            state_version=1,
            timestamp=self._TS,
        )
        self.assertEqual(state_a, state_b)

    def test_unknown_preset_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            get_simulation_preset(
                "nonexistent",  # type: ignore[arg-type]
                state_version=1,
                timestamp=self._TS,
            )

    def test_guardrail_snapshot_valid(self) -> None:
        """Every preset must produce a state that can export to Guardrail."""
        for preset_id in SimulationPresetId:
            with self.subTest(preset_id=preset_id.value):
                state = get_simulation_preset(
                    preset_id,
                    state_version=1,
                    timestamp=self._TS,
                )
                snapshot = state.to_guardrail_snapshot()
                self.assertIn("schema_version", snapshot)
                self.assertIn("speed", snapshot)
                self.assertIn("gear", snapshot)


if __name__ == "__main__":
    unittest.main()
