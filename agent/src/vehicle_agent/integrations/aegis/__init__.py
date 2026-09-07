"""Aegis integration for the Agent authorization ports."""

from .client import (
    GuardrailAdapterError,
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)

AegisClient = GuardrailClientAdapter
AegisClientConfig = GuardrailClientConfig
AegisIntegrationError = GuardrailAdapterError
AegisProvider = GuardrailProvider

__all__ = [
    "AegisClient",
    "AegisClientConfig",
    "AegisIntegrationError",
    "AegisProvider",
]
