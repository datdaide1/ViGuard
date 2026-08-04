"""Open Door Actuator Handler for vehicle execution boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from vivi_agent.vehicle.state.events import ActorKind
from vivi_agent.vehicle.state.machine import VehicleStateMachine
from vivi_agent.vehicle.state.model import DoorPosition, LockState, REQUIRED_DOOR_IDS, VehicleState
from .errors import InvalidDoorTargetError

DOOR_ALIAS_MAP: dict[str, str] = {
    "driver_door": "driver_door",
    "driver": "driver_door",
    "front_passenger_door": "front_passenger_door",
    "front_passenger": "front_passenger_door",
    "passenger_door": "front_passenger_door",
    "rear_left_door": "rear_left_door",
    "rear_left": "rear_left_door",
    "rear_right_door": "rear_right_door",
    "rear_right": "rear_right_door",
}


class OpenDoorHandler:
    """Actuator handler for opening vehicle doors.

    Performs parameter validation and applies atomic state transitions to the
    underlying :class:`VehicleStateMachine`.
    """

    def __init__(
        self,
        state_machine: VehicleStateMachine,
        *,
        actor_id: str = "open_door_handler",
    ) -> None:
        self._state_machine = state_machine
        self._actor_id = actor_id

    @property
    def state_machine(self) -> VehicleStateMachine:
        return self._state_machine

    def resolve_door_target(self, parameters: Mapping[str, Any] | None) -> str:
        """Extract and validate canonical door ID from proposal parameters."""
        if not parameters or not isinstance(parameters, Mapping):
            raise InvalidDoorTargetError("Proposal missing valid parameters dictionary")

        door_raw = (
            parameters.get("door")
            or parameters.get("door_id")
            or parameters.get("target_door")
            or parameters.get("target")
        )
        if not door_raw or not isinstance(door_raw, str):
            raise InvalidDoorTargetError("Door target parameter is missing or empty")

        door_key = door_raw.strip().lower()
        canonical_id = DOOR_ALIAS_MAP.get(door_key)
        if canonical_id is None or canonical_id not in REQUIRED_DOOR_IDS:
            raise InvalidDoorTargetError(
                f"Unsupported or invalid door target {door_raw!r}. Must be one of: {sorted(REQUIRED_DOOR_IDS)}"
            )

        return canonical_id

    def __call__(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        """Execute open door action for authorized proposal."""
        parameters = proposal.get("parameters") or proposal.get("arguments")
        if not isinstance(parameters, Mapping):
            # Fallback to checking top level if parameters/arguments keys are missing
            parameters = proposal

        door_id = self.resolve_door_target(parameters)

        correlation_id = str(
            proposal.get("proposal_id") or proposal.get("correlation_id") or "open_door_exec"
        )

        def patch_fn(state: VehicleState) -> VehicleState:
            new_doors = []
            for door in state.access.doors:
                if door.door_id == door_id:
                    new_doors.append(
                        replace(
                            door,
                            position=DoorPosition.OPEN,
                            lock=LockState.UNLOCKED,
                        )
                    )
                else:
                    new_doors.append(door)
            new_access = replace(state.access, doors=tuple(new_doors))
            return replace(state, access=new_access)

        event = self._state_machine.apply(
            patch_fn,
            actor_kind=ActorKind.AGENT,
            actor_id=self._actor_id,
            correlation_id=correlation_id,
        )


        return {
            "state_version": event.next_version,
            "facts": {
                "target_door": door_id,
                "position": DoorPosition.OPEN.value,
                "lock": LockState.UNLOCKED.value,
            },
            "message": f"Successfully opened door {door_id!r}",
        }


def make_open_door_handler(
    state_machine: VehicleStateMachine,
    *,
    actor_id: str = "open_door_handler",
) -> OpenDoorHandler:
    """Helper factory to create an :class:`OpenDoorHandler`."""
    return OpenDoorHandler(state_machine, actor_id=actor_id)
