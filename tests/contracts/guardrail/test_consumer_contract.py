from __future__ import annotations

import copy
import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from src.vivi_agent.contracts.guardrail.v1.contract import (
    CONTRACT_VERSION,
    ContractValidationError,
    proposal_digest,
    validate_action_proposal,
    validate_guardrail_result,
)
from src.vivi_agent.contracts.guardrail.v1.mock_server import create_server

CONTRACT_DIR = Path("src/vivi_agent/integrations/viguard/wire")


class ContractFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.examples = json.loads((CONTRACT_DIR / "examples.json").read_text(encoding="utf-8"))
        cls.schema = json.loads(
            (CONTRACT_DIR / "guardrail-agent.schema.json").read_text(encoding="utf-8")
        )

    def test_all_seven_outcomes_have_valid_fixtures(self) -> None:
        decisions = self.examples["decisions"]
        self.assertEqual(
            set(decisions),
            {
                "ALLOW",
                "BLOCK_UNSAFE",
                "BLOCK_UNAVAILABLE",
                "CONFIRM",
                "NOT_VOICE_ACTIONABLE",
                "ANSWER",
                "UNKNOWN",
            },
        )
        for decision in decisions.values():
            validate_guardrail_result(decision)

    def test_only_allow_has_a_permit(self) -> None:
        for outcome, decision in self.examples["decisions"].items():
            self.assertEqual("permit" in decision, outcome == "ALLOW")

    def test_required_decision_fields_fail_closed(self) -> None:
        required = ("intent", "outcome", "rule_id", "state_version")
        source = self.examples["decisions"]["BLOCK_UNSAFE"]
        for field in required:
            malformed = copy.deepcopy(source)
            malformed.pop(field)
            with self.subTest(field=field), self.assertRaises(ContractValidationError) as raised:
                validate_guardrail_result(malformed)
            self.assertEqual(raised.exception.code, "MALFORMED_GUARDRAIL_RESPONSE")
            self.assertFalse(raised.exception.execution_allowed)

    def test_non_executable_results_reject_permit(self) -> None:
        permit = self.examples["decisions"]["ALLOW"]["permit"]
        cases = [
            self.examples["decisions"]["BLOCK_UNSAFE"],
            self.examples["decisions"]["BLOCK_UNAVAILABLE"],
            self.examples["decisions"]["NOT_VOICE_ACTIONABLE"],
            self.examples["decisions"]["CONFIRM"],
            self.examples["decisions"]["ANSWER"],
            self.examples["decisions"]["UNKNOWN"],
            self.examples["error"],
        ]
        for source in cases:
            malformed = copy.deepcopy(source)
            malformed["permit"] = permit
            with self.subTest(kind=source.get("outcome", "error")), self.assertRaises(
                ContractValidationError
            ) as raised:
                validate_guardrail_result(malformed)
            self.assertEqual(raised.exception.code, "PERMIT_FORBIDDEN")

    def test_version_mismatch_is_typed_and_fail_closed(self) -> None:
        malformed = copy.deepcopy(self.examples["decisions"]["ALLOW"])
        malformed["contract_version"] = "2.0.0"
        with self.assertRaises(ContractValidationError) as raised:
            validate_guardrail_result(malformed)
        self.assertEqual(raised.exception.code, "CONTRACT_VERSION_MISMATCH")
        self.assertFalse(raised.exception.execution_allowed)

    def test_malformed_permit_digest_and_timestamps_fail_closed(self) -> None:
        malformed_digest = copy.deepcopy(self.examples["decisions"]["ALLOW"])
        malformed_digest["permit"]["proposal_digest"] = "not-a-digest"
        with self.assertRaises(ContractValidationError) as digest_error:
            validate_guardrail_result(malformed_digest)
        self.assertEqual(digest_error.exception.code, "INVALID_PERMIT")

        invalid_expiry = copy.deepcopy(self.examples["decisions"]["ALLOW"])
        invalid_expiry["permit"]["expires_at"] = invalid_expiry["permit"]["issued_at"]
        with self.assertRaises(ContractValidationError) as expiry_error:
            validate_guardrail_result(invalid_expiry)
        self.assertEqual(expiry_error.exception.code, "INVALID_PERMIT")

    def test_block_rejects_even_null_permit_field(self) -> None:
        malformed = copy.deepcopy(self.examples["decisions"]["BLOCK_UNSAFE"])
        malformed["permit"] = None
        with self.assertRaises(ContractValidationError) as raised:
            validate_guardrail_result(malformed)
        self.assertEqual(raised.exception.code, "PERMIT_FORBIDDEN")

    def test_digest_is_stable_and_execution_fields_are_bound(self) -> None:
        proposal = self.examples["action_proposal"]
        validate_action_proposal(proposal)
        digest = proposal_digest(proposal)
        self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            self.examples["decisions"]["ALLOW"]["permit"]["proposal_digest"], digest
        )
        reordered = dict(reversed(list(proposal.items())))
        self.assertEqual(proposal_digest(reordered), digest)
        changed = copy.deepcopy(proposal)
        changed["arguments"]["target"] = "passenger_door"
        self.assertNotEqual(proposal_digest(changed), digest)
        trace_only = copy.deepcopy(proposal)
        trace_only["model_id"] = "another-model"
        self.assertEqual(proposal_digest(trace_only), digest)

    def test_action_proposal_identifiers_are_bounded_non_empty_strings(self) -> None:
        invalid_values = (None, "", 123, "x" * 129)
        fields = (
            "proposal_id",
            "session_id",
            "source_turn_id",
            "tool",
            "model_provider",
            "model_id",
        )
        for field in fields:
            for value in invalid_values:
                malformed = copy.deepcopy(self.examples["action_proposal"])
                malformed[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    ContractValidationError
                ) as raised:
                    validate_action_proposal(malformed)
                self.assertEqual(raised.exception.code, "INVALID_ACTION_PROPOSAL")

    def test_every_local_schema_reference_resolves(self) -> None:
        definitions = self.schema["$defs"]

        def walk(value: object) -> None:
            if isinstance(value, dict):
                ref = value.get("$ref")
                if isinstance(ref, str) and ref.startswith("#/$defs/"):
                    self.assertIn(ref.removeprefix("#/$defs/"), definitions)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(self.schema)


class MockServerConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.examples = json.loads((CONTRACT_DIR / "examples.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def post(self, path: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=2)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())
        with response:
            return response.status, json.loads(response.read())

    def test_action_endpoint_returns_contract_valid_decision(self) -> None:
        proposal = copy.deepcopy(self.examples["action_proposal"])
        proposal["proposal_id"] = "prop-dynamic"
        status, result = self.post("/v1/evaluate/action", proposal)
        self.assertEqual(status, 200)
        self.assertEqual(result["proposal_id"], proposal["proposal_id"])
        self.assertEqual(result["permit"]["proposal_digest"], proposal_digest(proposal))
        validate_guardrail_result(result)

    def test_contract_mismatch_returns_typed_error_and_no_permit(self) -> None:
        proposal = copy.deepcopy(self.examples["action_proposal"])
        proposal["contract_version"] = "0.9.0"
        status, result = self.post("/v1/evaluate/action", proposal)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"]["code"], "CONTRACT_VERSION_MISMATCH")
        self.assertNotIn("permit", result)
        validate_guardrail_result(result)

    def test_confirmation_and_monitor_use_distinct_routes(self) -> None:
        confirm_status, confirm_result = self.post(
            "/v1/confirmations/confirm", self.examples["confirmation_request"]
        )
        monitor_status, monitor_result = self.post(
            "/v1/monitor/evaluate", self.examples["monitor_request"]
        )
        self.assertEqual(confirm_status, 200)
        self.assertEqual(monitor_status, 200)
        self.assertEqual(confirm_result["outcome"], "ALLOW")
        self.assertEqual(confirm_result["proposal_id"], "prop-003")
        self.assertEqual(
            confirm_result["permit"]["proposal_digest"],
            proposal_digest(self.examples["confirmation_action_proposal"]),
        )
        self.assertEqual(monitor_result["outcome"], "BLOCK_UNSAFE")
        validate_guardrail_result(confirm_result)
        validate_guardrail_result(monitor_result)

        replay_status, replay_result = self.post(
            "/v1/confirmations/confirm", self.examples["confirmation_request"]
        )
        self.assertEqual(replay_status, 409)
        self.assertEqual(replay_result["error"]["code"], "CONFIRMATION_NOT_ACTIVE")
        self.assertNotIn("permit", replay_result)
        validate_guardrail_result(replay_result)


if __name__ == "__main__":
    unittest.main()
