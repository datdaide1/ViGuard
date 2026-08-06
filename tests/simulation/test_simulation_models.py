"""Unit tests for Simulation Control data models (SIM-01)."""

from __future__ import annotations

import unittest

from vivi_agent.simulation.models import (
    SimulationControl,
    SimulationControlField,
    SimulationPresetId,
    SimulationResult,
)


class TestSimulationPresetId(unittest.TestCase):
    """Verify SimulationPresetId enum coverage."""

    def test_all_five_presets_defined(self) -> None:
        expected = {"parked", "driving", "highway_hda", "charging", "camp"}
        actual = {p.value for p in SimulationPresetId}
        self.assertEqual(actual, expected)

    def test_string_conversion(self) -> None:
        self.assertEqual(SimulationPresetId("parked"), SimulationPresetId.PARKED)
        self.assertEqual(SimulationPresetId("highway_hda"), SimulationPresetId.HIGHWAY_HDA)

    def test_invalid_preset_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            SimulationPresetId("nonexistent")


class TestSimulationControlField(unittest.TestCase):
    """Verify SimulationControlField enum coverage."""

    def test_all_seven_fields_defined(self) -> None:
        expected = {
            "power", "gear", "speed", "rain",
            "ambient_light", "obstacle", "driver_attention",
        }
        actual = {f.value for f in SimulationControlField}
        self.assertEqual(actual, expected)


class TestSimulationControl(unittest.TestCase):
    """Validate SimulationControl construction and field-level validation."""

    def test_valid_power_control(self) -> None:
        ctrl = SimulationControl(field=SimulationControlField.POWER, value=True)
        self.assertIs(ctrl.value, True)

    def test_invalid_power_control_non_bool(self) -> None:
        with self.assertRaises(ValueError):
            SimulationControl(field=SimulationControlField.POWER, value="on")

    def test_valid_gear_control(self) -> None:
        for gear in ("P", "R", "N", "D"):
            ctrl = SimulationControl(field=SimulationControlField.GEAR, value=gear)
            self.assertEqual(ctrl.value, gear)

    def test_invalid_gear_control(self) -> None:
        with self.assertRaises(ValueError):
            SimulationControl(field=SimulationControlField.GEAR, value="X")

    def test_valid_speed_control(self) -> None:
        ctrl = SimulationControl(field=SimulationControlField.SPEED, value=60.0)
        self.assertEqual(ctrl.value, 60.0)

    def test_speed_zero_valid(self) -> None:
        ctrl = SimulationControl(field=SimulationControlField.SPEED, value=0)
        self.assertEqual(ctrl.value, 0)

    def test_negative_speed_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SimulationControl(field=SimulationControlField.SPEED, value=-10.0)

    def test_speed_bool_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SimulationControl(field=SimulationControlField.SPEED, value=True)

    def test_valid_rain_control(self) -> None:
        ctrl = SimulationControl(field=SimulationControlField.RAIN, value=True)
        self.assertIs(ctrl.value, True)

    def test_invalid_rain_control(self) -> None:
        with self.assertRaises(ValueError):
            SimulationControl(field=SimulationControlField.RAIN, value=1)

    def test_valid_ambient_light_control(self) -> None:
        for light in ("day", "night"):
            ctrl = SimulationControl(field=SimulationControlField.AMBIENT_LIGHT, value=light)
            self.assertEqual(ctrl.value, light)

    def test_invalid_ambient_light_control(self) -> None:
        with self.assertRaises(ValueError):
            SimulationControl(field=SimulationControlField.AMBIENT_LIGHT, value="dusk")

    def test_valid_obstacle_control(self) -> None:
        ctrl = SimulationControl(field=SimulationControlField.OBSTACLE, value=True)
        self.assertIs(ctrl.value, True)

    def test_invalid_obstacle_control(self) -> None:
        with self.assertRaises(ValueError):
            SimulationControl(field=SimulationControlField.OBSTACLE, value="yes")

    def test_valid_driver_attention_control(self) -> None:
        ctrl = SimulationControl(
            field=SimulationControlField.DRIVER_ATTENTION,
            value={"hand_on_wheel": False, "driver_present": True},
        )
        self.assertEqual(ctrl.value["hand_on_wheel"], False)

    def test_driver_attention_missing_key(self) -> None:
        with self.assertRaises(ValueError):
            SimulationControl(
                field=SimulationControlField.DRIVER_ATTENTION,
                value={"driver_present": True},
            )

    def test_driver_attention_non_dict(self) -> None:
        with self.assertRaises(ValueError):
            SimulationControl(
                field=SimulationControlField.DRIVER_ATTENTION,
                value=True,
            )

    def test_driver_attention_hand_on_wheel_non_bool(self) -> None:
        with self.assertRaises(ValueError):
            SimulationControl(
                field=SimulationControlField.DRIVER_ATTENTION,
                value={"hand_on_wheel": 1},
            )

    def test_driver_attention_driver_present_non_bool(self) -> None:
        with self.assertRaises(ValueError):
            SimulationControl(
                field=SimulationControlField.DRIVER_ATTENTION,
                value={"hand_on_wheel": True, "driver_present": "yes"},
            )

    def test_invalid_field_type_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SimulationControl(field="power", value=True)

    def test_frozen_dataclass(self) -> None:
        ctrl = SimulationControl(field=SimulationControlField.POWER, value=True)
        with self.assertRaises(AttributeError):
            ctrl.value = False  # type: ignore[misc]


class TestSimulationResult(unittest.TestCase):
    """Verify SimulationResult construction."""

    def test_success_result(self) -> None:
        result = SimulationResult(
            success=True,
            state_version=5,
            event_id="evt-123",
            monitor_results=({"action_id": "a1", "outcome": "ALLOW"},),
        )
        self.assertTrue(result.success)
        self.assertEqual(result.state_version, 5)
        self.assertEqual(result.event_id, "evt-123")
        self.assertEqual(len(result.monitor_results), 1)
        self.assertIsNone(result.error)

    def test_failure_result(self) -> None:
        result = SimulationResult(
            success=False,
            state_version=3,
            error="Invariant violation",
        )
        self.assertFalse(result.success)
        self.assertIsNone(result.event_id)
        self.assertEqual(result.error, "Invariant violation")
        self.assertEqual(result.monitor_results, ())

    def test_frozen_dataclass(self) -> None:
        result = SimulationResult(success=True, state_version=1)
        with self.assertRaises(AttributeError):
            result.success = False  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
