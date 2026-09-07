"""EVAL-01 — harness-correctness proof via a deterministic FakeTransport.

Proves ``EvalRunner`` correctly drives a real ``ModelProviderAdapter``
(``GeminiAdapter``/``OpenAIAdapter``) end-to-end — payload construction,
response normalization, error handling, latency capture, rate-limit pacing
— entirely offline. This is the DI seam MOD-01's own README calls out
("permits deterministic offline tests"): the exact same ``EvalRunner`` code
drives a live transport in ``run_live_eval.py`` and this ``FakeTransport``
here.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Mapping

_EVAL01_DIR = Path(__file__).resolve().parents[3] / "evals" / "eval-01"
if str(_EVAL01_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL01_DIR))

from dataset import DatasetItem, ExpectedOutcome, ToolCall  # noqa: E402
from runner import EvalRunner  # noqa: E402
from scoring import aggregate_metrics, score_outcome  # noqa: E402

from vehicle_agent.model_providers import GeminiAdapter, OpenAIAdapter  # noqa: E402
from vehicle_agent.tools.registry import load_registry  # noqa: E402


class FakeTransport:
    """Deterministic, offline ``ProviderTransport`` — scripted per call."""

    def __init__(self, responses: list[Mapping[str, Any] | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[Mapping[str, Any]] = []
        self.timeouts: list[float] = []

    def __call__(self, payload: Mapping[str, Any], timeout_seconds: float) -> Mapping[str, Any]:
        self.calls.append(payload)
        self.timeouts.append(timeout_seconds)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _openai_tool_call_response(name: str, arguments: dict) -> dict:
    import json

    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": name, "arguments": json.dumps(arguments)}}
                    ]
                }
            }
        ]
    }


def _openai_text_response(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


class Eval01RunnerFakeTransportTests(unittest.TestCase):
    def _make_adapter(self, transport: FakeTransport) -> OpenAIAdapter:
        return OpenAIAdapter(
            model_id="gpt-5-mini",
            api_key="fake-key",
            registry=load_registry(),
            transport=transport,
            config_checksum="sha256:" + "0" * 64,
            timeout_seconds=5.0,
        )

    def _item(self, item_id: str, expected: ExpectedOutcome) -> DatasetItem:
        return DatasetItem(item_id=item_id, category="clear", utterance="Mở cửa ghế lái", expected=expected, split="dev")

    def test_correct_tool_call_is_captured_with_latency(self) -> None:
        transport = FakeTransport(
            [_openai_tool_call_response("control_access", {"action": "open", "target": "driver_door"})]
        )
        adapter = self._make_adapter(transport)
        item = self._item(
            "i1", ExpectedOutcome(kind="tool_call", tool_call=ToolCall("control_access", {"action": "open", "target": "driver_door"}))
        )
        runner = EvalRunner(adapter, pace_seconds=0.0)

        outcome = runner.run_item(item)

        self.assertEqual(outcome.proposal_kind, "action")
        self.assertEqual(outcome.tool, "control_access")
        self.assertEqual(outcome.arguments, {"action": "open", "target": "driver_door"})
        self.assertIsNotNone(outcome.latency_ms)
        self.assertGreaterEqual(outcome.latency_ms, 0)

        result = score_outcome(item, outcome)
        self.assertTrue(result.tool_correct)
        self.assertTrue(result.arguments_exact_match)

    def test_clarification_text_response_is_captured(self) -> None:
        transport = FakeTransport([_openai_text_response("Bạn muốn mở cửa nào?")])
        adapter = self._make_adapter(transport)
        item = self._item("i2", ExpectedOutcome(kind="clarification"))
        runner = EvalRunner(adapter, pace_seconds=0.0)

        outcome = runner.run_item(item)

        self.assertEqual(outcome.proposal_kind, "clarification")
        self.assertEqual(outcome.text, "Bạn muốn mở cửa nào?")

        result = score_outcome(item, outcome)
        self.assertTrue(result.clarification_correct)

    def test_malformed_response_recorded_as_malformed_output_error(self) -> None:
        transport = FakeTransport([{"choices": []}])  # violates "one choice required"
        adapter = self._make_adapter(transport)
        item = self._item(
            "i3", ExpectedOutcome(kind="tool_call", tool_call=ToolCall("control_access", {"action": "open", "target": "driver_door"}))
        )
        runner = EvalRunner(adapter, pace_seconds=0.0)

        outcome = runner.run_item(item)

        self.assertEqual(outcome.error_code, "MODEL_PROVIDER_MALFORMED_OUTPUT")
        result = score_outcome(item, outcome)
        self.assertTrue(result.is_malformed_output)

    def test_transport_exception_recorded_as_api_error(self) -> None:
        transport = FakeTransport([RuntimeError("connection reset")])
        adapter = self._make_adapter(transport)
        item = self._item(
            "i4", ExpectedOutcome(kind="tool_call", tool_call=ToolCall("control_access", {"action": "open", "target": "driver_door"}))
        )
        runner = EvalRunner(adapter, pace_seconds=0.0)

        outcome = runner.run_item(item)

        self.assertEqual(outcome.error_code, "MODEL_PROVIDER_API_ERROR")
        result = score_outcome(item, outcome)
        self.assertTrue(result.is_api_error)

    def test_missing_api_key_is_skipped_not_errored(self) -> None:
        transport = FakeTransport([])  # never called
        adapter = OpenAIAdapter(
            model_id="gpt-5-mini",
            api_key="",  # missing
            registry=load_registry(),
            transport=transport,
            config_checksum="sha256:" + "0" * 64,
        )
        item = self._item(
            "i5", ExpectedOutcome(kind="tool_call", tool_call=ToolCall("control_access", {"action": "open", "target": "driver_door"}))
        )
        runner = EvalRunner(adapter, pace_seconds=0.0)

        outcome = runner.run_item(item)

        self.assertIsNotNone(outcome.skipped_reason)
        self.assertEqual(len(transport.calls), 0)
        result = score_outcome(item, outcome)
        self.assertTrue(result.is_skipped)

    def test_run_paces_requests_using_injected_sleep(self) -> None:
        transport = FakeTransport(
            [
                _openai_tool_call_response("control_access", {"action": "open", "target": "driver_door"}),
                _openai_tool_call_response("control_access", {"action": "open", "target": "trunk"}),
                _openai_tool_call_response("control_access", {"action": "open", "target": "charge_port"}),
            ]
        )
        adapter = self._make_adapter(transport)
        items = [
            self._item("p1", ExpectedOutcome(kind="tool_call", tool_call=ToolCall("control_access", {"action": "open", "target": "driver_door"}))),
            self._item("p2", ExpectedOutcome(kind="tool_call", tool_call=ToolCall("control_access", {"action": "open", "target": "trunk"}))),
            self._item("p3", ExpectedOutcome(kind="tool_call", tool_call=ToolCall("control_access", {"action": "open", "target": "charge_port"}))),
        ]
        sleep_calls: list[float] = []
        runner = EvalRunner(adapter, pace_seconds=5.0, sleep=sleep_calls.append)

        outcomes = runner.run(items)

        self.assertEqual(len(outcomes), 3)
        # Paced before item 2 and item 3, never before the first item.
        self.assertEqual(sleep_calls, [5.0, 5.0])

    def test_full_dataset_slice_end_to_end_via_gemini_adapter_shape(self) -> None:
        """Exercises the Gemini payload/response shape too, not just OpenAI's."""
        from dataset import DATASET

        gemini_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"functionCall": {"name": "control_access", "args": {"action": "open", "target": "trunk"}}}
                        ]
                    }
                }
            ]
        }
        transport = FakeTransport([gemini_response])
        adapter = GeminiAdapter(
            model_id="gemini-3.5-flash-lite",
            api_key="fake-key",
            registry=load_registry(),
            transport=transport,
            config_checksum="sha256:" + "0" * 64,
        )
        item = next(i for i in DATASET if i.item_id == "clear__open_trunk")
        runner = EvalRunner(adapter, pace_seconds=0.0)

        outcome = runner.run_item(item)
        result = score_outcome(item, outcome)

        self.assertTrue(result.tool_correct)
        self.assertTrue(result.arguments_exact_match)

        report = aggregate_metrics([result], provider="gemini", split="all")
        self.assertEqual(report.tool_accuracy, 1.0)


if __name__ == "__main__":
    unittest.main()
