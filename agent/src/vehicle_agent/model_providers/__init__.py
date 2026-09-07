"""Provider-neutral model boundary for the Aegis Agent."""

from .adapters import GeminiAdapter, ModelProviderAdapter, OpenAIAdapter, ProviderTransport
from .contracts import (
    ModelActionProposal,
    ModelErrorCode,
    ModelProviderError,
    ProviderMetadata,
    ProposalKind,
)
from .selection import ModelProviderConfig, ModelProviderRouter, ProviderReadiness, TurnBinding
from .transports import (
    GeminiRestTransport,
    OpenAIRestTransport,
    RateLimitedTransport,
    RetryableTransportError,
)

__all__ = [
    "GeminiAdapter",
    "GeminiRestTransport",
    "ModelActionProposal",
    "ModelErrorCode",
    "ModelProviderAdapter",
    "ModelProviderConfig",
    "ModelProviderError",
    "ModelProviderRouter",
    "OpenAIAdapter",
    "OpenAIRestTransport",
    "ProviderMetadata",
    "ProviderReadiness",
    "ProviderTransport",
    "ProposalKind",
    "RateLimitedTransport",
    "RetryableTransportError",
    "TurnBinding",
]
