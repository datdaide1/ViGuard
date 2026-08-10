"""Environment configuration, readiness, selection, and bounded failover."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ..tools.registry import ToolRegistry
from ..workflows import WorkflowRegistry
from .adapters import GeminiAdapter, ModelProviderAdapter, OpenAIAdapter, ProviderTransport
from .contracts import ModelActionProposal, ModelErrorCode, ModelProviderError

SUPPORTED_PROVIDERS = ("openai", "gemini")


@dataclass(frozen=True)
class ModelProviderConfig:
    provider: str = "auto"
    priority: tuple[str, ...] = SUPPORTED_PROVIDERS
    openai_model: str = "gpt-5-mini"
    gemini_model: str = "gemini-3.6-flash"
    timeout_seconds: float = 10.0
    openai_api_key: str = ""
    gemini_api_key: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ModelProviderConfig":
        source = os.environ if env is None else env
        priority = tuple(
            item.strip().lower()
            for item in source.get("AGENT_MODEL_PROVIDER_PRIORITY", "openai,gemini").split(",")
            if item.strip()
        )
        try:
            config = cls(
                provider=source.get("AGENT_MODEL_PROVIDER", "auto").strip().lower(),
                priority=priority,
                openai_model=source.get("OPENAI_MODEL_ID", "gpt-5-mini").strip(),
                gemini_model=source.get("GEMINI_MODEL_ID", "gemini-3.6-flash").strip(),
                timeout_seconds=float(source.get("AGENT_MODEL_TIMEOUT_SECONDS", "10")),
                openai_api_key=source.get("OPENAI_API_KEY", ""),
                gemini_api_key=source.get("GEMINI_API_KEY", ""),
            )
        except ValueError as exc:
            raise ModelProviderError(
                ModelErrorCode.INVALID_CONFIG, "AGENT_MODEL_TIMEOUT_SECONDS must be numeric"
            ) from exc
        config.validate()
        return config

    def validate(self) -> None:
        if self.provider not in {"auto", *SUPPORTED_PROVIDERS}:
            raise ModelProviderError(ModelErrorCode.INVALID_CONFIG, f"unsupported provider {self.provider!r}")
        if not self.priority or len(set(self.priority)) != len(self.priority):
            raise ModelProviderError(ModelErrorCode.INVALID_CONFIG, "priority must be non-empty and unique")
        if any(item not in SUPPORTED_PROVIDERS for item in self.priority):
            raise ModelProviderError(ModelErrorCode.INVALID_CONFIG, "priority contains unsupported provider")
        if not self.openai_model or not self.gemini_model or self.timeout_seconds <= 0:
            raise ModelProviderError(ModelErrorCode.INVALID_CONFIG, "model IDs and positive timeout are required")

    def key_for(self, provider: str) -> str:
        return self.openai_api_key if provider == "openai" else self.gemini_api_key

    def model_for(self, provider: str) -> str:
        return self.openai_model if provider == "openai" else self.gemini_model

    @property
    def checksum(self) -> str:
        safe = {
            "provider": self.provider,
            "priority": self.priority,
            "models": {"openai": self.openai_model, "gemini": self.gemini_model},
            "timeout_seconds": self.timeout_seconds,
        }
        encoded = json.dumps(safe, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ProviderReadiness:
    ready: bool
    selected_provider: str | None
    available_providers: tuple[str, ...]
    reason: str | None = None


@dataclass
class TurnBinding:
    provider: str | None = None
    valid_proposal_created: bool = False
    side_effect_started: bool = False

    @property
    def pinned(self) -> bool:
        return self.valid_proposal_created or self.side_effect_started

    def record_proposal(self, proposal: ModelActionProposal) -> None:
        self.provider = proposal.metadata.provider
        self.valid_proposal_created = True

    def start_side_effect(self) -> None:
        if not self.provider:
            raise ModelProviderError(ModelErrorCode.TURN_PINNED, "cannot start lifecycle before provider selection")
        self.side_effect_started = True


class ModelProviderRouter:
    def __init__(
        self,
        config: ModelProviderConfig,
        registry: ToolRegistry,
        transports: Mapping[str, ProviderTransport],
        *,
        adapter_factory: Callable[..., ModelProviderAdapter] | None = None,
        workflow_registry: WorkflowRegistry | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.registry = registry
        # Cache correctness requires the provider-to-transport binding to stay
        # stable for the router lifetime. Snapshot caller-owned mutable maps.
        self.transports = MappingProxyType(dict(transports))
        self._factory = adapter_factory
        self.workflow_registry = workflow_registry
        self._adapter_cache: dict[str, ModelProviderAdapter] = {}
        self._adapter_cache_lock = threading.Lock()

    def readiness(self) -> ProviderReadiness:
        order = self._candidate_names()
        available = tuple(name for name in order if self.config.key_for(name) and name in self.transports)
        if not available:
            return ProviderReadiness(
                False,
                None,
                (),
                "No configured model provider has both an API key and backend transport",
            )
        return ProviderReadiness(True, available[0], available)

    def propose_tool(
        self, messages: Sequence[Mapping[str, str]], turn: TurnBinding | None = None
    ) -> ModelActionProposal:
        binding = turn or TurnBinding()
        names = self._available_names()
        if binding.provider:
            if binding.provider not in names:
                raise ModelProviderError(
                    ModelErrorCode.TURN_PINNED,
                    f"turn provider {binding.provider!r} is unavailable",
                    provider=binding.provider,
                )
            names = [binding.provider]
        last_error: ModelProviderError | None = None
        for name in names[:2]:
            if binding.pinned and binding.provider != name:
                break
            try:
                result = self._adapter(name).propose_tool(messages)
                binding.record_proposal(result)
                return result
            except ModelProviderError as exc:
                last_error = exc
                if binding.pinned or not exc.retryable:
                    raise
        detail = "all configured providers failed before creating a valid proposal"
        if last_error:
            detail += f"; last_error={last_error.code.value}"
        raise ModelProviderError(ModelErrorCode.ALL_UNAVAILABLE, detail, retryable=False) from last_error

    def compose_response(self, grounded_facts: Mapping[str, Any], turn: TurnBinding) -> ModelActionProposal:
        if not turn.provider:
            raise ModelProviderError(ModelErrorCode.TURN_PINNED, "response requires a selected turn provider")
        result = self._adapter(turn.provider).compose_response(grounded_facts)
        if result.metadata.provider != turn.provider:
            raise ModelProviderError(ModelErrorCode.TURN_PINNED, "provider changed within turn")
        return result

    def _candidate_names(self) -> list[str]:
        return [self.config.provider] if self.config.provider != "auto" else list(self.config.priority)

    def _available_names(self) -> list[str]:
        readiness = self.readiness()
        if not readiness.ready:
            raise ModelProviderError(ModelErrorCode.NOT_READY, readiness.reason or "not ready")
        return list(readiness.available_providers)

    def _adapter(self, provider: str) -> ModelProviderAdapter:
        with self._adapter_cache_lock:
            adapter = self._adapter_cache.get(provider)
            if adapter is None:
                adapter = self._build_adapter(provider)
                self._adapter_cache[provider] = adapter
            return adapter

    def _build_adapter(self, provider: str) -> ModelProviderAdapter:
        """Construct one provider adapter from immutable router configuration."""
        kwargs = {
            "model_id": self.config.model_for(provider),
            "api_key": self.config.key_for(provider),
            "registry": self.registry,
            "transport": self.transports[provider],
            "config_checksum": self.config.checksum,
            "timeout_seconds": self.config.timeout_seconds,
        }
        if self.workflow_registry is not None:
            kwargs["workflow_registry"] = self.workflow_registry
        if self._factory:
            return self._factory(provider=provider, **kwargs)
        adapter_type = OpenAIAdapter if provider == "openai" else GeminiAdapter
        return adapter_type(**kwargs)
