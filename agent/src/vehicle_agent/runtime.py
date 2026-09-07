"""Standalone production composition for the Aegis text agent."""

from __future__ import annotations

import re
import threading
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Mapping

from .behaviors.catalog import ACTION_BEHAVIOR_CONFIGS
from .behaviors.refusal import REFUSAL_CATALOG
from .catalog import IntentManifest
from .model_providers import (
    GeminiRestTransport,
    ModelProviderConfig,
    ModelProviderRouter,
    ModelActionProposal,
    ProviderMetadata,
    RateLimitedTransport,
    OpenAIRestTransport,
)
from .model_providers.adapters import ProviderTransport
from .orchestrator import AgentTurnRequest, TextAgent, TurnResult
from .queries import build_default_query_registry
from .tools.mapping import ToolMapper
from .tools.registry import ToolRegistry
from .vehicle.execution import AgentToolExecutor, HandlerRegistry, register_behavior_configs
from .vehicle.state import VehicleStateMachine


@dataclass(frozen=True)
class AgentReadiness:
    ready: bool
    provider: str | None
    action_handlers: int
    query_handlers: int
    refusal_handlers: int
    state_version: int
    reason: str | None = None


class DeterministicFirstRouter:
    """Resolve exact reviewed sample utterances before using a model provider."""

    def __init__(self, fallback: ModelProviderRouter, routes: Mapping[str, ModelActionProposal]) -> None:
        self._fallback = fallback
        self._routes = dict(routes)

    @staticmethod
    def normalize(text: str) -> str:
        normalized = text.strip().casefold()
        normalized = normalized.replace("bên tài xế", "ghế lái").replace("bên lái", "ghế lái")
        normalized = re.sub(r"[^0-9a-zà-ỹđ]+", " ", normalized)
        stopwords = {
            "làm", "ơn", "giúp", "tôi", "nhé", "cho", "biết", "hiện", "lên",
            "xe", "lái", "phần", "trăm",
        }
        return " ".join(token for token in normalized.split() if token not in stopwords)

    def readiness(self):
        return self._fallback.readiness()

    def propose_tool(self, messages, turn=None):
        latest = next(
            (item["content"] for item in reversed(messages) if item.get("role") == "user"),
            "",
        )
        proposal = self._routes.get(self.normalize(latest))
        if proposal is None:
            return self._fallback.propose_tool(messages, turn)
        if turn is not None:
            turn.record_proposal(proposal)
        return proposal

    def compose_response(self, grounded_facts, turn):
        return self._fallback.compose_response(grounded_facts, turn)


class AgentRuntime:
    """Single public API for text -> tool -> verified simulated vehicle result."""

    def __init__(
        self,
        *,
        agent: TextAgent,
        state_machine: VehicleStateMachine,
        model_router,
        action_handler_count: int,
        query_handler_count: int,
        refusal_handler_count: int,
        max_history_messages: int = 12,
        max_cached_requests: int = 1024,
    ) -> None:
        if max_history_messages < 0 or max_cached_requests < 1:
            raise ValueError("runtime bounds must be positive")
        self._agent = agent
        self.state_machine = state_machine
        self.model_router = model_router
        self._action_handler_count = action_handler_count
        self._query_handler_count = query_handler_count
        self._refusal_handler_count = refusal_handler_count
        self._max_history_messages = max_history_messages
        self._max_cached_requests = max_cached_requests
        self._history: dict[str, list[Mapping[str, str]]] = {}
        self._results: OrderedDict[tuple[str, str], TurnResult] = OrderedDict()
        self._request_locks: dict[tuple[str, str], tuple[threading.Lock, int]] = {}
        self._session_locks: dict[str, tuple[threading.Lock, int]] = {}
        self._lock = threading.Lock()

    def handle_text(
        self,
        text: str,
        *,
        session_id: str = "default",
        request_id: str | None = None,
        turn_id: str | None = None,
        intent_hint: str | None = None,
    ) -> TurnResult:
        request_id = request_id or f"request-{uuid.uuid4().hex}"
        turn_id = turn_id or f"turn-{uuid.uuid4().hex}"
        key = (session_id, request_id)
        with self._request_lock(key):
            with self._session_lock(session_id):
                return self._handle_once(text, session_id, request_id, turn_id, intent_hint)

    def _handle_once(
        self,
        text: str,
        session_id: str,
        request_id: str,
        turn_id: str,
        intent_hint: str | None,
    ) -> TurnResult:
        key = (session_id, request_id)
        with self._lock:
            cached = self._results.get(key)
            if cached is not None:
                self._results.move_to_end(key)
                return cached
            history = tuple(self._history.get(session_id, ()))

        snapshot = self.state_machine.snapshot()
        result = self._agent.handle_text(
            AgentTurnRequest(
                session_id=session_id,
                turn_id=turn_id,
                request_id=request_id,
                message=text,
                intent_hint=intent_hint,
                state_version=snapshot.state_version,
                trusted_state=snapshot.to_authorization_snapshot(),
                messages=history,
            )
        )
        with self._lock:
            self._results[key] = result
            self._results.move_to_end(key)
            while len(self._results) > self._max_cached_requests:
                self._results.popitem(last=False)
            if self._max_history_messages:
                messages = [*history, {"role": "user", "content": text}]
                if result.message:
                    messages.append({"role": "assistant", "content": result.message})
                self._history[session_id] = messages[-self._max_history_messages :]
        return result

    def reset_session(self, session_id: str) -> None:
        with self._lock:
            self._history.pop(session_id, None)
            self._results = OrderedDict(
                (key, value) for key, value in self._results.items() if key[0] != session_id
            )

    @contextmanager
    def _request_lock(self, key: tuple[str, str]):
        with self._lock:
            lock, users = self._request_locks.get(key, (threading.Lock(), 0))
            self._request_locks[key] = (lock, users + 1)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            with self._lock:
                current_lock, users = self._request_locks[key]
                if users == 1:
                    del self._request_locks[key]
                else:
                    self._request_locks[key] = (current_lock, users - 1)

    @contextmanager
    def _session_lock(self, session_id: str):
        with self._lock:
            lock, users = self._session_locks.get(session_id, (threading.Lock(), 0))
            self._session_locks[session_id] = (lock, users + 1)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            with self._lock:
                current_lock, users = self._session_locks[session_id]
                if users == 1:
                    del self._session_locks[session_id]
                else:
                    self._session_locks[session_id] = (current_lock, users - 1)

    def readiness(self) -> AgentReadiness:
        provider = self.model_router.readiness()
        return AgentReadiness(
            ready=(
                provider.ready
                and self._action_handler_count > 0
                and self._query_handler_count > 0
                and self._refusal_handler_count > 0
            ),
            provider=provider.selected_provider,
            action_handlers=self._action_handler_count,
            query_handlers=self._query_handler_count,
            refusal_handlers=self._refusal_handler_count,
            state_version=self.state_machine.snapshot().state_version,
            reason=provider.reason,
        )


def build_agent_runtime(
    *,
    config: ModelProviderConfig,
    manifest: IntentManifest,
    registry: ToolRegistry,
    mapper: ToolMapper,
    state_machine: VehicleStateMachine | None = None,
    transports: Mapping[str, ProviderTransport] | None = None,
    max_requests_per_minute: float = 12.0,
) -> AgentRuntime:
    """Build a complete standalone Agent from validated configuration."""

    machine = state_machine or VehicleStateMachine()
    provider_transports: dict[str, ProviderTransport] = dict(transports or {})
    if config.openai_api_key and "openai" not in provider_transports:
        provider_transports["openai"] = OpenAIRestTransport(config.openai_api_key)
    if config.gemini_api_key and "gemini" not in provider_transports:
        provider_transports["gemini"] = GeminiRestTransport(config.gemini_api_key)
    provider_transports = {
        name: RateLimitedTransport(transport, max_requests_per_minute)
        for name, transport in provider_transports.items()
    }
    provider_router = ModelProviderRouter(config, registry, provider_transports)

    rules_by_intent = {}
    for rule in mapper.rules:
        rules_by_intent.setdefault(rule.intent, []).append(rule)
    deterministic_routes = {}
    ambiguous_routes = set()
    metadata = ProviderMetadata("deterministic", "manifest-samples", manifest.checksum, 0)
    for definition in manifest.intents:
        rules = rules_by_intent.get(definition.intent, ())
        if len(rules) != 1:
            continue
        rule = rules[0]
        # A wildcard marks a required free-text value. Never turn the catalog
        # sample into an executable proposal carrying the literal placeholder;
        # the model must extract a real value or ask for clarification.
        if rule.value == "*":
            continue
        arguments = {"action": rule.action, "target": rule.target}
        if rule.value is not None:
            arguments["value"] = rule.value
        proposal = ModelActionProposal.action(rule.tool_name, arguments, metadata)
        for sample in definition.sample_utterances:
            normalized = DeterministicFirstRouter.normalize(sample)
            if normalized in ambiguous_routes:
                continue
            existing = deterministic_routes.get(normalized)
            if existing is not None and existing != proposal:
                deterministic_routes.pop(normalized)
                ambiguous_routes.add(normalized)
            else:
                deterministic_routes[normalized] = proposal
    model_router = DeterministicFirstRouter(provider_router, deterministic_routes)

    handler_registry = HandlerRegistry()
    register_behavior_configs(handler_registry, ACTION_BEHAVIOR_CONFIGS, machine)
    action_intents = {item.intent_id for item in ACTION_BEHAVIOR_CONFIGS}

    query_registry = build_default_query_registry()
    query_intents = query_registry.registered_intents()
    for intent in query_intents:
        def query_handler(proposal, query_intent=intent):
            query_proposal = dict(proposal)
            query_proposal["intent"] = query_intent
            answer = query_registry.execute(query_proposal, machine.snapshot())
            return {
                "message": answer.response_text,
                "state_version": machine.snapshot().state_version,
                "facts": dict(answer.facts),
            }

        handler_registry.register(intent, query_handler)

    refusal_intents = {item.intent_id for item in REFUSAL_CATALOG}
    for refusal in REFUSAL_CATALOG:
        def refusal_handler(proposal, entry=refusal):
            return {
                "message": entry.response_template,
                "state_version": machine.snapshot().state_version,
                "facts": {"refusal_reason": entry.reason},
            }

        handler_registry.register(refusal.intent_id, refusal_handler)

    missing = {
        definition.intent
        for definition in manifest.intents
        if definition.kind in {"action", "query"}
    } - action_intents - query_intents - refusal_intents
    if missing:
        raise RuntimeError(f"Agent handler coverage is incomplete: {sorted(missing)!r}")

    agent = TextAgent(
        model_router=model_router,
        mapper=mapper,
        executor=AgentToolExecutor(
            handler_registry,
            state_version_reader=lambda: machine.snapshot().state_version,
            mutating_intents=frozenset(action_intents),
        ),
    )
    return AgentRuntime(
        agent=agent,
        state_machine=machine,
        model_router=model_router,
        action_handler_count=len(action_intents),
        query_handler_count=len(query_intents),
        refusal_handler_count=len(refusal_intents),
    )
