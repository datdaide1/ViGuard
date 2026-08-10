"""ViGuard integration for the Agent authorization ports."""

from .client import (
    GuardrailAdapterError,
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)

ViGuardClient = GuardrailClientAdapter
ViGuardClientConfig = GuardrailClientConfig
ViGuardIntegrationError = GuardrailAdapterError
ViGuardProvider = GuardrailProvider

__all__ = [
    "ViGuardClient",
    "ViGuardClientConfig",
    "ViGuardIntegrationError",
    "ViGuardProvider",
]
