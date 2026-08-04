"""Vehicle execution boundary and tool gateway module."""

from .errors import (
    ExpiredPermitError,
    ExecutionError,
    GatewayExecutionError,
    HandlerNotFoundError,
    InvalidPermitError,
    PermitVerificationError,
    ReplayAttackError,
    SubstitutionAttackError,
)
from .gateway import HandlerRegistry, VehicleToolGateway
from .verifier import PermitStore, PermitVerifier

__all__ = [
    "ExpiredPermitError",
    "ExecutionError",
    "GatewayExecutionError",
    "HandlerNotFoundError",
    "HandlerRegistry",
    "InvalidPermitError",
    "PermitStore",
    "PermitVerificationError",
    "PermitVerifier",
    "ReplayAttackError",
    "SubstitutionAttackError",
    "VehicleToolGateway",
]
