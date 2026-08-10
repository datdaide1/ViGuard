"""OpenAI and Gemini serialization at the model trust boundary."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from ..tools.registry import ToolDefinition, ToolRegistry
from ..workflows import WorkflowRegistry
from .contracts import (
    ModelActionProposal,
    ModelErrorCode,
    ModelProviderError,
    ProviderMetadata,
)


class ProviderTransport(Protocol):
    """Backend-only HTTP/SDK seam; implementations must not log API keys."""

    def __call__(self, payload: Mapping[str, Any], timeout_seconds: float) -> Mapping[str, Any]: ...


class ModelProviderAdapter(ABC):
    MAX_CONTEXT_CHARS = 16_000
    MAX_OUTPUT_TOKENS = 512

    def __init__(
        self,
        *,
        model_id: str,
        api_key: str,
        registry: ToolRegistry,
        transport: ProviderTransport,
        config_checksum: str,
        timeout_seconds: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        workflow_registry: WorkflowRegistry | None = None,
    ) -> None:
        self.model_id = model_id
        self._api_key = api_key
        self.registry = registry
        self._transport = transport
        self.config_checksum = config_checksum
        self.timeout_seconds = timeout_seconds
        self._clock = clock
        self.workflow_registry = workflow_registry

    @property
    @abstractmethod
    def provider(self) -> str: ...

    def propose_tool(self, messages: Sequence[Mapping[str, str]]) -> ModelActionProposal:
        return self._invoke(self._proposal_payload(self._bounded_messages(messages)), proposal=True)

    def compose_response(self, grounded_facts: Mapping[str, Any]) -> ModelActionProposal:
        encoded = json.dumps(grounded_facts, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if len(encoded) > self.MAX_CONTEXT_CHARS:
            raise ModelProviderError(
                ModelErrorCode.INVALID_CONFIG, "grounded facts exceed context bound", provider=self.provider
            )
        return self._invoke(self._response_payload(encoded), proposal=False)

    def _bounded_messages(self, messages: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
        validated: list[dict[str, str]] = []
        for message in messages:
            role, content = message.get("role"), message.get("content")
            if role not in {"system", "user", "assistant"} or not isinstance(content, str):
                raise ModelProviderError(
                    ModelErrorCode.INVALID_CONFIG, "messages must contain valid role/content", provider=self.provider
                )
            validated.append({"role": role, "content": content})

        system_messages = [message for message in validated if message["role"] == "system"]
        history = [message for message in validated if message["role"] != "system"]
        mandatory_chars = sum(len(message["content"]) for message in system_messages)
        if mandatory_chars > self.MAX_CONTEXT_CHARS:
            raise ModelProviderError(
                ModelErrorCode.INVALID_CONFIG,
                "system instructions exceed context bound",
                provider=self.provider,
            )

        selected_history: list[dict[str, str]] = []
        total = mandatory_chars
        for message in reversed(history):
            if total + len(message["content"]) > self.MAX_CONTEXT_CHARS:
                if not selected_history:
                    raise ModelProviderError(
                        ModelErrorCode.INVALID_CONFIG,
                        "latest conversation message exceeds context bound",
                        provider=self.provider,
                    )
                break
            selected_history.append(message)
            total += len(message["content"])
        return system_messages + list(reversed(selected_history))

    def _invoke(self, payload: Mapping[str, Any], *, proposal: bool) -> ModelActionProposal:
        if not self._api_key:
            raise ModelProviderError(ModelErrorCode.NOT_READY, "API key is missing", provider=self.provider)
        started = self._clock()
        try:
            raw = self._transport(payload, self.timeout_seconds)
        except TimeoutError as exc:
            raise ModelProviderError(
                ModelErrorCode.TIMEOUT, "request timed out", provider=self.provider, retryable=True
            ) from exc
        except ModelProviderError:
            raise
        except Exception as exc:
            raise ModelProviderError(
                ModelErrorCode.API_ERROR,
                "provider request failed",
                provider=self.provider,
                retryable=True,
            ) from exc
        latency_ms = max(0, round((self._clock() - started) * 1000))
        metadata = ProviderMetadata(self.provider, self.model_id, self.config_checksum, latency_ms)
        try:
            return self._normalize(raw, metadata, proposal=proposal)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ModelProviderError(
                ModelErrorCode.MALFORMED_OUTPUT,
                "provider returned no valid single proposal",
                provider=self.provider,
                retryable=True,
            ) from exc

    @abstractmethod
    def _proposal_payload(self, messages: list[dict[str, str]]) -> Mapping[str, Any]: ...

    @abstractmethod
    def _response_payload(self, grounded_facts: str) -> Mapping[str, Any]: ...

    @abstractmethod
    def _normalize(
        self, raw: Mapping[str, Any], metadata: ProviderMetadata, *, proposal: bool
    ) -> ModelActionProposal: ...


class OpenAIAdapter(ModelProviderAdapter):
    @property
    def provider(self) -> str:
        return "openai"

    def _proposal_payload(self, messages: list[dict[str, str]]) -> Mapping[str, Any]:
        tools = [
            {
                "type": "function",
                "function": {**schema, "strict": True},
            }
            for schema in self.registry.model_tools()
        ]
        if self.workflow_registry is not None:
            tools.append(
                {
                    "type": "function",
                    "function": {**self.workflow_registry.model_schema(), "strict": True},
                }
            )
        return {
            "model": self.model_id,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "max_completion_tokens": self.MAX_OUTPUT_TOKENS,
        }

    def _response_payload(self, grounded_facts: str) -> Mapping[str, Any]:
        return {
            "model": self.model_id,
            "messages": [{"role": "user", "content": grounded_facts}],
            "tools": [],
            "max_completion_tokens": self.MAX_OUTPUT_TOKENS,
        }

    def _normalize(
        self, raw: Mapping[str, Any], metadata: ProviderMetadata, *, proposal: bool
    ) -> ModelActionProposal:
        choices = raw["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("one choice required")
        message = choices[0]["message"]
        calls = message.get("tool_calls", [])
        if calls:
            if not proposal or len(calls) != 1:
                raise ValueError("one tool call required")
            function = calls[0]["function"]
            arguments = function["arguments"]
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            if not isinstance(arguments, Mapping):
                raise TypeError("arguments must be an object")
            return ModelActionProposal.action(function["name"], arguments, metadata)
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("text is required")
        return (
            ModelActionProposal.clarification(content.strip(), metadata)
            if proposal
            else ModelActionProposal.response(content.strip(), metadata)
        )


class GeminiAdapter(ModelProviderAdapter):
    @property
    def provider(self) -> str:
        return "gemini"

    def _proposal_payload(self, messages: list[dict[str, str]]) -> Mapping[str, Any]:
        contents = [
            {"role": "model" if item["role"] == "assistant" else "user", "parts": [{"text": item["content"]}]}
            for item in messages
            if item["role"] != "system"
        ]
        system = "\n".join(item["content"] for item in messages if item["role"] == "system")
        payload: dict[str, Any] = {
            "model": self.model_id,
            "contents": contents,
            # ToolRegistry.model_tools() (used by OpenAIAdapter) emits a
            # oneOf/const/additionalProperties shape per tool. Gemini's
            # generateContent function-calling parser rejects that outright
            # (HTTP 400: Unknown name "const"/"additionalProperties") and, once
            # those two keywords are stripped, still does not read
            # properties/required nested inside oneOf branches — it returns the
            # right tool name with empty args. See
            # evals/eval-01/results/gemini_schema_bug_evidence.json. This is a
            # Gemini-specific parser quirk, not a general schema concern, so the
            # flattening lives here rather than on the registry; the real
            # per-(action, target, value) enforcement still happens post-hoc in
            # ToolRegistry.validate_call regardless of which schema shape a
            # provider was sent.
            "tools": [{"functionDeclarations": self._proposal_declarations()}],
            "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
            "generationConfig": {"maxOutputTokens": self.MAX_OUTPUT_TOKENS},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        return payload

    def _proposal_declarations(self) -> list[dict[str, Any]]:
        declarations = [self._flat_declaration(tool) for tool in self.registry.tools]
        if self.workflow_registry is not None:
            workflow = self.workflow_registry.model_schema()
            parameters = dict(workflow["parameters"])
            parameters.pop("additionalProperties", None)
            declarations.append({**workflow, "parameters": parameters})
        return declarations

    @staticmethod
    def _flat_declaration(tool: ToolDefinition) -> dict[str, Any]:
        """Flatten one tool's (action, target, value) signatures into the single
        flat {type: object, properties, required} shape Gemini's function-calling
        parser expects, instead of ToolDefinition.model_schema()'s oneOf-per-signature
        shape. action/target/value are exposed as the union of every signature's
        allowed values; "value" is left out of "required" because not every
        signature of a tool carries one (e.g. control_cabin mixes value-bearing
        and value-free actions) — ToolRegistry.validate_call still enforces it
        per-action and returns a clarification when it's missing.
        """
        actions = sorted({signature.action for signature in tool.signatures})
        targets = sorted({target for signature in tool.signatures for target in signature.targets})
        values = sorted({value for signature in tool.signatures for value in signature.values})
        properties: dict[str, Any] = {
            "action": {"type": "string", "enum": actions},
            "target": {"type": "string", "enum": targets},
        }
        if values:
            properties["value"] = {"type": "string", "enum": values}
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": ["action", "target"],
            },
        }

    def _response_payload(self, grounded_facts: str) -> Mapping[str, Any]:
        return {
            "model": self.model_id,
            "contents": [{"role": "user", "parts": [{"text": grounded_facts}]}],
            "generationConfig": {"maxOutputTokens": self.MAX_OUTPUT_TOKENS},
        }

    def _normalize(
        self, raw: Mapping[str, Any], metadata: ProviderMetadata, *, proposal: bool
    ) -> ModelActionProposal:
        candidates = raw["candidates"]
        if not isinstance(candidates, list) or len(candidates) != 1:
            raise ValueError("one candidate required")
        parts = candidates[0]["content"]["parts"]
        calls = [part["functionCall"] for part in parts if "functionCall" in part]
        texts = [part["text"] for part in parts if isinstance(part.get("text"), str) and part["text"].strip()]
        if calls:
            if not proposal or len(calls) != 1 or texts:
                raise ValueError("one tool call required")
            arguments = calls[0].get("args", {})
            if not isinstance(arguments, Mapping):
                raise TypeError("arguments must be an object")
            return ModelActionProposal.action(calls[0]["name"], arguments, metadata)
        if len(texts) != 1:
            raise ValueError("one text part required")
        return (
            ModelActionProposal.clarification(texts[0].strip(), metadata)
            if proposal
            else ModelActionProposal.response(texts[0].strip(), metadata)
        )
