from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from vivi_agent import build_runtime
from vivi_agent.model_providers import (
    ModelProviderConfig,
    RateLimitedTransport,
    RetryableTransportError,
)
from vivi_agent.runtime import build_agent_runtime
from vivi_agent.orchestrator import TurnStatus


class FakeGeminiTransport:
    def __init__(self):
        self.calls = 0

    def __call__(self, payload, timeout_seconds):
        self.calls += 1
        text = payload["contents"][-1]["parts"][0]["text"].lower()
        if "hồ gươm" in text:
            name = "control_vehicle_capability"
            args = {"action": "set", "target": "set_navigation_destination", "value": "Hồ Gươm"}
        elif "tốc độ" in text:
            name = "query_vehicle_state"
            args = {"action": "get", "target": "current_speed"}
        else:
            name = "control_access"
            args = {"action": "open", "target": "driver_door"}
        return {
            "candidates": [
                {"content": {"parts": [{"functionCall": {"name": name, "args": args}}]}}
            ]
        }


def make_runtime():
    base = build_runtime()
    transport = FakeGeminiTransport()
    runtime = build_agent_runtime(
        config=ModelProviderConfig(
            provider="gemini",
            priority=("gemini",),
            gemini_model="test-model",
            gemini_api_key="test-key",
        ),
        manifest=base.intent_manifest,
        registry=base.tool_registry,
        mapper=base.tool_mapper,
        transports={"gemini": transport},
    )
    return runtime, transport


def test_public_handle_text_uses_deterministic_fast_path_and_changes_state():
    runtime, transport = make_runtime()
    before = runtime.state_machine.snapshot().state_version

    result = runtime.handle_text("Mở cửa ghế lái", request_id="request-open")

    assert result.status is TurnStatus.COMPLETED
    assert result.execution_id
    assert runtime.state_machine.snapshot().state_version == before + 1
    assert transport.calls == 0


def test_simple_polite_paraphrase_uses_deterministic_fast_path():
    runtime, transport = make_runtime()

    result = runtime.handle_text("Làm ơn mở cửa ghế lái giúp tôi", request_id="polite-open")

    assert result.status is TurnStatus.COMPLETED
    assert result.execution_id
    assert transport.calls == 0


def test_query_uses_vehicle_state_without_mutating_it():
    runtime, _ = make_runtime()
    before = runtime.state_machine.snapshot().state_version

    result = runtime.handle_text("Tốc độ hiện tại là bao nhiêu?", request_id="request-speed")

    assert result.status is TurnStatus.COMPLETED
    assert "0" in result.message
    assert runtime.state_machine.snapshot().state_version == before


def test_candidate_action_executes_through_registered_handler():
    runtime, transport = make_runtime()
    before = runtime.state_machine.snapshot().state_version

    result = runtime.handle_text("Bật hệ thống điều hòa.", request_id="candidate-ac")

    assert result.status is TurnStatus.COMPLETED
    assert result.execution_id
    # Command-only capability has no modeled telemetry field. The handler
    # dispatches a typed one-shot command and leaves state unchanged until the
    # vehicle adapter reports telemetry back.
    assert runtime.state_machine.snapshot().state_version == before
    assert "candidate_capability_turnon_ac_commanded" in result.message
    assert transport.calls == 0


def test_parameterized_candidate_executes_model_selected_free_text_value():
    runtime, transport = make_runtime()

    result = runtime.handle_text(
        "Dẫn tôi tới Hồ Gươm theo đường nhanh nhất", request_id="candidate-navigation"
    )

    assert result.status is TurnStatus.COMPLETED
    assert result.execution_id
    assert runtime.state_machine.snapshot().state_version == 0
    assert "candidate_capability_set_navigation_destination_commanded" in result.message
    assert transport.calls == 1


def test_duplicate_request_id_returns_cached_result_without_second_model_or_action_call():
    runtime, transport = make_runtime()

    first = runtime.handle_text("Xin vui lòng mở cửa phía người lái", request_id="same-request")
    second = runtime.handle_text("Xin vui lòng mở cửa phía người lái", request_id="same-request")

    assert first is second
    assert transport.calls == 1
    assert runtime.state_machine.snapshot().state_version == 1


def test_runtime_readiness_reports_model_handlers_queries_and_state():
    runtime, _ = make_runtime()

    readiness = runtime.readiness()

    assert readiness.ready
    assert readiness.provider == "gemini"
    assert readiness.action_handlers > 0
    assert readiness.query_handlers == 10
    assert readiness.refusal_handlers == 1
    assert readiness.state_version == 0


def test_explicit_refusal_returns_response_without_state_mutation_or_model_call():
    runtime, transport = make_runtime()

    result = runtime.handle_text("Tắt cân bằng điện tử", request_id="refusal-request")

    assert result.status is TurnStatus.COMPLETED
    assert "không thể tắt" in result.message.lower()
    assert runtime.state_machine.snapshot().state_version == 0
    assert transport.calls == 0


def test_concurrent_duplicate_request_executes_model_and_action_once():
    runtime, transport = make_runtime()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: runtime.handle_text(
                    "Xin vui lòng mở cửa phía người lái", request_id="concurrent-request"
                ),
                range(2),
            )
        )

    assert results[0] is results[1]
    assert transport.calls == 1
    assert runtime.state_machine.snapshot().state_version == 1


def test_rate_limited_transport_retries_one_pre_proposal_transient_failure():
    calls = []

    def flaky(payload, timeout_seconds):
        calls.append(payload)
        if len(calls) == 1:
            raise RetryableTransportError("temporary")
        return {"ok": True}

    transport = RateLimitedTransport(flaky, requests_per_minute=1_000_000_000)

    assert transport({"request": 1}, 1.0) == {"ok": True}
    assert len(calls) == 2
