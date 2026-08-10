from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor

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
from src.vivi_agent.workflows import load_default_workflows


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
OPENAI_WORKFLOW = {
    "choices": [{"message": {"tool_calls": [{"function": {
        "name": "run_predefined_workflow",
        "arguments": '{"workflow_id":"park_and_secure"}',
    }}]}}]
}
GEMINI_WORKFLOW = {
    "candidates": [{"content": {"parts": [{"functionCall": {
        "name": "run_predefined_workflow",
        "args": {"workflow_id": "park_and_secure"},
    }}]}}]
}


class AdapterTests(unittest.TestCase):
    def adapter(self, cls, transport, *, workflows=False):
        return cls(
            model_id="configured-model",
            api_key="backend-secret",
            registry=RUNTIME_TOOL_REGISTRY,
            transport=transport,
            config_checksum="sha256:test",
            clock=iter((1.0, 1.025)).__next__,
            workflow_registry=(
                load_default_workflows(RUNTIME_TOOL_REGISTRY) if workflows else None
            ),
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

    def test_openai_cached_schema_is_isolated_from_transport_mutation(self) -> None:
        adapter = self.adapter(OpenAIAdapter, SequenceTransport())

        first = adapter._proposal_payload([{"role": "user", "content": "Mở cửa lái"}])
        expected_name = first["tools"][0]["function"]["name"]
        first["tools"][0]["function"]["name"] = "mutated"
        second = adapter._proposal_payload([{"role": "user", "content": "Mở cửa lái"}])

        self.assertEqual(second["tools"][0]["function"]["name"], expected_name)

    def test_gemini_uses_native_declarations_and_same_contract(self) -> None:
        transport = SequenceTransport(GEMINI_ACTION)
        result = self.adapter(GeminiAdapter, transport).propose_tool(
            [{"role": "system", "content": "Select at most one tool"}, {"role": "user", "content": "Mở cửa"}]
        )
        self.assertEqual(result.kind, ProposalKind.ACTION)
        self.assertEqual(result.tool_name, "control_access")
        payload = transport.calls[0][0]
        declarations = payload["tools"][0]["functionDeclarations"]
        self.assertEqual(len(declarations), 10)
        self.assertEqual(payload["toolConfig"]["functionCallingConfig"]["mode"], "AUTO")
        self.assertIn("systemInstruction", payload)

        # Regression guard for the confirmed real-API bug (see
        # evals/eval-01/results/gemini_schema_bug_evidence.json): Gemini's
        # generateContent parser 400s on oneOf/const/additionalProperties and,
        # even with those stripped, ignores properties/required nested inside
        # oneOf branches. Every declaration sent to Gemini must be flat.
        for declaration in declarations:
            parameters = declaration["parameters"]
            self.assertEqual(parameters["type"], "object")
            self.assertNotIn("oneOf", parameters)
            self.assertNotIn("additionalProperties", parameters)
            self.assertIn("properties", parameters)
            self.assertIn("required", parameters)
            for prop in parameters["properties"].values():
                self.assertNotIn("const", prop)

        access = next(item for item in declarations if item["name"] == "control_access")["parameters"]
        self.assertEqual(set(access["properties"]["action"]["enum"]), {"open", "lock", "unlock"})
        self.assertIn("driver_door", access["properties"]["target"]["enum"])
        self.assertIn("all_doors", access["properties"]["target"]["enum"])
        self.assertNotIn("value", access["properties"])
        self.assertEqual(set(access["required"]), {"action", "target"})

        # "value" is only required for some control_cabin/control_transmission
        # signatures, so it must stay out of "required" at the schema level;
        # ToolRegistry.validate_call still enforces it per-action.
        drive = next(item for item in declarations if item["name"] == "set_drive_mode")["parameters"]
        self.assertEqual(set(drive["properties"]["value"]["enum"]), {"eco", "normal", "sport"})
        self.assertNotIn("value", drive["required"])

    def test_gemini_cached_schema_is_isolated_from_transport_mutation(self) -> None:
        adapter = self.adapter(GeminiAdapter, SequenceTransport())

        first = adapter._proposal_payload([{"role": "user", "content": "Mở cửa lái"}])
        declarations = first["tools"][0]["functionDeclarations"]
        expected_name = declarations[0]["name"]
        declarations[0]["name"] = "mutated"
        second = adapter._proposal_payload([{"role": "user", "content": "Mở cửa lái"}])

        declarations = second["tools"][0]["functionDeclarations"]
        self.assertEqual(declarations[0]["name"], expected_name)

    def test_gemini_flat_schema_lets_model_fill_arguments_in_one_pass(self) -> None:
        # Reproduces finding_2 from evals/eval-01/results/gemini_schema_bug_evidence.json:
        # with the old oneOf-nested schema Gemini returned the right tool name but
        # empty args. The flat schema's args come straight through unmodified, so a
        # non-empty args dict here would have masked the original bug.
        transport = SequenceTransport(GEMINI_ACTION)
        result = self.adapter(GeminiAdapter, transport).propose_tool(
            [{"role": "user", "content": "Mở cửa lái"}]
        )
        self.assertEqual(dict(result.arguments or {}), {"action": "open", "target": "driver_door"})

    def test_both_providers_normalize_the_same_closed_workflow_selection(self) -> None:
        for adapter_type, raw in (
            (OpenAIAdapter, OPENAI_WORKFLOW),
            (GeminiAdapter, GEMINI_WORKFLOW),
        ):
            adapter = self.adapter(adapter_type, SequenceTransport(raw), workflows=True)
            result = adapter.propose_tool(
                [{"role": "user", "content": "Park and secure the vehicle"}]
            )
            self.assertEqual(result.tool_name, "run_predefined_workflow")
            self.assertEqual(dict(result.arguments or {}), {"workflow_id": "park_and_secure"})
            payload = adapter._transport.calls[0][0]
            if adapter_type is OpenAIAdapter:
                workflow = next(
                    tool["function"] for tool in payload["tools"]
                    if tool["function"]["name"] == "run_predefined_workflow"
                )
                self.assertTrue(workflow["strict"])
            else:
                workflow = next(
                    item for item in payload["tools"][0]["functionDeclarations"]
                    if item["name"] == "run_predefined_workflow"
                )
                self.assertNotIn("additionalProperties", workflow["parameters"])

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
    def test_router_snapshots_transport_bindings_for_cache_consistency(self) -> None:
        original = SequenceTransport(OPENAI_ACTION)
        replacement = SequenceTransport(OPENAI_ACTION)
        transports = {"openai": original}
        router = ModelProviderRouter(
            ModelProviderConfig(openai_api_key="key"),
            RUNTIME_TOOL_REGISTRY,
            transports,
        )

        transports["openai"] = replacement
        router.propose_tool([{"role": "user", "content": "open"}])

        self.assertEqual(len(original.calls), 1)
        self.assertEqual(len(replacement.calls), 0)

    def test_explicit_transport_replacement_invalidates_cached_adapter(self) -> None:
        original = SequenceTransport(OPENAI_ACTION)
        replacement = SequenceTransport(OPENAI_ACTION)
        router = ModelProviderRouter(
            ModelProviderConfig(openai_api_key="key"),
            RUNTIME_TOOL_REGISTRY,
            {"openai": original},
        )
        original_adapter = router._adapter("openai")

        router.replace_transport("openai", replacement)
        replacement_adapter = router._adapter("openai")
        router.propose_tool([{"role": "user", "content": "open"}])

        self.assertIsNot(original_adapter, replacement_adapter)
        self.assertEqual(len(original.calls), 0)
        self.assertEqual(len(replacement.calls), 1)
        self.assertIs(router.transports["openai"], replacement)

    def test_transport_replacement_rejects_invalid_binding(self) -> None:
        router = ModelProviderRouter(
            ModelProviderConfig(openai_api_key="key"),
            RUNTIME_TOOL_REGISTRY,
            {"openai": SequenceTransport(OPENAI_ACTION)},
        )
        with self.assertRaises(ModelProviderError) as raised:
            router.replace_transport("other", SequenceTransport(OPENAI_ACTION))
        self.assertEqual(raised.exception.code, ModelErrorCode.INVALID_CONFIG)

        with self.assertRaises(ModelProviderError) as raised:
            router.replace_transport("openai", None)
        self.assertEqual(raised.exception.code, ModelErrorCode.INVALID_CONFIG)

    def test_router_reuses_one_adapter_per_provider_across_threads(self) -> None:
        created = []

        def factory(**kwargs):
            kwargs.pop("provider")
            adapter = OpenAIAdapter(**kwargs)
            created.append(adapter)
            return adapter

        router = ModelProviderRouter(
            ModelProviderConfig(openai_api_key="key"),
            RUNTIME_TOOL_REGISTRY,
            {"openai": SequenceTransport(*([OPENAI_ACTION] * 20))},
            adapter_factory=factory,
        )

        with ThreadPoolExecutor(max_workers=8) as pool:
            adapters = list(pool.map(lambda _: router._adapter("openai"), range(20)))

        self.assertEqual(len(created), 1)
        self.assertTrue(all(adapter is created[0] for adapter in adapters))

    def test_router_opt_in_exposes_and_returns_a_workflow_selection(self) -> None:
        transport = SequenceTransport(OPENAI_WORKFLOW)
        router = ModelProviderRouter(
            ModelProviderConfig(openai_api_key="key"),
            RUNTIME_TOOL_REGISTRY,
            {"openai": transport},
            workflow_registry=load_default_workflows(RUNTIME_TOOL_REGISTRY),
        )
        result = router.propose_tool([{"role": "user", "content": "Park and secure"}])
        self.assertEqual(result.tool_name, "run_predefined_workflow")
        self.assertEqual(dict(result.arguments or {}), {"workflow_id": "park_and_secure"})
        names = {
            tool["function"]["name"] for tool in transport.calls[0][0]["tools"]
        }
        self.assertIn("run_predefined_workflow", names)

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
