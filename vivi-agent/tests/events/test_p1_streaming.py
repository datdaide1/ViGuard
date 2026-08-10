"""P1-STREAM acceptance tests for public progress and response streaming."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from src.vivi_agent.contracts.agent_ui.v1.contract import (
    AgentUIContractError,
    MAX_CHUNK_CHARS,
    MAX_RESPONSE_CHUNKS,
    validate_event_stream,
    validate_public_payload,
)
from src.vivi_agent.events import AgentEventPipeline


class P1StreamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = AgentEventPipeline()
        self.ids = {"session_id": "session-stream", "turn_id": "turn-1", "request_id": "req-1"}

    def test_progress_and_chunks_are_contiguous_public_events(self) -> None:
        self.pipeline.emit_turn_progress(**self.ids, phase="received", progress=0.0)
        self.pipeline.emit_turn_progress(**self.ids, phase="responding", progress=0.8, message="Đang soạn phản hồi")
        self.pipeline.emit_response_chunk(**self.ids, stream_id="stream-1", chunk_index=0, delta="Xin ")
        self.pipeline.emit_response_chunk(**self.ids, stream_id="stream-1", chunk_index=1, delta="chào", final=True)
        self.pipeline.emit_turn_progress(**self.ids, phase="completed", progress=1.0)

        events = self.pipeline.store.get_events("session-stream")
        validate_event_stream(events)
        self.assertEqual([event["sequence"] for event in events], [1, 2, 3, 4, 5])
        self.assertEqual("".join(event["delta"] for event in events if event["event_type"] == "response_chunk"), "Xin chào")

    def test_progress_regression_and_event_after_terminal_are_rejected(self) -> None:
        self.pipeline.emit_turn_progress(**self.ids, phase="responding", progress=0.7)
        for phase, progress, code in (
            ("resolving", 0.8, "TURN_PROGRESS_REGRESSION"),
            ("responding", 0.6, "TURN_PROGRESS_REGRESSION"),
        ):
            with self.subTest(code=code), self.assertRaises(AgentUIContractError) as raised:
                self.pipeline.emit_turn_progress(**self.ids, phase=phase, progress=progress)
            self.assertEqual(raised.exception.code, code)
        self.pipeline.emit_turn_progress(**self.ids, phase="completed", progress=1.0)
        with self.assertRaises(AgentUIContractError) as raised:
            self.pipeline.emit_turn_progress(**self.ids, phase="completed", progress=1.0)
        self.assertEqual(raised.exception.code, "TURN_PROGRESS_ALREADY_TERMINAL")

    def test_chunk_gap_stream_switch_and_post_terminal_chunk_are_rejected(self) -> None:
        with self.assertRaises(AgentUIContractError) as raised:
            self.pipeline.emit_response_chunk(**self.ids, stream_id="stream-1", chunk_index=1, delta="gap")
        self.assertEqual(raised.exception.code, "RESPONSE_CHUNK_GAP")
        self.pipeline.emit_response_chunk(**self.ids, stream_id="stream-1", chunk_index=0, delta="first")
        with self.assertRaises(AgentUIContractError) as raised:
            self.pipeline.emit_response_chunk(**self.ids, stream_id="stream-2", chunk_index=1, delta="switch")
        self.assertEqual(raised.exception.code, "RESPONSE_STREAM_MISMATCH")
        self.pipeline.emit_response_chunk(**self.ids, stream_id="stream-1", chunk_index=1, delta="last", final=True)
        with self.assertRaises(AgentUIContractError) as raised:
            self.pipeline.emit_response_chunk(**self.ids, stream_id="stream-1", chunk_index=2, delta="late")
        self.assertEqual(raised.exception.code, "RESPONSE_STREAM_ALREADY_TERMINAL")

    def test_private_reasoning_is_redacted_before_chunk_validation(self) -> None:
        event = self.pipeline.emit_raw(
            {
                "contract_version": "1.1.0", "kind": "event", "event_type": "response_chunk",
                "event_id": "evt-safe", "session_id": "session-safe", "turn_id": "turn-safe",
                "request_id": "req-safe", "occurred_at": "2026-08-10T00:00:00Z", "actor": "AGENT",
                "stream_id": "stream-safe", "chunk_index": 0, "delta": "Public answer", "content_kind": "answer",
                "final": True, "hidden_reasoning": "must never be public",
            }
        )
        self.assertNotIn("hidden_reasoning", event)

    def test_session_subscription_replays_then_follows_only_its_session(self) -> None:
        self.pipeline.emit_turn_progress(**self.ids, phase="received", progress=0.0)
        received: list[dict[str, object]] = []
        token = self.pipeline.stream_adapter.subscribe_session("session-stream", received.append)
        self.pipeline.emit_turn_progress(**self.ids, phase="responding", progress=0.8)
        self.pipeline.emit_turn_progress(
            session_id="other-session", turn_id="turn-2", request_id="req-2", phase="received", progress=0.0
        )
        self.pipeline.stream_adapter.unsubscribe_session(token)
        self.pipeline.emit_turn_progress(**self.ids, phase="completed", progress=1.0)
        self.assertEqual([event["sequence"] for event in received], [1, 2])

    def test_reconnect_cursor_replays_no_duplicate_chunks(self) -> None:
        first = self.pipeline.emit_response_chunk(**self.ids, stream_id="stream-1", chunk_index=0, delta="one")
        self.pipeline.emit_response_chunk(**self.ids, stream_id="stream-1", chunk_index=1, delta="two", final=True)
        resumed = self.pipeline.polling_adapter.poll("session-stream", since_sequence=first["sequence"])
        self.assertEqual([event["chunk_index"] for event in resumed], [1])

    def test_broken_ui_subscriber_cannot_break_event_storage(self) -> None:
        errors: list[Exception] = []

        def broken(_: dict[str, object]) -> None:
            raise RuntimeError("UI disconnected")

        self.pipeline.stream_adapter.subscribe_session("session-stream", broken, on_error=errors.append)
        stored = self.pipeline.emit_turn_progress(**self.ids, phase="received", progress=0.0)
        self.assertEqual(stored["sequence"], 1)
        self.assertEqual(len(errors), 1)
        self.pipeline.emit_turn_progress(**self.ids, phase="responding", progress=0.8)
        self.assertEqual(len(errors), 1, "failed subscription must be detached")

    def test_broken_error_handler_cannot_break_event_storage(self) -> None:
        def broken(_: dict[str, object]) -> None:
            raise RuntimeError("UI disconnected")

        def broken_error_handler(_: Exception) -> None:
            raise RuntimeError("error channel disconnected")

        self.pipeline.stream_adapter.subscribe_session(
            "session-stream", broken, on_error=broken_error_handler
        )
        stored = self.pipeline.emit_turn_progress(**self.ids, phase="received", progress=0.0)
        self.assertEqual(stored["sequence"], 1)

    def test_callback_runs_outside_registry_lock(self) -> None:
        callback_started = Event()
        release_callback = Event()

        def blocking(_: dict[str, object]) -> None:
            callback_started.set()
            release_callback.wait(timeout=2)

        self.pipeline.stream_adapter.subscribe_session("session-stream", blocking)
        producer = Thread(
            target=lambda: self.pipeline.emit_turn_progress(
                **self.ids, phase="received", progress=0.0
            )
        )
        producer.start()
        self.assertTrue(callback_started.wait(timeout=1))
        token = self.pipeline.stream_adapter.subscribe_session("other-session", lambda _: None)
        self.pipeline.stream_adapter.unsubscribe_session(token)
        release_callback.set()
        producer.join(timeout=1)
        self.assertFalse(producer.is_alive())

    def test_subscriber_can_unsubscribe_itself_without_mutating_iteration(self) -> None:
        received: list[int] = []
        token = ""

        def once(event: dict[str, object]) -> None:
            received.append(int(event["sequence"]))
            self.pipeline.stream_adapter.unsubscribe_session(token)

        token = self.pipeline.stream_adapter.subscribe_session("session-stream", once)
        self.pipeline.emit_turn_progress(**self.ids, phase="received", progress=0.0)
        self.pipeline.emit_turn_progress(**self.ids, phase="responding", progress=0.8)
        self.assertEqual(received, [1])

    def test_completed_progress_and_content_kind_are_consistent(self) -> None:
        with self.assertRaises(AgentUIContractError) as raised:
            self.pipeline.emit_turn_progress(**self.ids, phase="completed", progress=0.9)
        self.assertEqual(raised.exception.code, "INCOMPLETE_TERMINAL_PROGRESS")
        self.pipeline.emit_response_chunk(**self.ids, stream_id="stream-1", chunk_index=0, delta="one")
        with self.assertRaises(AgentUIContractError) as raised:
            self.pipeline.emit_response_chunk(
                **self.ids, stream_id="stream-1", chunk_index=1, delta="two", content_kind="status"
            )
        self.assertEqual(raised.exception.code, "RESPONSE_CONTENT_KIND_MISMATCH")

    def test_contract_10_remains_valid_but_cannot_emit_streaming_events(self) -> None:
        legacy_request = {
            "contract_version": "1.0.0", "kind": "request", "request_type": "message",
            "session_id": "legacy-session", "turn_id": "legacy-turn", "request_id": "legacy-request",
            "occurred_at": "2026-08-10T00:00:00Z", "message": "hello",
        }
        validate_public_payload(legacy_request)
        stream_event = self.pipeline.emit_turn_progress(**self.ids, phase="received", progress=0.0)
        stream_event["contract_version"] = "1.0.0"
        with self.assertRaises(AgentUIContractError) as raised:
            validate_public_payload(stream_event)
        self.assertEqual(raised.exception.code, "STREAMING_REQUIRES_V1_1")

    def test_chunk_and_session_bounds_are_enforced(self) -> None:
        self.pipeline.emit_response_chunk(
            **self.ids, stream_id="stream-1", chunk_index=0, delta="x" * MAX_CHUNK_CHARS
        )
        with self.assertRaises(AgentUIContractError) as raised:
            self.pipeline.emit_response_chunk(
                **self.ids, stream_id="stream-1", chunk_index=1, delta="x" * (MAX_CHUNK_CHARS + 1)
            )
        self.assertEqual(raised.exception.code, "INVALID_CHUNK_DELTA")

        bounded = AgentEventPipeline()
        bounded.store.MAX_EVENTS_PER_SESSION = 1
        bounded.emit_turn_progress(**self.ids, phase="received", progress=0.0)
        with self.assertRaisesRegex(ValueError, "EVENT_STORE_SESSION_LIMIT"):
            bounded.emit_turn_progress(**self.ids, phase="resolving", progress=0.1)

    def test_store_validates_each_event_once_instead_of_rescanning_history(self) -> None:
        from src.vivi_agent.events import store as store_module

        with patch.object(
            store_module, "validate_next_event", wraps=store_module.validate_next_event
        ) as validator:
            for index in range(20):
                self.pipeline.emit_turn_progress(
                    session_id="session-once", turn_id=f"turn-{index}", request_id=f"req-{index}",
                    phase="received", progress=0.0,
                )
        self.assertEqual(validator.call_count, 20)

    def test_chunk_index_limit_is_enforced_by_payload_validation(self) -> None:
        event = self.pipeline.emit_response_chunk(
            **self.ids, stream_id="stream-limit", chunk_index=0, delta="ok"
        )
        event["chunk_index"] = MAX_RESPONSE_CHUNKS
        with self.assertRaises(AgentUIContractError) as raised:
            validate_public_payload(event)
        self.assertEqual(raised.exception.code, "RESPONSE_CHUNK_LIMIT")

    def test_json_schema_accepts_both_new_event_variants(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is optional")
        schema = json.loads(Path("src/vivi_agent/contracts/agent_ui/v1/agent-ui.schema.json").read_text(encoding="utf-8"))
        progress = self.pipeline.emit_turn_progress(**self.ids, phase="received", progress=0.0)
        chunk = self.pipeline.emit_response_chunk(**self.ids, stream_id="stream-1", chunk_index=0, delta="ok", final=True)
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(progress)
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(chunk)


if __name__ == "__main__":
    unittest.main()
