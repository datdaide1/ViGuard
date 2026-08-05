"""Provider-neutral model boundary for the ViVi Agent."""

from .adapters import GeminiAdapter, ModelProviderAdapter, OpenAIAdapter, ProviderTransport
from .contracts import (
    ModelActionProposal,
    ModelErrorCode,
    ModelProviderError,
    ProviderMetadata,
    ProposalKind,
)
from .selection import ModelProviderConfig, ModelProviderRouter, ProviderReadiness, TurnBinding

__all__ = [
    "GeminiAdapter",
    "ModelActionProposal",
    "ModelErrorCode",
    "ModelProviderAdapter",
    "ModelProviderConfig",
    "ModelProviderError",
    "ModelProviderRouter",
    "OpenAIAdapter",
    "ProviderMetadata",
    "ProviderReadiness",
    "ProviderTransport",
    "ProposalKind",
    "TurnBinding",
]
