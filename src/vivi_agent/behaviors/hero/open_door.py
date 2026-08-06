"""HERO-01 — Reference `open_door` behavior implementation.

Provides state-aware action guards, fake-state attack defense, complete behavior
facts/events formatting, recovery metadata generation, and deterministic reset.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from vivi_agent.vehicle.execution.errors import InvalidDoorTargetError
from vivi_agent.vehicle.execution.open_door import DOOR_ALIAS_MAP
from vivi_agent.vehicle.state.events import ActorKind, StateChangedEvent
from vivi_agent.vehicle.state.machine import VehicleStateMachine
from vivi_agent.vehicle.state.model import (
    DoorPosition,
    DoorState,
    Gear,
    LockState,
    REQUIRED_DOOR_IDS,
    VehicleState,
)


@dataclass(frozen=True)
class OpenDoorStateGuardResult:
    """Evaluation result for open_door state guard."""

    is_safe: bool
    reason_code: str
    message: str
    door_id: str
    current_speed_kph: float
    current_gear: str
    current_door_position: str
    current_door_lock: str
    already_open: bool = False


@dataclass(frozen=True)
class FakeStateCheckResult:
    """Result of validating prompt text state claims against telemetry state."""

    prompt_claimed_stopped: bool
    actual_stopped: bool
    is_fake_state_attack: bool
    detail: str


class OpenDoorHeroBehavior:
    """Reference implementation for HERO-01 open_door behavior."""

    INTENT_ID: str = "open_door"

    @staticmethod
    def resolve_door_id(door_raw: str | None) -> str:
        """Resolve and validate canonical door ID from alias or input string.

        Fails closed (matching ``OpenDoorHandler.resolve_door_target``) instead
        of silently defaulting to a door the caller never asked for.
        """
        if not door_raw or not isinstance(door_raw, str):
            raise InvalidDoorTargetError("Door target parameter is missing or empty")
        key = door_raw.strip().lower()
        canonical = DOOR_ALIAS_MAP.get(key)
        if canonical is None or canonical not in REQUIRED_DOOR_IDS:
            raise InvalidDoorTargetError(
                f"Unsupported or invalid door target {door_raw!r}. Must be one of: {sorted(REQUIRED_DOOR_IDS)}"
            )
        return canonical

    @classmethod
    def evaluate_state_guard(
        cls,
        state: VehicleState,
        door_target: str = "driver_door",
    ) -> OpenDoorStateGuardResult:
        """Evaluate ground-truth VehicleState for open_door safety.

        Rules:
        - Vehicle must be stationary (speed_kph == 0.0)
        - Gear must be PARK (Gear.PARK)
        - Door target must exist
        """
        canonical_door = cls.resolve_door_id(door_target)
        door_state = cls._find_door(state, canonical_door)

        pos_val = door_state.position.value if door_state else DoorPosition.CLOSED.value
        lock_val = door_state.lock.value if door_state else LockState.LOCKED.value
        speed = state.motion.speed_kph
        gear_val = state.transmission.gear.value

        # Unsafe condition 1: Vehicle is in motion
        if speed > 0.0:
            return OpenDoorStateGuardResult(
                is_safe=False,
                reason_code="BLOCK_VEHICLE_MOVING",
                message=f"Cannot open door {canonical_door!r} while vehicle is moving ({speed:.1f} km/h).",
                door_id=canonical_door,
                current_speed_kph=speed,
                current_gear=gear_val,
                current_door_position=pos_val,
                current_door_lock=lock_val,
            )

        # Unsafe condition 2: Vehicle gear is not in PARK
        if state.transmission.gear != Gear.PARK:
            return OpenDoorStateGuardResult(
                is_safe=False,
                reason_code="BLOCK_GEAR_NOT_PARK",
                message=f"Cannot open door {canonical_door!r} while gear is {gear_val!r}. Vehicle must be in PARK.",
                door_id=canonical_door,
                current_speed_kph=speed,
                current_gear=gear_val,
                current_door_position=pos_val,
                current_door_lock=lock_val,
            )

        # Check if door is already open
        already_open = (door_state.position == DoorPosition.OPEN) if door_state else False

        return OpenDoorStateGuardResult(
            is_safe=True,
            reason_code="PERMITTED",
            message=f"Safe to open door {canonical_door!r}.",
            door_id=canonical_door,
            current_speed_kph=speed,
            current_gear=gear_val,
            current_door_position=pos_val,
            current_door_lock=lock_val,
            already_open=already_open,
        )

    @classmethod
    def detect_fake_state_attack(
        cls,
        user_prompt: str,
        state: VehicleState,
    ) -> FakeStateCheckResult:
        """Detect whether user/model prompt text falsely claims vehicle is stopped/safe.

        Agent MUST NOT trust prompt state assertions and MUST rely on ground-truth
        `VehicleState`.
        """
        prompt_lower = user_prompt.lower()
        fake_keywords = [
            "đã dừng",
            "đang dừng",
            "đang đỗ",
            "đang đỗ rồi",
            "xe đang đứng yên",
            "stopped",
            "parked",
            "already stopped",
        ]
        prompt_claimed_stopped = any(
            kw in prompt_lower and not cls._is_negated(prompt_lower, prompt_lower.index(kw))
            for kw in fake_keywords
        )
        actual_stopped = (state.motion.speed_kph == 0.0) and (state.transmission.gear == Gear.PARK)

        is_fake_attack = prompt_claimed_stopped and not actual_stopped

        detail = (
            f"Fake-state attack detected: Prompt claims vehicle is stopped/parked, "
            f"but actual telemetry is speed={state.motion.speed_kph} km/h, gear={state.transmission.gear.value}."
            if is_fake_attack
            else "No fake-state attack detected or state matches prompt."
        )

        return FakeStateCheckResult(
            prompt_claimed_stopped=prompt_claimed_stopped,
            actual_stopped=actual_stopped,
            is_fake_state_attack=is_fake_attack,
            detail=detail,
        )

    @classmethod
    def build_behavior_facts(
        cls,
        state: VehicleState,
        door_target: str,
        decision_outcome: str,
        execution_result: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build canonical behavior facts dict for telemetry & UI auditing."""
        canonical_door = cls.resolve_door_id(door_target)
        door_state = cls._find_door(state, canonical_door)

        facts: dict[str, Any] = {
            "intent": cls.INTENT_ID,
            "target_door": canonical_door,
            "vehicle_speed_kph": state.motion.speed_kph,
            "gear": state.transmission.gear.value,
            "epb_engaged": state.transmission.epb_engaged,
            "decision_outcome": decision_outcome,
            "state_version": state.state_version,
            "door_position_before": door_state.position.value if door_state else "UNKNOWN",
            "door_lock_before": door_state.lock.value if door_state else "UNKNOWN",
        }

        if execution_result:
            facts["execution"] = dict(execution_result)
            if "facts" in execution_result:
                facts["door_position_after"] = execution_result["facts"].get("position")
                facts["door_lock_after"] = execution_result["facts"].get("lock")

        return facts

    @classmethod
    def build_recovery_metadata(
        cls,
        guard_result: OpenDoorStateGuardResult,
    ) -> dict[str, Any]:
        """Generate structured recovery guidance when open_door is blocked."""
        if guard_result.is_safe:
            return {}

        hints = []
        actions = []
        if guard_result.current_speed_kph > 0.0:
            hints.append(f"Tốc độ xe hiện tại là {guard_result.current_speed_kph:.1f} km/h (yêu cầu 0.0 km/h).")
            actions.append("Dừng hẳn xe trước khi thao tác.")

        if guard_result.current_gear != Gear.PARK.value:
            hints.append(f"Cần số hiện tại là {guard_result.current_gear!r} (yêu cầu PARK).")
            actions.append("Đưa cần số về P.")

        return {
            "intent": cls.INTENT_ID,
            "target_door": guard_result.door_id,
            "reason_code": guard_result.reason_code,
            "recovery_hint": " ".join(hints),
            "suggested_action": " -> ".join(actions) if actions else "Dừng xe và về P.",
            "safety_guard": "STRICT_GROUND_TRUTH",
        }

    @staticmethod
    def _is_negated(prompt_lower: str, match_index: int, window: int = 20) -> bool:
        """Check for a negation marker directly preceding a matched keyword.

        Prevents substrings like "not stopped" or "chưa dừng" from being
        counted as a claim that the vehicle is stopped/parked.
        """
        preceding = prompt_lower[max(0, match_index - window):match_index]
        negation_markers = ("not ", "n't ", "chưa ", "không ", "chẳng ")
        return any(marker in preceding for marker in negation_markers)

    @staticmethod
    def _find_door(state: VehicleState, door_id: str) -> DoorState | None:
        for door in state.access.doors:
            if door.door_id == door_id:
                return door
        return None


def reset_open_door_state(
    state_machine: VehicleStateMachine,
    *,
    actor_id: str = "open_door_reset",
) -> StateChangedEvent:
    """Deterministically reset all vehicle doors to closed and locked baseline.

    Prevents state leakage across evaluation turns and test runs.
    """
    def patch_fn(state: VehicleState) -> VehicleState:
        new_doors = tuple(
            replace(door, position=DoorPosition.CLOSED, lock=LockState.LOCKED)
            for door in state.access.doors
        )
        new_access = replace(state.access, doors=new_doors)
        return replace(state, access=new_access)

    return state_machine.apply(
        patch_fn,
        actor_kind=ActorKind.SYSTEM,
        actor_id=actor_id,
        correlation_id="open_door_deterministic_reset",
    )
