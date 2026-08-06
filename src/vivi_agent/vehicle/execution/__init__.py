"""Vehicle execution boundary and tool gateway module."""

from .errors import (
    BehaviorConfigValidationError,
    BehaviorReadinessError,
    ExpiredPermitError,
    ExecutionError,
    GatewayExecutionError,
    HandlerNotFoundError,
    InvalidDoorTargetError,
    InvalidPermitError,
    PermitVerificationError,
    ReplayAttackError,
    SubstitutionAttackError,
)
from .gateway import HandlerRegistry, VehicleToolGateway
from .generic import (
    AccessActuatorHandler,
    ActiveActionHandler,
    BaseGenericHandler,
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
from .open_door import OpenDoorHandler, make_open_door_handler
from .verifier import PermitStore, PermitVerifier

__all__ = [
    "AccessActuatorHandler",
    "ActiveActionHandler",
    "BaseGenericHandler",
    "BehaviorConfig",
    "BehaviorConfigValidationError",
    "BehaviorHandlerType",
    "BehaviorReadinessError",
    "CompoundActionHandler",
    "EnumSetterHandler",
    "ExpiredPermitError",
    "ExecutionError",
    "GatewayExecutionError",
    "HandlerNotFoundError",
    "HandlerRegistry",
    "InvalidDoorTargetError",
    "InvalidPermitError",
    "OneShotEventHandler",
    "OpenDoorHandler",
    "PermitStore",
    "PermitVerificationError",
    "PermitVerifier",
    "PositionActuatorHandler",
    "ReplayAttackError",
    "SubstitutionAttackError",
    "TimedTransitionHandler",
    "ToggleHandler",
    "VehicleToolGateway",
    "create_generic_handler",
    "make_open_door_handler",
    "register_behavior_configs",
    "validate_behavior_catalog_readiness",
    "validate_behavior_config",
]


