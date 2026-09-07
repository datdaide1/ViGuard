"""Unit and integration tests for Open Door Actuator Handler (EXEC-02)."""

from __future__ import annotations

from typing import Any

import pytest

from vehicle_agent.contracts.guardrail.v1.contract import proposal_digest
from vehicle_agent.vehicle.execution import (
    InvalidDoorTargetError,
    OpenDoorHandler,
    VehicleToolGateway,
    make_open_door_handler,
)
from vehicle_agent.vehicle.execution.open_door import DOOR_ALIAS_MAP
from vehicle_agent.vehicle.state import (
    DoorPosition,
    LockState,
    VehicleStateMachine,
)
from vehicle_agent.vehicle.state.model import REQUIRED_DOOR_IDS


def make_proposal(
    proposal_id: str = "prop-door-1",
    session_id: str = "sess-door-1",
    source_turn_id: str = "turn-door-1",
    tool: str = "open_door",
    door: str = "driver_door",
) -> dict[str, Any]:
    return {
        "contract_version": "1.0.0",
        "proposal_id": proposal_id,
        "session_id": session_id,
        "source_turn_id": source_turn_id,
        "tool": tool,
        "arguments": {"door": door},
        "model_provider": "openai",
        "model_id": "gpt-4o",
    }


def make_decision(
    proposal: dict[str, Any],
    permit_id: str = "permit-door-1",
    intent: str = "open_door",
    state_version: int = 0,
) -> dict[str, Any]:
    digest = proposal_digest(proposal)
    permit = {
        "permit_id": permit_id,
        "proposal_digest": digest,
        "intent": intent,
        "rule_id": "R_OPEN_DOOR",
        "state_version": state_version,
        "policy_checksum": "sha256:" + "0" * 64,
        "issued_at": "2020-01-01T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
        "single_use": True,
    }
    return {
        "contract_version": "1.0.0",
        "kind": "decision",
        "request_id": "req-door-1",
        "proposal_id": proposal["proposal_id"],
        "intent": intent,
        "outcome": "ALLOW",
        "rule_id": "R_OPEN_DOOR",
        "state_version": state_version,
        "policy_checksum": "sha256:" + "0" * 64,
        "reason_code": "SAFE_OPERATION",
        "relevant_state": {},
        "permit": permit,
    }


def test_open_door_handler_directly() -> None:
    state_machine = VehicleStateMachine()
    handler = OpenDoorHandler(state_machine)

    initial_snapshot = state_machine.snapshot()
    driver_door_init = next(d for d in initial_snapshot.access.doors if d.door_id == "driver_door")
    assert driver_door_init.position == DoorPosition.CLOSED
    assert driver_door_init.lock == LockState.LOCKED

    proposal = make_proposal(door="driver_door")
    output = handler(proposal)

    assert output["state_version"] == 1
    assert output["facts"]["target_door"] == "driver_door"
    assert output["facts"]["position"] == DoorPosition.OPEN.value
    assert output["facts"]["lock"] == LockState.UNLOCKED.value

    new_snapshot = state_machine.snapshot()
    assert new_snapshot.state_version == 1
    driver_door_after = next(d for d in new_snapshot.access.doors if d.door_id == "driver_door")
    assert driver_door_after.position == DoorPosition.OPEN
    assert driver_door_after.lock == LockState.UNLOCKED


def test_open_door_via_gateway_success() -> None:
    state_machine = VehicleStateMachine()
    gateway = VehicleToolGateway()
    handler = make_open_door_handler(state_machine)
    gateway.registry.register("open_door", handler)

    proposal = make_proposal(door="front_passenger_door")
    decision = make_decision(proposal, state_version=0)

    result = gateway.execute(proposal, decision)

    assert result.success is True
    assert result.state_version == 1
    assert result.facts["target_door"] == "front_passenger_door"
    assert "Successfully opened door" in result.message

    snapshot = state_machine.snapshot()
    door = next(d for d in snapshot.access.doors if d.door_id == "front_passenger_door")
    assert door.position == DoorPosition.OPEN
    assert door.lock == LockState.UNLOCKED

    events = state_machine.event_store.list_all()
    assert len(events) == 1
    assert events[0].next_version == 1


@pytest.mark.parametrize(
    "door_input, canonical_id",
    [
        ("driver_door", "driver_door"),
        ("driver", "driver_door"),
        ("front_passenger_door", "front_passenger_door"),
        ("front_passenger", "front_passenger_door"),
        ("passenger_door", "front_passenger_door"),
        ("rear_left_door", "rear_left_door"),
        ("rear_left", "rear_left_door"),
        ("rear_right_door", "rear_right_door"),
        ("rear_right", "rear_right_door"),
        ("Driver_Door", "driver_door"),
        ("  driver  ", "driver_door"),
    ],
)

def test_open_door_all_valid_door_inputs(door_input: str, canonical_id: str) -> None:
    state_machine = VehicleStateMachine()
    handler = OpenDoorHandler(state_machine)

    proposal = make_proposal(door=door_input)
    output = handler(proposal)

    assert output["facts"]["target_door"] == canonical_id
    snapshot = state_machine.snapshot()
    door = next(d for d in snapshot.access.doors if d.door_id == canonical_id)
    assert door.position == DoorPosition.OPEN
    assert door.lock == LockState.UNLOCKED


def test_open_door_invalid_target_rejects_and_no_mutation() -> None:
    state_machine = VehicleStateMachine()
    gateway = VehicleToolGateway()
    handler = make_open_door_handler(state_machine)
    gateway.registry.register("open_door", handler)

    proposal = make_proposal(door="trunk_door")
    decision = make_decision(proposal)

    result = gateway.execute(proposal, decision)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "INVALID_DOOR_TARGET"

    snapshot = state_machine.snapshot()
    assert snapshot.state_version == 0
    assert len(state_machine.event_store.list_all()) == 0


def test_open_door_missing_door_parameter_fails() -> None:
    state_machine = VehicleStateMachine()
    handler = OpenDoorHandler(state_machine)

    proposal: dict[str, Any] = {
        "contract_version": "1.0.0",
        "proposal_id": "prop-bad-1",
        "tool": "open_door",
        "arguments": {},
    }

    with pytest.raises(InvalidDoorTargetError) as exc_info:
        handler(proposal)

    assert exc_info.value.code == "INVALID_DOOR_TARGET"
    assert state_machine.snapshot().state_version == 0


def test_open_door_idempotent() -> None:
    state_machine = VehicleStateMachine()
    handler = OpenDoorHandler(state_machine)

    proposal = make_proposal(door="driver_door")
    out1 = handler(proposal)
    assert out1["state_version"] == 1

    # Second open door call on same door
    proposal2 = make_proposal(proposal_id="prop-door-2", door="driver_door")
    out2 = handler(proposal2)
    assert out2["state_version"] == 2

    snapshot = state_machine.snapshot()
    driver_door = next(d for d in snapshot.access.doors if d.door_id == "driver_door")
    assert driver_door.position == DoorPosition.OPEN
    assert driver_door.lock == LockState.UNLOCKED


def test_open_door_replay_permit_fails_closed() -> None:
    state_machine = VehicleStateMachine()
    gateway = VehicleToolGateway()
    handler = make_open_door_handler(state_machine)
    gateway.registry.register("open_door", handler)

    proposal = make_proposal(door="driver_door")
    decision = make_decision(proposal)

    res1 = gateway.execute(proposal, decision)
    assert res1.success is True

    # Replay same decision & permit
    res2 = gateway.execute(proposal, decision)
    assert res2.success is False
    assert res2.error is not None
    assert res2.error.code == "PERMIT_REPLAYED"

    # Only 1 state version increment happened
    assert state_machine.snapshot().state_version == 1


def test_door_alias_map_covers_exactly_the_canonical_door_ids() -> None:
    """DOOR_ALIAS_MAP must stay derived from/validated against REQUIRED_DOOR_IDS.

    Guards against the alias table silently drifting from the canonical
    vehicle state schema (Sourcery review feedback on PR #16).
    """
    assert set(DOOR_ALIAS_MAP.values()) == set(REQUIRED_DOOR_IDS)
    # Every canonical door ID is a valid alias for itself.
    for door_id in REQUIRED_DOOR_IDS:
        assert DOOR_ALIAS_MAP[door_id] == door_id


def test_door_alias_map_resolves_short_aliases_to_canonical_ids() -> None:
    handler = make_open_door_handler(VehicleStateMachine())

    for alias, canonical_id in DOOR_ALIAS_MAP.items():
        assert handler.resolve_door_target({"door": alias}) == canonical_id
