"""Vehicle simulator domain types."""

from .state import (
    DEFAULT_VEHICLE_STATE,
    VEHICLE_STATE_SCHEMA_VERSION,
    VehicleState,
    VehicleStateValidationError,
    get_preset,
)

__all__ = [
    "DEFAULT_VEHICLE_STATE",
    "VEHICLE_STATE_SCHEMA_VERSION",
    "VehicleState",
    "VehicleStateValidationError",
    "get_preset",
]
