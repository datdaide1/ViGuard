"""Shared contracts returned by every model provider.

The contracts intentionally exclude provider reasoning and every Guardrail- or
vehicle-owned field. Model output remains an untrusted proposal at this layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class ProposalKind(str, Enum):
    ACTION = "action"
    CLARIFICATION = "clarification"
    RESPONSE = "response"


class ModelErrorCode(str, Enum):
    NOT_READY = "MODEL_PROVIDER_NOT_READY"
    TIMEOUT = "MODEL_PROVIDER_TIMEOUT"
    API_ERROR = "MODEL_PROVIDER_API_ERROR"
    MALFORMED_OUTPUT = "MODEL_PROVIDER_MALFORMED_OUTPUT"
    INVALID_CONFIG = "MODEL_PROVIDER_INVALID_CONFIG"
    ALL_UNAVAILABLE = "MODEL_PROVIDERS_UNAVAILABLE"
    TURN_PINNED = "MODEL_PROVIDER_TURN_PINNED"


class ModelProviderError(RuntimeError):
    def __init__(
        self,
        code: ModelErrorCode,
        detail: str,
        *,
        provider: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code
        self.detail = detail
        self.provider = provider
        self.retryable = retryable


@dataclass(frozen=True)
class ProviderMetadata:
    provider: str
    model_id: str
    config_checksum: str
    latency_ms: int

    def to_event_metadata(self) -> dict[str, str | int]:
        return {
            "model_provider": self.provider,
            "model_id": self.model_id,
            "model_config_checksum": self.config_checksum,
            "model_latency_ms": self.latency_ms,
        }


@dataclass(frozen=True)
class ModelActionProposal:
    kind: ProposalKind
    metadata: ProviderMetadata
    tool_name: str | None = None
    arguments: Mapping[str, Any] | None = None
    text: str | None = None

    @classmethod
    def action(
        cls,
        tool_name: str,
        arguments: Mapping[str, Any],
        metadata: ProviderMetadata,
    ) -> "ModelActionProposal":
        return cls(
            ProposalKind.ACTION,
            metadata,
            tool_name=tool_name,
            arguments=MappingProxyType(dict(arguments)),
        )

    @classmethod
    def clarification(cls, text: str, metadata: ProviderMetadata) -> "ModelActionProposal":
        return cls(ProposalKind.CLARIFICATION, metadata, text=text)

    @classmethod
    def response(cls, text: str, metadata: ProviderMetadata) -> "ModelActionProposal":
        return cls(ProposalKind.RESPONSE, metadata, text=text)
