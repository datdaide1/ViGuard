from __future__ import annotations

import unittest

from src.vivi_agent import RUNTIME_TOOL_REGISTRY
from src.vivi_agent.model_providers import (
    GeminiAdapter,
    ModelErrorCode,
    ModelProviderConfig,
    ModelProviderError,
    ModelProviderRouter,
    OpenAIAdapter,
    ProposalKind,
    TurnBinding,
)


class SequenceTransport:
    def __init__(self, *results: object) -> None:
        self.results = list(results)
        self.calls: list[tuple[object, float]] = []

    def __call__(self, payload: object, timeout_seconds: float):
        self.calls.append((payload, timeout_seconds))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


OPENAI_ACTION = {
    "choices": [
        {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "control_access",
                            "arguments": '{"action":"open","target":"driver_door"}',
                        }
                    }
                ]
            }
        }
    ]
}
GEMINI_ACTION = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "functionCall": {
                            "name": "control_access",
                            "args": {"action": "open", "target": "driver_door"},
                        }
                    }
                ]
            }
        }
    ]
}


class AdapterTests(unittest.TestCase):
    def adapter(self, cls, transport):
        return cls(
            model_id="configured-model",
            api_key="backend-secret",
            registry=RUNTIME_TOOL_REGISTRY,
            transport=transport,
            config_checksum="sha256:test",
            clock=iter((1.0, 1.025)).__next__,
        )

    def test_openai_uses_strict_single_function_call_and_normalizes(self) -> None:
        transport = SequenceTransport(OPENAI_ACTION)
        result = self.adapter(OpenAIAdapter, transport).propose_tool(
            [{"role": "user", "content": "Mở cửa lái"}]
        )
        self.assertEqual(result.kind, ProposalKind.ACTION)
        self.assertEqual(result.tool_name, "control_access")
        self.assertEqual(dict(result.arguments or {}), {"action": "open", "target": "driver_door"})
        metadata = result.metadata.to_event_metadata()
        self.assertEqual(metadata["model_provider"], "openai")
        self.assertEqual(metadata["model_id"], "configured-model")
        self.assertEqual(metadata["model_config_checksum"], "sha256:test")
        self.assertEqual(metadata["model_latency_ms"], 25)

        payload = transport.calls[0][0]
        self.assertFalse(payload["parallel_tool_calls"])
        self.assertEqual(payload["max_completion_tokens"], 512)
        self.assertNotIn("max_output_tokens", payload)
        self.assertTrue(all(tool["function"]["strict"] for tool in payload["tools"]))
        self.assertEqual(len(payload["tools"]), 10)
        self.assertNotIn("backend-secret", repr(payload))

    def test_gemini_uses_native_declarations_and_same_contract(self) -> None:
        transport = SequenceTransport(GEMINI_ACTION)
        result = self.adapter(GeminiAdapter, transport).propose_tool(
            [{"role": "system", "content": "Select at most one tool"}, {"role": "user", "content": "Mở cửa"}]
        )
        self.assertEqual(result.kind, ProposalKind.ACTION)
        self.assertEqual(result.tool_name, "control_access")
        payload = transport.calls[0][0]
        self.assertEqual(len(payload["tools"][0]["functionDeclarations"]), 10)
        self.assertEqual(payload["toolConfig"]["functionCallingConfig"]["mode"], "AUTO")
        self.assertIn("systemInstruction", payload)

    def test_text_is_clarification_for_proposal_and_response_for_composition(self) -> None:
        proposal_transport = SequenceTransport(
            {"choices": [{"message": {"content": "Bạn muốn mở cửa nào?"}}]}
        )
        proposal = self.adapter(OpenAIAdapter, proposal_transport).propose_tool(
            [{"role": "user", "content": "Mở cửa"}]
        )
        self.assertEqual(proposal.kind, ProposalKind.CLARIFICATION)

        response_transport = SequenceTransport(
            {"candidates": [{"content": {"parts": [{"text": "Đã mở cửa lái."}]}}]}
        )
        response = self.adapter(GeminiAdapter, response_transport).compose_response(
            {"outcome": "success"}
        )
        self.assertEqual(response.kind, ProposalKind.RESPONSE)

    def test_timeout_and_multiple_calls_fail_without_proposal(self) -> None:
        timeout = self.adapter(OpenAIAdapter, SequenceTransport(TimeoutError()))
        with self.assertRaises(ModelProviderError) as raised:
            timeout.propose_tool([{"role": "user", "content": "open"}])
        self.assertEqual(raised.exception.code, ModelErrorCode.TIMEOUT)

        malformed = {"choices": [{"message": {"tool_calls": OPENAI_ACTION["choices"][0]["message"]["tool_calls"] * 2}}]}
        with self.assertRaises(ModelProviderError) as raised:
            self.adapter(OpenAIAdapter, SequenceTransport(malformed)).propose_tool(
                [{"role": "user", "content": "open"}]
            )
        self.assertEqual(raised.exception.code, ModelErrorCode.MALFORMED_OUTPUT)

    def test_context_bound_preserves_system_instructions(self) -> None:
        transport = SequenceTransport(OPENAI_ACTION)
        adapter = self.adapter(OpenAIAdapter, transport)
        adapter.propose_tool(
            [
                {"role": "system", "content": "mandatory-safety-policy"},
                {"role": "user", "content": "old" * 5_000},
                {"role": "assistant", "content": "recent" * 500},
                {"role": "user", "content": "open driver door"},
            ]
        )
        sent = transport.calls[0][0]["messages"]
        self.assertEqual(sent[0], {"role": "system", "content": "mandatory-safety-policy"})
        self.assertNotIn({"role": "user", "content": "old" * 5_000}, sent)
        self.assertEqual(sent[-1], {"role": "user", "content": "open driver door"})

    def test_context_bound_rejects_unfit_mandatory_or_latest_message(self) -> None:
        adapter = self.adapter(OpenAIAdapter, SequenceTransport(OPENAI_ACTION))
        with self.assertRaises(ModelProviderError) as raised:
            adapter.propose_tool([{"role": "system", "content": "x" * 16_001}])
        self.assertEqual(raised.exception.code, ModelErrorCode.INVALID_CONFIG)

        adapter = self.adapter(OpenAIAdapter, SequenceTransport(OPENAI_ACTION))
        with self.assertRaises(ModelProviderError) as raised:
            adapter.propose_tool(
                [
                    {"role": "system", "content": "mandatory"},
                    {"role": "user", "content": "x" * 16_000},
                ]
            )
        self.assertEqual(raised.exception.code, ModelErrorCode.INVALID_CONFIG)

    def test_provider_exception_detail_never_echoes_transport_secret(self) -> None:
        leaked = "https://provider.invalid?key=super-secret"
        adapter = self.adapter(OpenAIAdapter, SequenceTransport(RuntimeError(leaked)))
        with self.assertRaises(ModelProviderError) as raised:
            adapter.propose_tool([{"role": "user", "content": "open"}])
        self.assertEqual(raised.exception.code, ModelErrorCode.API_ERROR)
        self.assertEqual(raised.exception.detail, "provider request failed")
        self.assertNotIn("super-secret", str(raised.exception))


class SelectionTests(unittest.TestCase):
    def test_environment_config_priority_models_and_secret_free_checksum(self) -> None:
        config = ModelProviderConfig.from_env(
            {
                "AGENT_MODEL_PROVIDER": "auto",
                "AGENT_MODEL_PROVIDER_PRIORITY": "gemini,openai",
                "OPENAI_API_KEY": "openai-secret",
                "GEMINI_API_KEY": "gemini-secret",
                "OPENAI_MODEL_ID": "openai-exact",
                "GEMINI_MODEL_ID": "gemini-exact",
            }
        )
        self.assertEqual(config.priority, ("gemini", "openai"))
        self.assertEqual(config.model_for("openai"), "openai-exact")
        self.assertNotIn("secret", config.checksum)

        with self.assertRaises(ModelProviderError) as raised:
            ModelProviderConfig.from_env({"AGENT_MODEL_TIMEOUT_SECONDS": "forever"})
        self.assertEqual(raised.exception.code, ModelErrorCode.INVALID_CONFIG)

    def test_auto_selects_first_available_and_no_key_fails_readiness(self) -> None:
        openai = SequenceTransport(OPENAI_ACTION)
        config = ModelProviderConfig(openai_api_key="key")
        router = ModelProviderRouter(config, RUNTIME_TOOL_REGISTRY, {"openai": openai})
        self.assertEqual(router.readiness().selected_provider, "openai")

        not_ready = ModelProviderRouter(
            ModelProviderConfig(), RUNTIME_TOOL_REGISTRY, {"openai": openai}
        )
        self.assertFalse(not_ready.readiness().ready)
        with self.assertRaises(ModelProviderError) as raised:
            not_ready.propose_tool([{"role": "user", "content": "open"}])
        self.assertEqual(raised.exception.code, ModelErrorCode.NOT_READY)

    def test_failover_happens_once_only_before_valid_proposal(self) -> None:
        openai = SequenceTransport(TimeoutError())
        gemini = SequenceTransport(GEMINI_ACTION)
        config = ModelProviderConfig(openai_api_key="one", gemini_api_key="two")
        router = ModelProviderRouter(
            config, RUNTIME_TOOL_REGISTRY, {"openai": openai, "gemini": gemini}
        )
        turn = TurnBinding()
        result = router.propose_tool([{"role": "user", "content": "open"}], turn)
        self.assertEqual(result.metadata.provider, "gemini")
        self.assertEqual(turn.provider, "gemini")
        self.assertTrue(turn.pinned)
        self.assertEqual(len(openai.calls), 1)
        self.assertEqual(len(gemini.calls), 1)

    def test_non_retryable_error_stops_failover_and_leaves_turn_unpinned(self) -> None:
        openai = SequenceTransport(
            ModelProviderError(
                ModelErrorCode.INVALID_CONFIG,
                "provider configuration is invalid",
                provider="openai",
                retryable=False,
            )
        )
        gemini = SequenceTransport(GEMINI_ACTION)
        router = ModelProviderRouter(
            ModelProviderConfig(openai_api_key="one", gemini_api_key="two"),
            RUNTIME_TOOL_REGISTRY,
            {"openai": openai, "gemini": gemini},
        )
        turn = TurnBinding()

        with self.assertRaises(ModelProviderError) as raised:
            router.propose_tool([{"role": "user", "content": "open"}], turn)

        self.assertEqual(raised.exception.code, ModelErrorCode.INVALID_CONFIG)
        self.assertEqual(len(openai.calls), 1)
        self.assertEqual(len(gemini.calls), 0)
        self.assertIsNone(turn.provider)
        self.assertFalse(turn.pinned)

    def test_all_unavailable_reports_last_error_and_leaves_turn_unpinned(self) -> None:
        openai = SequenceTransport(TimeoutError())
        gemini = SequenceTransport(TimeoutError())
        router = ModelProviderRouter(
            ModelProviderConfig(openai_api_key="one", gemini_api_key="two"),
            RUNTIME_TOOL_REGISTRY,
            {"openai": openai, "gemini": gemini},
        )
        turn = TurnBinding()

        with self.assertRaises(ModelProviderError) as raised:
            router.propose_tool([{"role": "user", "content": "open"}], turn)

        self.assertEqual(raised.exception.code, ModelErrorCode.ALL_UNAVAILABLE)
        self.assertIn("last_error=MODEL_PROVIDER_TIMEOUT", raised.exception.detail)
        self.assertEqual(len(openai.calls), 1)
        self.assertEqual(len(gemini.calls), 1)
        self.assertIsNone(turn.provider)
        self.assertFalse(turn.pinned)

    def test_pinned_turn_never_fails_over_during_response(self) -> None:
        openai = SequenceTransport(
            OPENAI_ACTION,
            TimeoutError(),
        )
        gemini = SequenceTransport(GEMINI_ACTION)
        router = ModelProviderRouter(
            ModelProviderConfig(openai_api_key="one", gemini_api_key="two"),
            RUNTIME_TOOL_REGISTRY,
            {"openai": openai, "gemini": gemini},
        )
        turn = TurnBinding()
        router.propose_tool([{"role": "user", "content": "open"}], turn)
        turn.start_side_effect()
        with self.assertRaises(ModelProviderError) as raised:
            router.compose_response({"outcome": "success"}, turn)
        self.assertEqual(raised.exception.provider, "openai")
        self.assertEqual(len(gemini.calls), 0)


if __name__ == "__main__":
    unittest.main()
