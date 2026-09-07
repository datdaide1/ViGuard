"""Unit tests for EXEC-03 Generic Handler Framework and Behavior Config Validation."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from vehicle_agent.contracts.guardrail.v1.contract import proposal_digest
from vehicle_agent.vehicle.execution.errors import (
    BehaviorConfigValidationError,
    BehaviorReadinessError,
    ExecutionError,
    HandlerNotFoundError,
    InvalidDoorTargetError,
)
from vehicle_agent.vehicle.execution.gateway import HandlerRegistry, VehicleToolGateway
from vehicle_agent.vehicle.execution.generic import (
    AccessActuatorHandler,
    ActiveActionHandler,
    BehaviorConfig,
    BehaviorHandlerType,
    CompoundActionHandler,
    EnumSetterHandler,
    OneShotEventHandler,
    PositionActuatorHandler,
    TimedTransitionHandler,
    ToggleHandler,
    create_generic_handler,
    register_behavior_configs,
    validate_behavior_catalog_readiness,
    validate_behavior_config,
)
from vehicle_agent.vehicle.state.machine import VehicleStateMachine
from vehicle_agent.vehicle.state.model import (
    ActiveActionPhase,
    DoorPosition,
    DriveMode,
    LockState,
)


def make_test_proposal(
    proposal_id: str = "prop-101",
    tool: str = "toggle_fog_light",
    arguments: dict | None = None,
) -> dict:
    return {
        "contract_version": "1.0.0",
        "proposal_id": proposal_id,
        "session_id": "sess-001",
        "source_turn_id": "turn-001",
        "tool": tool,
        "arguments": arguments if arguments is not None else {},
        "model_provider": "test",
        "model_id": "test-model",
    }


@pytest.fixture
def state_machine() -> VehicleStateMachine:
    return VehicleStateMachine()


@pytest.fixture
def gateway(state_machine: VehicleStateMachine) -> VehicleToolGateway:
    gtw = VehicleToolGateway()

    # Pre-register test configs
    configs = [
        BehaviorConfig(
            intent_id="toggle_fog_light",
            handler_type=BehaviorHandlerType.TOGGLE,
            target_substate="lighting",
            target_field="fog_light",
        ),
        BehaviorConfig(
            intent_id="set_drive_mode",
            handler_type=BehaviorHandlerType.ENUM_SETTER,
            target_substate="modes",
            target_field="drive_mode",
            enum_cls=DriveMode,
        ),
        BehaviorConfig(
            intent_id="open_door",
            handler_type=BehaviorHandlerType.ACCESS,
            target_substate="access",
        ),
        BehaviorConfig(
            intent_id="set_seat_position",
            handler_type=BehaviorHandlerType.POSITION,
            target_substate="cabin",
            target_field="driver_seat_position",
            value_range=(0.0, 1.0),
        ),
        BehaviorConfig(
            intent_id="activate_hud",
            handler_type=BehaviorHandlerType.TIMED,
            target_substate="cabin",
            target_field="hud_active",
            duration_seconds=300.0,
        ),
        BehaviorConfig(
            intent_id="open_notification_center",
            handler_type=BehaviorHandlerType.ONE_SHOT,
            target_substate="ui",
            target_field="notification_center_open",
            event_name="SHOW_NOTIFICATIONS",
        ),
        BehaviorConfig(
            intent_id="start_autopark",
            handler_type=BehaviorHandlerType.ACTIVE_ACTION,
            target_substate="modes",
            active_action_name="autopark_mode",
        ),
    ]

    register_behavior_configs(gtw.registry, configs, state_machine)
    return gtw


# ==============================================================================
# 1. BehaviorConfig Validation Tests
# ==============================================================================

def test_validate_behavior_config_valid() -> None:
    cfg = BehaviorConfig(
        intent_id="test_toggle",
        handler_type=BehaviorHandlerType.TOGGLE,
        target_substate="lighting",
        target_field="fog_light",
    )
    validate_behavior_config(cfg)  # Should not raise


def test_validate_behavior_config_invalid_intent_id() -> None:
    cfg = BehaviorConfig(intent_id="", handler_type=BehaviorHandlerType.TOGGLE)
    with pytest.raises(BehaviorConfigValidationError, match="intent_id must be a non-empty string"):
        validate_behavior_config(cfg)


def test_validate_behavior_config_invalid_handler_type() -> None:
    cfg = BehaviorConfig(intent_id="test", handler_type="unsupported_type")
    with pytest.raises(BehaviorConfigValidationError, match="Invalid handler_type"):
        validate_behavior_config(cfg)


def test_validate_behavior_config_missing_toggle_fields() -> None:
    cfg = BehaviorConfig(
        intent_id="test_toggle",
        handler_type=BehaviorHandlerType.TOGGLE,
        target_substate="lighting",
    )
    with pytest.raises(BehaviorConfigValidationError, match="requires target_substate and target_field"):
        validate_behavior_config(cfg)


def test_validate_behavior_config_invalid_substate() -> None:
    cfg = BehaviorConfig(
        intent_id="test_toggle",
        handler_type=BehaviorHandlerType.TOGGLE,
        target_substate="non_existent_substate",
        target_field="some_field",
    )
    with pytest.raises(BehaviorConfigValidationError, match="Invalid target_substate"):
        validate_behavior_config(cfg)


def test_validate_behavior_config_active_actions_substate_rejected() -> None:
    cfg = BehaviorConfig(
        intent_id="test_active_sub",
        handler_type=BehaviorHandlerType.TOGGLE,
        target_substate="active_actions",
        target_field="some_field",
    )
    with pytest.raises(BehaviorConfigValidationError, match="Invalid target_substate"):
        validate_behavior_config(cfg)


def test_validate_behavior_config_access_invalid_substate() -> None:
    cfg = BehaviorConfig(
        intent_id="test_access",
        handler_type=BehaviorHandlerType.ACCESS,
        target_substate="lighting",
    )
    with pytest.raises(BehaviorConfigValidationError, match="requires target_substate='access'"):
        validate_behavior_config(cfg)


def test_validate_behavior_config_invalid_enum_cls() -> None:
    cfg = BehaviorConfig(
        intent_id="test_enum",
        handler_type=BehaviorHandlerType.ENUM_SETTER,
        target_substate="modes",
        target_field="drive_mode",
        enum_cls=str,  # Not an Enum
    )
    with pytest.raises(BehaviorConfigValidationError, match="enum_cls must be a subclass of Enum"):
        validate_behavior_config(cfg)


def test_validate_behavior_config_invalid_position_range() -> None:
    cfg = BehaviorConfig(
        intent_id="test_pos",
        handler_type=BehaviorHandlerType.POSITION,
        target_substate="cabin",
        target_field="driver_seat_position",
        value_range=(0.8, 0.2),  # min > max
    )
    with pytest.raises(BehaviorConfigValidationError, match="min <= max"):
        validate_behavior_config(cfg)


def test_validate_behavior_config_empty_compound() -> None:
    cfg = BehaviorConfig(
        intent_id="test_compound",
        handler_type=BehaviorHandlerType.COMPOUND,
        sub_configs=(),
    )
    with pytest.raises(BehaviorConfigValidationError, match="requires non-empty sub_configs"):
        validate_behavior_config(cfg)


def test_validate_behavior_catalog_readiness() -> None:
    configs = [
        BehaviorConfig(
            intent_id="intent_1",
            handler_type=BehaviorHandlerType.TOGGLE,
            target_substate="lighting",
            target_field="fog_light",
        ),
    ]
    # Valid catalog
    validate_behavior_catalog_readiness(configs, required_intents=["intent_1"])

    # Missing required intent raises BehaviorReadinessError
    with pytest.raises(BehaviorReadinessError, match="missing behavior configs"):
        validate_behavior_catalog_readiness(configs, required_intents=["intent_1", "intent_2"])


# ==============================================================================
# 2. Individual Handler Type Unit Tests
# ==============================================================================

def test_toggle_handler(state_machine: VehicleStateMachine) -> None:
    cfg = BehaviorConfig(
        intent_id="toggle_fog_light",
        handler_type=BehaviorHandlerType.TOGGLE,
        target_substate="lighting",
        target_field="fog_light",
    )
    handler = ToggleHandler(cfg, state_machine)

    # Initial fog_light is False
    assert state_machine.snapshot().lighting.fog_light is False

    # Execute toggle (no parameter -> toggle to True)
    res = handler({"proposal_id": "p1"})
    assert res["state_version"] == 1
    assert res["facts"]["value"] is True
    assert state_machine.snapshot().lighting.fog_light is True

    # Execute explicit off
    res2 = handler({"proposal_id": "p2", "parameters": {"state": "off"}})
    assert res2["state_version"] == 2
    assert res2["facts"]["value"] is False
    assert state_machine.snapshot().lighting.fog_light is False


def test_toggle_explicit_false(state_machine: VehicleStateMachine) -> None:
    cfg = BehaviorConfig(
        intent_id="toggle_fog_light",
        handler_type=BehaviorHandlerType.TOGGLE,
        target_substate="lighting",
        target_field="fog_light",
        param_name="fog_light",
    )
    handler = ToggleHandler(cfg, state_machine)

    # Pass explicit value=False
    res = handler({"proposal_id": "p1", "parameters": {"value": False}})
    assert res["facts"]["value"] is False
    assert state_machine.snapshot().lighting.fog_light is False


def test_enum_setter_handler(state_machine: VehicleStateMachine) -> None:
    cfg = BehaviorConfig(
        intent_id="set_drive_mode",
        handler_type=BehaviorHandlerType.ENUM_SETTER,
        target_substate="modes",
        target_field="drive_mode",
        enum_cls=DriveMode,
    )
    handler = EnumSetterHandler(cfg, state_machine)

    # Default drive_mode is NORMAL
    assert state_machine.snapshot().modes.drive_mode == DriveMode.NORMAL

    # Set SPORT
    res = handler({"proposal_id": "p1", "parameters": {"mode": "SPORT"}})
    assert res["state_version"] == 1
    assert res["facts"]["value"] == "SPORT"
    assert state_machine.snapshot().modes.drive_mode == DriveMode.SPORT

    # Invalid enum value raises ExecutionError
    with pytest.raises(ExecutionError) as exc_info:
        handler({"proposal_id": "p2", "parameters": {"mode": "INVALID_MODE"}})
    assert exc_info.value.code == "INVALID_ENUM_VALUE"


def test_access_actuator_handler(state_machine: VehicleStateMachine) -> None:
    cfg = BehaviorConfig(
        intent_id="open_door",
        handler_type=BehaviorHandlerType.ACCESS,
        target_substate="access",
    )
    handler = AccessActuatorHandler(cfg, state_machine)

    res = handler({"proposal_id": "p1", "parameters": {"door": "driver", "action": "open"}})
    assert res["state_version"] == 1
    assert res["facts"]["target"] == "driver_door"
    assert res["facts"]["position"] == "OPEN"

    driver_door = next(d for d in state_machine.snapshot().access.doors if d.door_id == "driver_door")
    assert driver_door.position == DoorPosition.OPEN
    assert driver_door.lock == LockState.UNLOCKED


def test_access_actuator_missing_door_target_fails(state_machine: VehicleStateMachine) -> None:
    cfg = BehaviorConfig(
        intent_id="open_door",
        handler_type=BehaviorHandlerType.ACCESS,
        target_substate="access",
    )
    handler = AccessActuatorHandler(cfg, state_machine)

    # Missing door parameter raises InvalidDoorTargetError instead of opening all doors
    with pytest.raises(InvalidDoorTargetError, match="Door target parameter is missing or empty"):
        handler({"proposal_id": "p1", "parameters": {"action": "open"}})


def test_position_actuator_handler(state_machine: VehicleStateMachine) -> None:
    cfg = BehaviorConfig(
        intent_id="set_seat_position",
        handler_type=BehaviorHandlerType.POSITION,
        target_substate="cabin",
        target_field="driver_seat_position",
        value_range=(0.0, 1.0),
    )
    handler = PositionActuatorHandler(cfg, state_machine)

    res = handler({"proposal_id": "p1", "parameters": {"level": 0.8}})
    assert res["state_version"] == 1
    assert res["facts"]["value"] == 0.8
    assert state_machine.snapshot().cabin.driver_seat_position == 0.8

    # Test out of range
    with pytest.raises(ExecutionError) as exc_info:
        handler({"proposal_id": "p2", "parameters": {"level": 1.5}})
    assert exc_info.value.code == "VALUE_OUT_OF_RANGE"


def test_position_explicit_zero(state_machine: VehicleStateMachine) -> None:
    cfg = BehaviorConfig(
        intent_id="set_seat_position",
        handler_type=BehaviorHandlerType.POSITION,
        target_substate="cabin",
        target_field="driver_seat_position",
        value_range=(0.0, 1.0),
        param_name="seat_pos",
    )
    handler = PositionActuatorHandler(cfg, state_machine)

    res = handler({"proposal_id": "p1", "parameters": {"value": 0.0}})
    assert res["facts"]["value"] == 0.0
    assert state_machine.snapshot().cabin.driver_seat_position == 0.0


def test_timed_transition_handler(state_machine: VehicleStateMachine) -> None:
    cfg = BehaviorConfig(
        intent_id="activate_hud",
        handler_type=BehaviorHandlerType.TIMED,
        target_substate="cabin",
        target_field="hud_active",
        duration_seconds=120.0,
    )
    handler = TimedTransitionHandler(cfg, state_machine)

    res = handler({"proposal_id": "p1", "parameters": {"duration": 180}})
    assert res["state_version"] == 1
    assert res["facts"]["duration_seconds"] == 180.0
    assert state_machine.snapshot().cabin.hud_active is True


def test_one_shot_event_handler(state_machine: VehicleStateMachine) -> None:
    cfg = BehaviorConfig(
        intent_id="flash_lights",
        handler_type=BehaviorHandlerType.ONE_SHOT,
        event_name="FLASH_HEADLIGHTS_BURST",
    )
    handler = OneShotEventHandler(cfg, state_machine)

    res = handler({"proposal_id": "p1"})
    assert res["facts"]["one_shot_event"] == "FLASH_HEADLIGHTS_BURST"
    assert res["facts"]["triggered"] is True


def test_active_action_handler(state_machine: VehicleStateMachine) -> None:
    cfg = BehaviorConfig(
        intent_id="start_autopark",
        handler_type=BehaviorHandlerType.ACTIVE_ACTION,
        active_action_name="autopark",
    )
    handler = ActiveActionHandler(cfg, state_machine)

    res = handler({"proposal_id": "p1", "parameters": {"action": "start"}})
    assert res["state_version"] == 1
    assert res["facts"]["phase"] == "started"

    active_actions = state_machine.snapshot().active_actions
    assert len(active_actions) == 1
    assert active_actions[0].intent == "start_autopark"
    assert active_actions[0].phase == ActiveActionPhase.STARTED


def test_compound_action_handler(state_machine: VehicleStateMachine) -> None:
    sub1 = BehaviorConfig(
        intent_id="sub_toggle",
        handler_type=BehaviorHandlerType.TOGGLE,
        target_substate="lighting",
        target_field="fog_light",
    )
    sub2 = BehaviorConfig(
        intent_id="sub_enum",
        handler_type=BehaviorHandlerType.ENUM_SETTER,
        target_substate="modes",
        target_field="drive_mode",
        enum_cls=DriveMode,
        default_value=DriveMode.SPORT,
    )
    compound_cfg = BehaviorConfig(
        intent_id="prep_sport_night_mode",
        handler_type=BehaviorHandlerType.COMPOUND,
        sub_configs=(sub1, sub2),
    )

    handler = CompoundActionHandler(compound_cfg, state_machine)
    res = handler({"proposal_id": "p1"})

    assert res["state_version"] == 1
    assert res["facts"]["compound_steps"] == 2
    assert state_machine.snapshot().lighting.fog_light is True
    assert state_machine.snapshot().modes.drive_mode == DriveMode.SPORT


# ==============================================================================
# 3. Gateway Fail-Closed Authorized Execution Tests
# ==============================================================================

def test_gateway_execution_authorized(gateway: VehicleToolGateway) -> None:
    proposal = make_test_proposal(
        proposal_id="prop-101",
        tool="toggle_fog_light",
        arguments={"state": "on"},
    )
    digest = proposal_digest(proposal)
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    permit = {
        "permit_id": "pmt-101",
        "intent": "toggle_fog_light",
        "proposal_digest": digest,
        "rule_id": "R001",
        "state_version": 0,
        "policy_checksum": "sha256:" + "a" * 64,
        "single_use": True,
        "issued_at": now_iso,
        "expires_at": datetime.now(tz=timezone.utc).replace(year=2030).isoformat(),
    }
    decision = {
        "contract_version": "1.0.0",
        "kind": "decision",
        "request_id": "req-101",
        "proposal_id": proposal["proposal_id"],
        "intent": "toggle_fog_light",
        "outcome": "ALLOW",
        "rule_id": "R001",
        "state_version": 0,
        "policy_checksum": "sha256:" + "a" * 64,
        "reason_code": "SAFE",
        "permit": permit,
    }

    result = gateway.execute(proposal, decision)
    assert result.success is True
    assert result.state_version == 1
    assert result.facts["value"] is True


def test_gateway_registered_handler_failure_propagates(gateway: VehicleToolGateway) -> None:
    # Established baseline state version
    valid_proposal = make_test_proposal(
        proposal_id="prop-200",
        tool="set_drive_mode",
        arguments={"mode": "ECO"},
    )
    valid_digest = proposal_digest(valid_proposal)
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    valid_permit = {
        "permit_id": "pmt-200",
        "intent": "set_drive_mode",
        "proposal_digest": valid_digest,
        "rule_id": "R001",
        "state_version": 0,
        "policy_checksum": "sha256:" + "a" * 64,
        "single_use": True,
        "issued_at": now_iso,
        "expires_at": datetime.now(tz=timezone.utc).replace(year=2030).isoformat(),
    }
    valid_decision = {
        "contract_version": "1.0.0",
        "kind": "decision",
        "request_id": "req-200",
        "proposal_id": valid_proposal["proposal_id"],
        "intent": "set_drive_mode",
        "outcome": "ALLOW",
        "rule_id": "R001",
        "state_version": 0,
        "policy_checksum": "sha256:" + "a" * 64,
        "reason_code": "SAFE",
        "permit": valid_permit,
    }

    valid_result = gateway.execute(valid_proposal, valid_decision)
    assert valid_result.success is True
    baseline_state_version = valid_result.state_version

    # Invoke registered handler with invalid parameters -> ExecutionError
    invalid_proposal = make_test_proposal(
        proposal_id="prop-201",
        tool="set_drive_mode",
        arguments={"mode": "INVALID_MODE"},
    )
    invalid_digest = proposal_digest(invalid_proposal)
    invalid_permit = {
        "permit_id": "pmt-201",
        "intent": "set_drive_mode",
        "proposal_digest": invalid_digest,
        "rule_id": "R001",
        "state_version": baseline_state_version,
        "policy_checksum": "sha256:" + "a" * 64,
        "single_use": True,
        "issued_at": now_iso,
        "expires_at": datetime.now(tz=timezone.utc).replace(year=2030).isoformat(),
    }
    invalid_decision = {
        "contract_version": "1.0.0",
        "kind": "decision",
        "request_id": "req-201",
        "proposal_id": invalid_proposal["proposal_id"],
        "intent": "set_drive_mode",
        "outcome": "ALLOW",
        "rule_id": "R001",
        "state_version": baseline_state_version,
        "policy_checksum": "sha256:" + "a" * 64,
        "reason_code": "SAFE",
        "permit": invalid_permit,
    }

    result = gateway.execute(invalid_proposal, invalid_decision)
    assert result.success is False
    assert result.error is not None
    assert result.error.code == "INVALID_ENUM_VALUE"
    assert gateway.verifier.store.is_used("pmt-201") is True


def test_gateway_unregistered_handler_fails(gateway: VehicleToolGateway) -> None:
    proposal = make_test_proposal(
        proposal_id="prop-102",
        tool="unregistered_tool",
        arguments={},
    )
    digest = proposal_digest(proposal)
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    permit = {
        "permit_id": "pmt-102",
        "intent": "unregistered_tool",
        "proposal_digest": digest,
        "rule_id": "R001",
        "state_version": 0,
        "policy_checksum": "sha256:" + "a" * 64,
        "single_use": True,
        "issued_at": now_iso,
        "expires_at": datetime.now(tz=timezone.utc).replace(year=2030).isoformat(),
    }
    decision = {
        "contract_version": "1.0.0",
        "kind": "decision",
        "request_id": "req-102",
        "proposal_id": proposal["proposal_id"],
        "intent": "unregistered_tool",
        "outcome": "ALLOW",
        "rule_id": "R001",
        "state_version": 0,
        "policy_checksum": "sha256:" + "a" * 64,
        "reason_code": "SAFE",
        "permit": permit,
    }

    result = gateway.execute(proposal, decision)
    assert result.success is False
    assert result.error.code == "HANDLER_NOT_FOUND"
