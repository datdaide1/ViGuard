from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from types import MappingProxyType

from src.vivi_agent.vehicle.state import (
    DEFAULT_VEHICLE_STATE,
    PIP_FIELD_NAMES,
    POWER_DEPENDENT_ADAS_INTENTS,
    PRESETS,
    REQUIRED_DOOR_IDS,
    AccState,
    AccessState,
    ActiveAction,
    AdasState,
    DoorPosition,
    DoorState,
    Gear,
    LockState,
    MotionPhase,
    MotionState,
    PowerState,
    StateSource,
    TransmissionState,
    VehicleState,
    VehicleStateValidationError,
    get_preset,
    pip_provenance,
)


class VehicleStateTests(unittest.TestCase):
    def state(self, **changes: object) -> VehicleState:
        observed_at = datetime(2026, 8, 4, tzinfo=timezone.utc)
        base = {
            "state_version": 1,
            "timestamp": observed_at,
            "pip_field_provenance": pip_provenance(StateSource.SIMULATOR, observed_at),
            "power": PowerState(powered_on=True),
        }
        base.update(changes)
        return VehicleState(**base)

    def test_default_state_is_valid_immutable_and_deterministic(self) -> None:
        self.assertEqual(DEFAULT_VEHICLE_STATE.state_version, 0)
        self.assertEqual(DEFAULT_VEHICLE_STATE.transmission.gear, Gear.PARK)
        self.assertEqual(DEFAULT_VEHICLE_STATE.motion.phase, MotionPhase.STOPPED)
        with self.assertRaises(FrozenInstanceError):
            DEFAULT_VEHICLE_STATE.state_version = 1  # type: ignore[misc]

    def test_guardrail_projection_has_complete_closed_pip_fields(self) -> None:
        snapshot = self.state().to_guardrail_snapshot()
        self.assertEqual(
            set(snapshot),
            PIP_FIELD_NAMES | {"schema_version", "state_version", "timestamp"},
        )
        self.assertEqual(snapshot["timestamp"], "2026-08-04T00:00:00Z")
        self.assertEqual(snapshot["door_lock_state"], "Locked")

    def test_open_door_cannot_be_locked_and_derives_aggregate_unlock(self) -> None:
        with self.assertRaises(VehicleStateValidationError) as raised:
            DoorState("driver_door", DoorPosition.OPEN, LockState.LOCKED)
        self.assertEqual(raised.exception.code, "OPEN_DOOR_LOCKED")

        access = AccessState(
            doors=tuple(
                DoorState(
                    door_id,
                    DoorPosition.OPEN if door_id == "driver_door" else DoorPosition.CLOSED,
                    LockState.UNLOCKED if door_id == "driver_door" else LockState.LOCKED,
                )
                for door_id in sorted(REQUIRED_DOOR_IDS)
            )
        )
        self.assertEqual(access.door_lock_state, LockState.UNLOCKED)

    def test_incomplete_or_unknown_door_coverage_is_rejected(self) -> None:
        for doors in (
            (DoorState("driver_door"),),
            tuple(DoorState(door_id) for door_id in sorted(REQUIRED_DOOR_IDS))
            + (DoorState("cargo_door"),),
        ):
            with self.subTest(doors=doors):
                with self.assertRaises(VehicleStateValidationError) as raised:
                    AccessState(doors=doors)
                self.assertEqual(raised.exception.code, "INVALID_DOOR_COVERAGE")

    def test_park_requires_zero_speed(self) -> None:
        with self.assertRaises(VehicleStateValidationError) as raised:
            self.state(motion=MotionState(1, MotionPhase.MOVING))
        self.assertEqual(raised.exception.code, "PARK_REQUIRES_STOPPED")

    def test_motion_phase_must_match_speed(self) -> None:
        for speed, phase in ((1, MotionPhase.STOPPED), (0, MotionPhase.MOVING)):
            with self.subTest(speed=speed, phase=phase):
                with self.assertRaises(VehicleStateValidationError) as raised:
                    MotionState(speed, phase)
                self.assertEqual(raised.exception.code, "MOTION_PHASE_MISMATCH")

    def test_powered_off_vehicle_rejects_running_adas_or_action(self) -> None:
        with self.assertRaises(VehicleStateValidationError) as adas_error:
            replace(
                DEFAULT_VEHICLE_STATE,
                adas=AdasState(acc_state=AccState.ACTIVE),
            )
        self.assertEqual(adas_error.exception.code, "POWER_OFF_ACTIVE_ADAS")

        with self.assertRaises(VehicleStateValidationError) as action_error:
            replace(
                DEFAULT_VEHICLE_STATE,
                active_actions=(ActiveAction("a-1", "activate_autopark"),),
            )
        self.assertEqual(action_error.exception.code, "POWER_OFF_ACTIVE_ADAS")

        self.assertEqual(
            POWER_DEPENDENT_ADAS_INTENTS,
            frozenset({"activate_aac", "activate_hda", "activate_autopark"}),
        )

    def test_invalid_numeric_values_are_rejected(self) -> None:
        for value in (-1, 101, float("nan"), float("inf"), True):
            with self.subTest(value=value):
                with self.assertRaises(VehicleStateValidationError):
                    PowerState(battery_pct=value)

    def test_powered_on_vehicle_may_be_charging(self) -> None:
        power = PowerState(powered_on=True, charging=True)
        self.assertTrue(power.powered_on)
        self.assertTrue(power.charging)

    def test_hda_requires_active_acc_and_tcs_requires_esc(self) -> None:
        with self.assertRaises(VehicleStateValidationError) as hda_error:
            AdasState(hda_active=True)
        self.assertEqual(hda_error.exception.code, "HDA_REQUIRES_ACTIVE_ACC")

        with self.assertRaises(VehicleStateValidationError) as tcs_error:
            AdasState(tcs_active=True, esc_active=False)
        self.assertEqual(tcs_error.exception.code, "TCS_REQUIRES_ESC")

    def test_presets_materialize_with_caller_owned_metadata(self) -> None:
        observed_at = datetime(2026, 8, 4, 12, 30, tzinfo=timezone.utc)
        moving = get_preset("moving_drive", state_version=7, timestamp=observed_at)
        self.assertEqual(moving.state_version, 7)
        self.assertEqual(moving.timestamp, observed_at)
        self.assertEqual(moving.transmission, TransmissionState(Gear.DRIVE, False))
        self.assertEqual(moving.motion, MotionState(30.0, MotionPhase.MOVING))

        charging = get_preset("charging", state_version=8, timestamp=observed_at)
        self.assertTrue(charging.power.powered_on)
        self.assertTrue(charging.power.charging)
        self.assertTrue(
            all(
                item.source is StateSource.PRESET
                for item in charging.pip_field_provenance
            )
        )

    def test_preset_index_is_immutable_and_derived_from_preset_ids(self) -> None:
        self.assertIsInstance(PRESETS, MappingProxyType)
        self.assertEqual(set(PRESETS), {preset.preset_id for preset in PRESETS.values()})
        with self.assertRaises(TypeError):
            PRESETS["drift"] = PRESETS["parked_ready"]  # type: ignore[index]

    def test_timestamp_must_be_timezone_aware(self) -> None:
        with self.assertRaises(VehicleStateValidationError) as raised:
            VehicleState(
                state_version=0,
                timestamp=datetime(2026, 8, 4),
                pip_field_provenance=pip_provenance(
                    StateSource.SIMULATOR, datetime(2026, 8, 4, tzinfo=timezone.utc)
                ),
            )
        self.assertEqual(raised.exception.code, "NAIVE_TIMESTAMP")

    def test_state_version_must_be_a_non_negative_integer(self) -> None:
        for version in (-1, 1.5, True):
            with self.subTest(version=version):
                with self.assertRaises(VehicleStateValidationError) as raised:
                    VehicleState(
                        state_version=version,  # type: ignore[arg-type]
                        timestamp=datetime(2026, 8, 4, tzinfo=timezone.utc),
                        pip_field_provenance=pip_provenance(
                            StateSource.SIMULATOR,
                            datetime(2026, 8, 4, tzinfo=timezone.utc),
                        ),
                    )
                self.assertEqual(raised.exception.code, "INVALID_STATE_VERSION")

    def test_runtime_types_fail_closed_instead_of_coercing(self) -> None:
        with self.assertRaises(VehicleStateValidationError) as enum_error:
            TransmissionState(gear="P")  # type: ignore[arg-type]
        self.assertEqual(enum_error.exception.code, "INVALID_ENUM_FIELD")

        with self.assertRaises(VehicleStateValidationError) as bool_error:
            PowerState(powered_on=1)  # type: ignore[arg-type]
        self.assertEqual(bool_error.exception.code, "INVALID_BOOLEAN_FIELD")

    def test_unavailable_pip_field_fails_guardrail_export(self) -> None:
        observed_at = datetime(2026, 8, 4, tzinfo=timezone.utc)
        state = self.state(
            pip_field_provenance=pip_provenance(
                StateSource.SIMULATOR,
                observed_at,
                unavailable_fields=frozenset({"battery_pct"}),
            )
        )
        with self.assertRaises(VehicleStateValidationError) as raised:
            state.to_guardrail_snapshot()
        self.assertEqual(raised.exception.code, "INCOMPLETE_GUARDRAIL_SNAPSHOT")

    def test_provenance_requires_every_current_policy_field_once(self) -> None:
        observed_at = datetime(2026, 8, 4, tzinfo=timezone.utc)
        incomplete = pip_provenance(StateSource.SIMULATOR, observed_at)[:-1]
        with self.assertRaises(VehicleStateValidationError) as raised:
            VehicleState(
                state_version=1,
                timestamp=observed_at,
                pip_field_provenance=incomplete,
            )
        self.assertEqual(raised.exception.code, "INCOMPLETE_PIP_PROVENANCE")


if __name__ == "__main__":
    unittest.main()
