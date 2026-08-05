"""Vehicle execution boundary and tool gateway module."""

from .errors import (
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
from .open_door import OpenDoorHandler, make_open_door_handler
from .verifier import PermitStore, PermitVerifier

__all__ = [
    "ExpiredPermitError",
    "ExecutionError",
    "GatewayExecutionError",
    "HandlerNotFoundError",
    "HandlerRegistry",
    "InvalidDoorTargetError",
    "InvalidPermitError",
    "OpenDoorHandler",
    "PermitStore",
    "PermitVerificationError",
    "PermitVerifier",
    "ReplayAttackError",
    "SubstitutionAttackError",
    "VehicleToolGateway",
    "make_open_door_handler",
]

