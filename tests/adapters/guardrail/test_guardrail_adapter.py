from __future__ import annotations

import copy
import json
import threading
import unittest
import urllib.error
from pathlib import Path
from io import BytesIO
from unittest.mock import patch

from src.vivi_agent.adapters.guardrail import (
    GuardrailAdapterError,
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)
from src.vivi_agent.contracts.guardrail.v1.mock_server import create_server

EXAMPLES = json.loads(
    Path("src/vivi_agent/contracts/guardrail/v1/examples.json").read_text(encoding="utf-8")
)


class GuardrailAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def client(self, provider: GuardrailProvider = GuardrailProvider.MOCK):
        return GuardrailClientAdapter(
            GuardrailClientConfig(self.base_url, provider, retry_backoff_seconds=0)
        )

    def test_config_rejects_negative_retry_backoff(self) -> None:
        with self.assertRaisesRegex(ValueError, "retry_backoff_seconds"):
            GuardrailClientConfig(
                self.base_url,
                GuardrailProvider.REAL,
                retry_backoff_seconds=-0.01,
            )

        config = GuardrailClientConfig(
            self.base_url,
            GuardrailProvider.MOCK,
            retry_backoff_seconds=0,
        )
        self.assertEqual(config.retry_backoff_seconds, 0)

    def test_mock_and_real_use_the_same_interface_and_visible_metadata(self) -> None:
        for provider in GuardrailProvider:
            client = self.client(provider)
            result = client.evaluate(copy.deepcopy(EXAMPLES["action_proposal"]))
            self.assertEqual(result["outcome"], "ALLOW")
            self.assertEqual(client.event_metadata["guardrail_provider"], provider.value)
            self.assertEqual(client.uses_mock, provider is GuardrailProvider.MOCK)

    def test_mock_fixtures_cover_allow_block_confirm_query_and_error(self) -> None:
        client = self.client()
        expected = {
            "ALLOW": "ALLOW",
            "BLOCK_UNSAFE": "BLOCK_UNSAFE",
            "CONFIRM": "CONFIRM",
            "ANSWER": "ANSWER",
        }
        for fixture, outcome in expected.items():
            proposal = copy.deepcopy(EXAMPLES["action_proposal"])
            proposal["proposal_id"] = f"prop-{fixture.lower()}"
            proposal["arguments"]["mock_outcome"] = fixture
            self.assertEqual(client.evaluate(proposal)["outcome"], outcome)

        proposal = copy.deepcopy(EXAMPLES["action_proposal"])
        proposal["arguments"]["mock_outcome"] = "MISSING"
        error = client.evaluate(proposal)
        self.assertEqual(error["kind"], "error")
        self.assertNotIn("permit", error)

    def test_state_changing_evaluation_is_never_retried(self) -> None:
        client = GuardrailClientAdapter(
            GuardrailClientConfig("http://127.0.0.1:1", GuardrailProvider.REAL, read_only_retries=3)
        )
        with patch("urllib.request.urlopen", side_effect=TimeoutError) as request:
            with self.assertRaises(GuardrailAdapterError) as raised:
                client.evaluate(EXAMPLES["action_proposal"])
        self.assertEqual(request.call_count, 1)
        self.assertFalse(raised.exception.execution_allowed)

    def test_read_only_query_uses_bounded_retries(self) -> None:
        client = GuardrailClientAdapter(
            GuardrailClientConfig(
                "http://127.0.0.1:1",
                GuardrailProvider.REAL,
                read_only_retries=2,
                retry_backoff_seconds=0,
            )
        )
        with patch("urllib.request.urlopen", side_effect=TimeoutError) as request:
            with self.assertRaises(GuardrailAdapterError) as raised:
                client.evaluate_query({"request_id": "req-1"})
        self.assertEqual(request.call_count, 3)
        self.assertTrue(raised.exception.retryable)

    def test_query_uses_fixed_read_only_route(self) -> None:
        client = self.client()
        response = copy.deepcopy(EXAMPLES["decisions"]["ANSWER"])
        with patch.object(client, "_post", return_value=response) as post:
            client.evaluate_query({"request_id": "req-query"})
        self.assertEqual(post.call_args.args[0], "/v1/evaluate/query")
        self.assertTrue(post.call_args.kwargs["read_only"])

    def test_http_error_cannot_smuggle_an_allow_decision(self) -> None:
        client = self.client(GuardrailProvider.REAL)
        decision = json.dumps(EXAMPLES["decisions"]["ALLOW"]).encode("utf-8")
        http_error = urllib.error.HTTPError(
            self.base_url,
            500,
            "Internal Server Error",
            {},
            BytesIO(decision),
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(GuardrailAdapterError) as raised:
                client.evaluate(EXAMPLES["action_proposal"])
        self.assertEqual(raised.exception.code, "MALFORMED_GUARDRAIL_RESPONSE")
        self.assertFalse(raised.exception.execution_allowed)

    def test_invalid_or_unbound_response_fails_closed(self) -> None:
        malformed = copy.deepcopy(EXAMPLES["decisions"]["BLOCK_UNSAFE"])
        malformed.pop("rule_id")
        mismatch = copy.deepcopy(EXAMPLES["decisions"]["ALLOW"])
        mismatch["proposal_id"] = "another-proposal"
        for response in (malformed, mismatch):
            client = self.client(GuardrailProvider.REAL)
            with patch.object(client, "_post", return_value=response):
                with self.assertRaises(GuardrailAdapterError) as raised:
                    client.evaluate(EXAMPLES["action_proposal"])
            self.assertFalse(raised.exception.execution_allowed)


if __name__ == "__main__":
    unittest.main()
