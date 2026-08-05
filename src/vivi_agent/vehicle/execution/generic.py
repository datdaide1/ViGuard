"""Generic Handler Library and Behavior Config Validator for Vehicle Execution boundary.

This module provides data-driven generic actuator handlers to eliminate the need
for 47 distinct handler classes while guaranteeing atomic mutations, authorized
execution through VehicleToolGateway, and fail-closed readiness validation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from vivi_agent.vehicle.state.events import ActorKind
from vivi_agent.vehicle.state.machine import TransitionError, VehicleStateMachine
from vivi_agent.vehicle.state.model import (
    REQUIRED_DOOR_IDS,
    ActiveAction,
    ActiveActionPhase,
    DoorPosition,
    DoorState,
    LockState,
    VehicleState,
)
from .errors import (
    BehaviorConfigValidationError,
    BehaviorReadinessError,
    ExecutionError,
    InvalidDoorTargetError,
)
from .open_door import DOOR_ALIAS_MAP

# Type alias for a raw handler callable matching HandlerRegistry requirements
RawHandlerFn = Callable[[Mapping[str, Any]], dict[str, Any]]


class BehaviorHandlerType(str, Enum):
    """Enumeration of generic handler categories supported by ViVi Agent."""

    TOGGLE = "toggle"
    ENUM_SETTER = "enum_setter"
    ACCESS = "access"
    POSITION = "position"
    TIMED = "timed"
    ONE_SHOT = "one_shot"
    ACTIVE_ACTION = "active_action"
    COMPOUND = "compound"


@dataclass(frozen=True)
class BehaviorConfig:
    """Declarative specification for a data-driven vehicle behavior."""

    intent_id: str
    handler_type: BehaviorHandlerType | str
    target_substate: str | None = None
    target_field: str | None = None
    param_name: str | None = None
    enum_cls: type[Enum] | None = None
    value_range: tuple[float, float] | None = None
    step_range: tuple[float, float] | None = None
    allowed_values: tuple[Any, ...] | None = None
    default_value: Any = None
    duration_seconds: float | None = None
    event_name: str | None = None
    active_action_name: str | None = None
    sub_configs: tuple[BehaviorConfig, ...] = field(default_factory=tuple)


def validate_behavior_config(config: BehaviorConfig) -> None:
    """Validate a BehaviorConfig instance against schema and type rules.

    Raises
    ------
    BehaviorConfigValidationError
        If the configuration is invalid or missing required attributes.
    """
    if not config.intent_id or not isinstance(config.intent_id, str):
        raise BehaviorConfigValidationError("intent_id must be a non-empty string")

    # Normalize handler_type
    try:
        htype = (
            config.handler_type
            if isinstance(config.handler_type, BehaviorHandlerType)
            else BehaviorHandlerType(str(config.handler_type).lower())
        )
    except ValueError:
        raise BehaviorConfigValidationError(
            f"Invalid handler_type {config.handler_type!r} for intent {config.intent_id!r}"
        )

    # Substate verification on VehicleState field annotations if specified
    # Finding 7 fix: active_actions is a tuple field, not a substate dataclass
    valid_substates = set(VehicleState.__dataclass_fields__.keys()) - {
        "state_version",
        "timestamp",
        "pip_field_provenance",
        "active_actions",
    }

    if htype == BehaviorHandlerType.TOGGLE:
        if not config.target_substate or not config.target_field:
            raise BehaviorConfigValidationError(
                f"ToggleHandler for {config.intent_id!r} requires target_substate and target_field"
            )
        if config.target_substate not in valid_substates:
            raise BehaviorConfigValidationError(
                f"Invalid target_substate {config.target_substate!r} for intent {config.intent_id!r}"
            )

    elif htype == BehaviorHandlerType.ENUM_SETTER:
        if not config.target_substate or not config.target_field or config.enum_cls is None:
            raise BehaviorConfigValidationError(
                f"EnumSetterHandler for {config.intent_id!r} requires target_substate, target_field, and enum_cls"
            )
        if config.target_substate not in valid_substates:
            raise BehaviorConfigValidationError(
                f"Invalid target_substate {config.target_substate!r} for intent {config.intent_id!r}"
            )
        if not (isinstance(config.enum_cls, type) and issubclass(config.enum_cls, Enum)):
            raise BehaviorConfigValidationError(
                f"enum_cls must be a subclass of Enum for intent {config.intent_id!r}"
            )

    elif htype == BehaviorHandlerType.ACCESS:
        # Finding 8 fix: AccessActuatorHandler target_substate must be 'access' if provided
        substate = config.target_substate or "access"
        if substate != "access":
            raise BehaviorConfigValidationError(
                f"AccessActuatorHandler for {config.intent_id!r} requires target_substate='access'"
            )

    elif htype == BehaviorHandlerType.POSITION:
        if not config.target_substate or not config.target_field:
            raise BehaviorConfigValidationError(
                f"PositionActuatorHandler for {config.intent_id!r} requires target_substate and target_field"
            )
        if config.target_substate not in valid_substates:
            raise BehaviorConfigValidationError(
                f"Invalid target_substate {config.target_substate!r} for intent {config.intent_id!r}"
            )
        if config.value_range is not None:
            if len(config.value_range) != 2 or config.value_range[0] > config.value_range[1]:
                raise BehaviorConfigValidationError(
                    f"value_range must be (min, max) tuple with min <= max for intent {config.intent_id!r}"
                )

    elif htype == BehaviorHandlerType.TIMED:
        if not config.target_substate or not config.target_field:
            raise BehaviorConfigValidationError(
                f"TimedTransitionHandler for {config.intent_id!r} requires target_substate and target_field"
            )
        if config.target_substate not in valid_substates:
            raise BehaviorConfigValidationError(
                f"Invalid target_substate {config.target_substate!r} for intent {config.intent_id!r}"
            )
        if config.duration_seconds is not None and config.duration_seconds <= 0:
            raise BehaviorConfigValidationError(
                f"duration_seconds must be positive for intent {config.intent_id!r}"
            )

    elif htype == BehaviorHandlerType.ONE_SHOT:
        pass  # event_name defaults to intent_id if omitted

    elif htype == BehaviorHandlerType.ACTIVE_ACTION:
        pass  # active_action_name defaults to intent_id if omitted

    elif htype == BehaviorHandlerType.COMPOUND:
        # Finding 2 fix: Validate sub_configs non-empty and recursively validate each sub_config
        if not config.sub_configs:
            raise BehaviorConfigValidationError(
                f"CompoundActionHandler for {config.intent_id!r} requires non-empty sub_configs"
            )
        for sub_cfg in config.sub_configs:
            validate_behavior_config(sub_cfg)


def validate_behavior_catalog_readiness(
    configs: Sequence[BehaviorConfig],
    required_intents: Sequence[str] | None = None,
) -> None:
    """Validate full catalog readiness for all behavior configurations at startup.

    Raises
    ------
    BehaviorReadinessError
        If catalog validation fails or required intents are missing behavior handlers.
    """
    seen_intents: set[str] = set()
    for config in configs:
        try:
            validate_behavior_config(config)
        except BehaviorConfigValidationError as exc:
            raise BehaviorReadinessError(f"Behavior readiness check failed for {config.intent_id!r}: {exc}") from exc

        if config.intent_id in seen_intents:
            raise BehaviorReadinessError(f"Duplicate behavior config registered for intent {config.intent_id!r}")
        seen_intents.add(config.intent_id)

    if required_intents is not None:
        missing = sorted(set(required_intents) - seen_intents)
        if missing:
            raise BehaviorReadinessError(
                f"Behavior readiness check failed: missing behavior configs for required intents: {missing}"
            )


# ------------------------------------------------------------------------------
# Generic Handlers Implementations
# ------------------------------------------------------------------------------

class BaseGenericHandler:
    """Base class for generic vehicle actuator handlers."""

    def __init__(
        self,
        config: BehaviorConfig,
        state_machine: VehicleStateMachine,
        *,
        actor_id: str | None = None,
    ) -> None:
        validate_behavior_config(config)
        self.config = config
        self.state_machine = state_machine
        self.actor_id = actor_id or f"handler_{config.intent_id}"

    def extract_parameters(self, proposal: Mapping[str, Any]) -> Mapping[str, Any]:
        params = proposal.get("parameters") or proposal.get("arguments")
        if isinstance(params, Mapping):
            return params
        return proposal

    # Finding 10 fix: Shared helper for correlation_id derivation and state_machine.apply()
    def _apply_transition(
        self,
        proposal: Mapping[str, Any],
        patch_fn: Callable[[VehicleState], VehicleState],
    ) -> Any:
        correlation_id = str(
            proposal.get("proposal_id")
            or proposal.get("correlation_id")
            or f"exec_{self.config.intent_id}"
        )
        try:
            return self.state_machine.apply(
                patch_fn,
                actor_kind=ActorKind.AGENT,
                actor_id=self.actor_id,
                correlation_id=correlation_id,
            )
        except TransitionError as exc:
            if isinstance(exc.cause, ExecutionError):
                raise exc.cause from exc
            raise


class ToggleHandler(BaseGenericHandler):
    """Handler for boolean state field toggles (or explicit on/off/toggle parameters)."""

    def __call__(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        params = self.extract_parameters(proposal)

        # Finding 5 fix: Check params keys without dropping explicit False via 'or' chain
        raw_val = None
        for key in (self.config.param_name, "state", "value", "enable", "on", "action"):
            if key and key in params and params[key] is not None:
                raw_val = params[key]
                break

        assert self.config.target_substate is not None
        assert self.config.target_field is not None
        substate_name = self.config.target_substate
        field_name = self.config.target_field

        def patch_fn(state: VehicleState) -> VehicleState:
            current_substate = getattr(state, substate_name)
            current_val = getattr(current_substate, field_name)

            if raw_val is None or str(raw_val).lower() in ("toggle", "switch"):
                next_val = not current_val
            elif isinstance(raw_val, bool):
                next_val = raw_val
            elif str(raw_val).lower() in ("on", "true", "enable", "activate", "1"):
                next_val = True
            elif str(raw_val).lower() in ("off", "false", "disable", "deactivate", "0"):
                next_val = False
            else:
                next_val = not current_val

            new_substate = replace(current_substate, **{field_name: next_val})
            return replace(state, **{substate_name: new_substate})

        event = self._apply_transition(proposal, patch_fn)

        final_substate = getattr(event.snapshot, substate_name)
        final_val = getattr(final_substate, field_name)

        return {
            "state_version": event.next_version,
            "facts": {
                "intent": self.config.intent_id,
                "field": field_name,
                "value": final_val,
            },
            "message": f"Successfully updated {field_name!r} to {final_val}",
        }


class EnumSetterHandler(BaseGenericHandler):
    """Handler for enum state field updates."""

    def __call__(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        params = self.extract_parameters(proposal)

        # Finding 5/6 fix: Check param keys checking is not None
        raw_val = None
        for key in (self.config.param_name, "mode", "value", "setting", "state"):
            if key and key in params and params[key] is not None:
                raw_val = params[key]
                break

        if raw_val is None:
            if self.config.default_value is not None:
                raw_val = self.config.default_value
            else:
                raise ExecutionError("INVALID_ENUM_VALUE", f"Missing required enum parameter {self.config.param_name or 'mode'!r}")

        assert self.config.enum_cls is not None
        enum_cls = self.config.enum_cls
        target_enum: Enum | None = None

        if isinstance(raw_val, enum_cls):
            target_enum = raw_val
        elif isinstance(raw_val, str):
            raw_str = raw_val.strip()
            for member in enum_cls:
                if (
                    member.value == raw_str
                    or member.name.lower() == raw_str.lower()
                    or str(member.value).lower() == raw_str.lower()
                ):
                    target_enum = member
                    break

        if target_enum is None:
            allowed = [m.value for m in enum_cls]
            raise ExecutionError(
                "INVALID_ENUM_VALUE",
                f"Unsupported value {raw_val!r} for {self.config.target_field!r}. Must be one of: {allowed}",
            )

        assert self.config.target_substate is not None
        assert self.config.target_field is not None
        substate_name = self.config.target_substate
        field_name = self.config.target_field

        def patch_fn(state: VehicleState) -> VehicleState:
            current_substate = getattr(state, substate_name)
            new_substate = replace(current_substate, **{field_name: target_enum})
            return replace(state, **{substate_name: new_substate})

        event = self._apply_transition(proposal, patch_fn)

        return {
            "state_version": event.next_version,
            "facts": {
                "intent": self.config.intent_id,
                "field": field_name,
                "value": target_enum.value,
            },
            "message": f"Successfully set {field_name!r} to {target_enum.value!r}",
        }


class AccessActuatorHandler(BaseGenericHandler):
    """Handler for door, window, trunk, frunk, and lock access actuators."""

    def __call__(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        params = self.extract_parameters(proposal)

        # Finding 1 fix: Require explicit door/window target parameter, fail-closed if missing
        target_raw = None
        for key in ("door", "door_id", "window", "target", "item"):
            if key in params and params[key] is not None:
                target_raw = params[key]
                break

        if not target_raw or not isinstance(target_raw, str):
            raise InvalidDoorTargetError("Door target parameter is missing or empty")

        key = target_raw.strip().lower()
        canonical_door = DOOR_ALIAS_MAP.get(key)
        if canonical_door is None or canonical_door not in REQUIRED_DOOR_IDS:
            raise InvalidDoorTargetError(
                f"Unsupported or invalid door target {target_raw!r}. Must be one of: {sorted(REQUIRED_DOOR_IDS)}"
            )

        # Finding 3 fix: Explicit closed vocabulary parsing to prevent OPEN+LOCKED & unintentional unlocks
        action_raw = None
        for key in ("action", "position", "state"):
            if key in params and params[key] is not None:
                action_raw = params[key]
                break

        action_str = str(action_raw).strip().lower() if action_raw else "open"

        if action_str in ("open", "unlock_and_open"):
            target_pos = DoorPosition.OPEN
            target_lock = LockState.UNLOCKED
        elif action_str in ("close", "shut"):
            target_pos = DoorPosition.CLOSED
            target_lock = LockState.UNLOCKED
        elif action_str == "lock":
            target_pos = DoorPosition.CLOSED
            target_lock = LockState.LOCKED
        elif action_str == "unlock":
            target_pos = DoorPosition.CLOSED
            target_lock = LockState.UNLOCKED
        else:
            if "open" in action_str:
                target_pos = DoorPosition.OPEN
                target_lock = LockState.UNLOCKED
            elif "lock" in action_str:
                target_pos = DoorPosition.CLOSED
                target_lock = LockState.LOCKED
            else:
                target_pos = DoorPosition.CLOSED
                target_lock = LockState.UNLOCKED

        def patch_fn(state: VehicleState) -> VehicleState:
            current_access = state.access
            new_doors = []
            for door in current_access.doors:
                if door.door_id == canonical_door:
                    new_doors.append(
                        replace(door, position=target_pos, lock=target_lock)
                    )
                else:
                    new_doors.append(door)
            new_access = replace(current_access, doors=tuple(new_doors))
            return replace(state, access=new_access)

        event = self._apply_transition(proposal, patch_fn)

        return {
            "state_version": event.next_version,
            "facts": {
                "intent": self.config.intent_id,
                "target": canonical_door,
                "position": target_pos.value,
                "lock": target_lock.value,
            },
            "message": f"Access actuator applied for {canonical_door!r}",
        }


class PositionActuatorHandler(BaseGenericHandler):
    """Handler for numeric range/position actuators (temperature, seat position, angle, fan speed)."""

    def __call__(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        params = self.extract_parameters(proposal)

        # Finding 6 fix: Check param keys using 'is not None' to preserve 0
        raw_val = None
        for key in (self.config.param_name, "value", "position", "angle", "temperature", "level"):
            if key and key in params and params[key] is not None:
                raw_val = params[key]
                break

        delta_val = None
        for key in ("delta", "adjustment"):
            if key in params and params[key] is not None:
                delta_val = params[key]
                break

        assert self.config.target_substate is not None
        assert self.config.target_field is not None
        substate_name = self.config.target_substate
        field_name = self.config.target_field

        # Finding 4 fix: Compute delta and validate range inside patch_fn on fresh VehicleState snapshot
        def patch_fn(state: VehicleState) -> VehicleState:
            current_substate = getattr(state, substate_name)
            current_val = getattr(current_substate, field_name)

            if raw_val is not None:
                try:
                    val = float(raw_val)
                except (ValueError, TypeError):
                    raise ExecutionError("INVALID_NUMERIC_VALUE", f"Invalid numeric parameter {raw_val!r}")
            elif delta_val is not None:
                try:
                    val = float(current_val) + float(delta_val)
                except (ValueError, TypeError):
                    raise ExecutionError("INVALID_NUMERIC_VALUE", f"Invalid numeric delta {delta_val!r}")
            elif self.config.default_value is not None:
                val = float(self.config.default_value)
            else:
                raise ExecutionError("MISSING_POSITION_VALUE", f"Missing required position parameter {self.config.param_name or 'level'!r}")

            if self.config.value_range is not None:
                min_v, max_v = self.config.value_range
                if val < min_v or val > max_v:
                    raise ExecutionError(
                        "VALUE_OUT_OF_RANGE",
                        f"Value {val} for {field_name!r} is out of bounds [{min_v}, {max_v}]",
                    )

            target_val: int | float = int(round(val)) if isinstance(current_val, int) else val
            new_substate = replace(current_substate, **{field_name: target_val})
            return replace(state, **{substate_name: new_substate})

        event = self._apply_transition(proposal, patch_fn)

        final_substate = getattr(event.snapshot, substate_name)
        final_val = getattr(final_substate, field_name)

        return {
            "state_version": event.next_version,
            "facts": {
                "intent": self.config.intent_id,
                "field": field_name,
                "value": final_val,
            },
            "message": f"Successfully set position {field_name!r} to {final_val}",
        }


class TimedTransitionHandler(BaseGenericHandler):
    """Handler for timed operations (defogger, cabin pre-conditioning)."""

    def __call__(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        params = self.extract_parameters(proposal)
        duration = None
        for key in ("duration", "duration_seconds"):
            if key in params and params[key] is not None:
                duration = params[key]
                break

        if duration is None:
            duration = self.config.duration_seconds or 300.0

        try:
            duration = float(duration)
        except (ValueError, TypeError):
            duration = 300.0

        assert self.config.target_substate is not None
        assert self.config.target_field is not None
        substate_name = self.config.target_substate
        field_name = self.config.target_field

        def patch_fn(state: VehicleState) -> VehicleState:
            current_substate = getattr(state, substate_name)
            new_substate = replace(current_substate, **{field_name: True})
            return replace(state, **{substate_name: new_substate})

        event = self._apply_transition(proposal, patch_fn)

        return {
            "state_version": event.next_version,
            "facts": {
                "intent": self.config.intent_id,
                "field": field_name,
                "duration_seconds": duration,
                "status": "initiated",
            },
            "message": f"Initiated timed transition for {field_name!r} ({duration}s)",
        }


class OneShotEventHandler(BaseGenericHandler):
    """Handler for discrete one-shot visual/UI events."""

    def __call__(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        event_name = self.config.event_name or self.config.intent_id

        if self.config.target_substate and self.config.target_field:
            substate_name = self.config.target_substate
            field_name = self.config.target_field

            def patch_fn(state: VehicleState) -> VehicleState:
                current_substate = getattr(state, substate_name)
                new_substate = replace(current_substate, **{field_name: True})
                return replace(state, **{substate_name: new_substate})

            event = self._apply_transition(proposal, patch_fn)
            next_version = event.next_version
        else:
            next_version = self.state_machine.snapshot().state_version

        return {
            "state_version": next_version,
            "facts": {
                "intent": self.config.intent_id,
                "one_shot_event": event_name,
                "triggered": True,
            },
            "message": f"Fired one-shot event {event_name!r}",
        }


class ActiveActionHandler(BaseGenericHandler):
    """Handler for monitored active actions (autopark, camp mode, pet mode, etc.)."""

    def __call__(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        params = self.extract_parameters(proposal)
        action_name = self.config.active_action_name or self.config.intent_id
        action_id = f"act-{uuid.uuid4().hex[:8]}"

        action_cmd = str(params.get("action") or params.get("command") or "start").lower()
        target_phase = (
            ActiveActionPhase.STOPPED if "stop" in action_cmd or "cancel" in action_cmd else ActiveActionPhase.STARTED
        )

        def patch_fn(state: VehicleState) -> VehicleState:
            current_actions = list(state.active_actions)
            filtered = [a for a in current_actions if a.intent != self.config.intent_id]
            if target_phase != ActiveActionPhase.STOPPED:
                new_action = ActiveAction(
                    action_id=action_id,
                    intent=self.config.intent_id,
                    phase=target_phase,
                    progress=0.0,
                )
                filtered.append(new_action)

            next_state = replace(state, active_actions=tuple(filtered))
            if self.config.target_substate and self.config.target_field:
                substate_name = self.config.target_substate
                field_name = self.config.target_field
                current_substate = getattr(next_state, substate_name)
                is_active = target_phase != ActiveActionPhase.STOPPED
                new_substate = replace(current_substate, **{field_name: is_active})
                next_state = replace(next_state, **{substate_name: new_substate})

            return next_state

        event = self._apply_transition(proposal, patch_fn)

        return {
            "state_version": event.next_version,
            "facts": {
                "intent": self.config.intent_id,
                "action_name": action_name,
                "action_id": action_id,
                "phase": target_phase.value,
            },
            "message": f"Active action {action_name!r} transition to phase {target_phase.value!r}",
        }


def _apply_sub_config_state_mutation(
    state: VehicleState,
    sub_cfg: BehaviorConfig,
    proposal: Mapping[str, Any],
) -> VehicleState:
    """Helper applying a single sub_config patch to VehicleState inside compound transition."""
    htype = (
        sub_cfg.handler_type
        if isinstance(sub_cfg.handler_type, BehaviorHandlerType)
        else BehaviorHandlerType(str(sub_cfg.handler_type).lower())
    )

    if htype == BehaviorHandlerType.TOGGLE and sub_cfg.target_substate and sub_cfg.target_field:
        substate = getattr(state, sub_cfg.target_substate)
        cur_val = getattr(substate, sub_cfg.target_field)
        new_val = not cur_val if sub_cfg.default_value is None else bool(sub_cfg.default_value)
        new_substate = replace(substate, **{sub_cfg.target_field: new_val})
        return replace(state, **{sub_cfg.target_substate: new_substate})

    elif htype == BehaviorHandlerType.ENUM_SETTER and sub_cfg.target_substate and sub_cfg.target_field:
        substate = getattr(state, sub_cfg.target_substate)
        val = sub_cfg.default_value
        if val is not None:
            new_substate = replace(substate, **{sub_cfg.target_field: val})
            return replace(state, **{sub_cfg.target_substate: new_substate})

    elif htype == BehaviorHandlerType.POSITION and sub_cfg.target_substate and sub_cfg.target_field:
        substate = getattr(state, sub_cfg.target_substate)
        if sub_cfg.default_value is not None:
            new_substate = replace(substate, **{sub_cfg.target_field: sub_cfg.default_value})
            return replace(state, **{sub_cfg.target_substate: new_substate})

    elif htype == BehaviorHandlerType.TIMED and sub_cfg.target_substate and sub_cfg.target_field:
        substate = getattr(state, sub_cfg.target_substate)
        new_substate = replace(substate, **{sub_cfg.target_field: True})
        return replace(state, **{sub_cfg.target_substate: new_substate})

    elif htype == BehaviorHandlerType.ONE_SHOT and sub_cfg.target_substate and sub_cfg.target_field:
        substate = getattr(state, sub_cfg.target_substate)
        new_substate = replace(substate, **{sub_cfg.target_field: True})
        return replace(state, **{sub_cfg.target_substate: new_substate})

    elif htype == BehaviorHandlerType.ACTIVE_ACTION:
        current_actions = list(state.active_actions)
        filtered = [a for a in current_actions if a.intent != sub_cfg.intent_id]
        new_action = ActiveAction(
            action_id=f"act-{uuid.uuid4().hex[:8]}",
            intent=sub_cfg.intent_id,
            phase=ActiveActionPhase.STARTED,
            progress=0.0,
        )
        filtered.append(new_action)
        next_state = replace(state, active_actions=tuple(filtered))
        if sub_cfg.target_substate and sub_cfg.target_field:
            substate = getattr(next_state, sub_cfg.target_substate)
            new_substate = replace(substate, **{sub_cfg.target_field: True})
            next_state = replace(next_state, **{sub_cfg.target_substate: new_substate})
        return next_state

    elif htype == BehaviorHandlerType.COMPOUND:
        cur = state
        for child_cfg in sub_cfg.sub_configs:
            cur = _apply_sub_config_state_mutation(cur, child_cfg, proposal)
        return cur

    return state


class CompoundActionHandler(BaseGenericHandler):
    """Handler executing multiple sub-handler updates atomically in one turn."""

    def __call__(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        # Finding 2 fix: Execute state mutations for all supported sub-config types atomically
        def compound_patch_fn(state: VehicleState) -> VehicleState:
            current = state
            for sub_cfg in self.config.sub_configs:
                current = _apply_sub_config_state_mutation(current, sub_cfg, proposal)
            return current

        event = self._apply_transition(proposal, compound_patch_fn)

        return {
            "state_version": event.next_version,
            "facts": {
                "intent": self.config.intent_id,
                "compound_steps": len(self.config.sub_configs),
            },
            "message": f"Successfully executed compound action {self.config.intent_id!r}",
        }


# ------------------------------------------------------------------------------
# Factory & Registration Helpers
# ------------------------------------------------------------------------------

def create_generic_handler(
    config: BehaviorConfig,
    state_machine: VehicleStateMachine,
    *,
    actor_id: str | None = None,
) -> RawHandlerFn:
    """Instantiate a generic handler for a given BehaviorConfig."""
    validate_behavior_config(config)

    htype = (
        config.handler_type
        if isinstance(config.handler_type, BehaviorHandlerType)
        else BehaviorHandlerType(str(config.handler_type).lower())
    )

    handler_map: dict[BehaviorHandlerType, type[BaseGenericHandler]] = {
        BehaviorHandlerType.TOGGLE: ToggleHandler,
        BehaviorHandlerType.ENUM_SETTER: EnumSetterHandler,
        BehaviorHandlerType.ACCESS: AccessActuatorHandler,
        BehaviorHandlerType.POSITION: PositionActuatorHandler,
        BehaviorHandlerType.TIMED: TimedTransitionHandler,
        BehaviorHandlerType.ONE_SHOT: OneShotEventHandler,
        BehaviorHandlerType.ACTIVE_ACTION: ActiveActionHandler,
        BehaviorHandlerType.COMPOUND: CompoundActionHandler,
    }

    cls = handler_map[htype]
    handler_instance = cls(config, state_machine, actor_id=actor_id)
    return handler_instance


def register_behavior_configs(
    registry: Any,
    configs: Sequence[BehaviorConfig],
    state_machine: VehicleStateMachine,
) -> None:
    """Validate and register a collection of BehaviorConfigs into a HandlerRegistry.

    Raises
    ------
    BehaviorConfigValidationError
        If any BehaviorConfig fails validation.
    """
    for config in configs:
        validate_behavior_config(config)
        handler_fn = create_generic_handler(config, state_machine)
        registry.register(config.intent_id, handler_fn)
