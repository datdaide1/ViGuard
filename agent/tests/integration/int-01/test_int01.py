"""Integration tests for INT-01: Chạy integration với Guardrail thật.

Verifies end-to-end integration between Agent Orchestrator, Guardrail Client Adapter
(both MOCK and REAL providers), HTTP Guardrail Server, and Vehicle Execution Gateway.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import threading
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

# Ensure src is in python path
SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src"))
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)
if ROOT_PATH not in sys.path:
    sys.path.insert(0, ROOT_PATH)

from vehicle_agent.adapters.guardrail import (
    GuardrailAdapterError,
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)
from vehicle_agent.catalog import load_manifest
from vehicle_agent.contracts.guardrail.v1.contract import (
    CONTRACT_VERSION,
    ContractValidationError,
    proposal_digest,
    validate_action_proposal,
    validate_guardrail_result,
)
from vehicle_agent.contracts.guardrail.v1.mock_server import create_server
from vehicle_agent.model_providers import ModelActionProposal, ProviderMetadata, TurnBinding
from vehicle_agent.orchestrator import (
    AgentOrchestrator,
    CancellationToken,
    ExecutionResult,
    TurnError,
    TurnRequest,
    TurnState,
    TurnStatus,
)
from vehicle_agent.tools.mapping import load_default_mapper
from vehicle_agent.tools.registry import load_registry
from vehicle_agent.vehicle.execution import VehicleToolGateway, make_open_door_handler
from vehicle_agent.vehicle.state import VehicleStateMachine


EXAMPLES = json.loads(
    Path(SRC_PATH, "vehicle_agent/integrations/aegis/wire/examples.json").read_text(encoding="utf-8")
)
META = ProviderMetadata("openai", "test-model-v1", "sha256:test", 5)
FIXED_TIME = datetime.fromisoformat("2026-08-03T10:00:01+00:00")


class ActuatorSpy:
    """Spy wrapper to verify actuator handler call counts."""

    def __init__(self, target_handler: Any = None) -> None:
        self.target_handler = target_handler
        self.call_count: int = 0
        self.calls: list[dict[str, Any]] = []

    def __call__(self, proposal: dict[str, Any]) -> dict[str, Any]:
        self.call_count += 1
        self.calls.append(proposal)
        if self.target_handler:
            return self.target_handler(proposal)
        return {
            "state_version": 1,
            "facts": {"target_door": "driver_door", "position": "open"},
            "message": "Đã mở cửa ghế lái.",
        }


class MockModelRouter:
    """Deterministic model router for testing tool proposal mapping."""

    def __init__(self, mock_proposal: ModelActionProposal | None = None) -> None:
        self.mock_proposal = mock_proposal or ModelActionProposal.action(
            "control_access",
            {"action": "open", "target": "driver_door"},
            META,
        )

    def propose_tool(
        self, messages: list[dict[str, str]], binding: TurnBinding
    ) -> ModelActionProposal:
        binding.record_proposal(self.mock_proposal)
        return self.mock_proposal

    def compose_response(
        self, facts: Mapping[str, Any], turn: TurnBinding
    ) -> ModelActionProposal:
        return ModelActionProposal.response("Phản hồi thông tin xe.", META)


class SpyExecutor:
    """Proxies Orchestrator execution calls to VehicleToolGateway while tracking calls."""

    def __init__(self, gateway: VehicleToolGateway) -> None:
        self.gateway = gateway
        self.execution_count: int = 0

    def execute(
        self,
        proposal: Mapping[str, Any],
        decision: Mapping[str, Any],
        cancellation: CancellationToken,
    ) -> ExecutionResult:
        self.execution_count += 1
        return self.gateway.execute(
            proposal, decision, cancellation, current_time=FIXED_TIME
        )


class GuardrailIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.mapper = load_default_mapper(load_registry(), load_manifest())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get_client(self, provider: GuardrailProvider = GuardrailProvider.REAL) -> GuardrailClientAdapter:
        return GuardrailClientAdapter(
            GuardrailClientConfig(
                base_url=self.base_url,
                provider=provider,
                timeout_seconds=2.0,
                read_only_retries=1,
                retry_backoff_seconds=0.01,
            )
        )

    def setUp(self) -> None:
        self.actuator_spy = ActuatorSpy(make_open_door_handler(VehicleStateMachine()))
        self.gateway = VehicleToolGateway()
        self.gateway.registry.register("open_door", self.actuator_spy)
        self.gateway.registry.register("control_access", self.actuator_spy)
        self.executor_spy = SpyExecutor(self.gateway)

    def test_contract_version_handshake(self) -> None:
        """Verify contract version handshake and mismatch fail-closed behavior."""
        client = self.get_client()
        self.assertEqual(client.event_metadata["guardrail_contract_version"], CONTRACT_VERSION)

        # Mismatched contract version in payload should raise GuardrailAdapterError
        proposal = copy.deepcopy(EXAMPLES["action_proposal"])
        proposal["contract_version"] = "99.0.0"
        with self.assertRaises(GuardrailAdapterError) as raised:
            client.evaluate(proposal)
        self.assertEqual(raised.exception.code, "CONTRACT_VERSION_MISMATCH")
        self.assertFalse(raised.exception.execution_allowed)

    def test_public_outcome_allow_executes_handler(self) -> None:
        """Verify ALLOW outcome authorizes vehicle gateway execution and calls handler exactly once."""
        client = self.get_client()
        router = MockModelRouter()
        orchestrator = AgentOrchestrator(
            model_router=router,
            mapper=self.mapper,
            guardrail=client,
            executor=self.executor_spy,
        )

        request = TurnRequest(
            session_id="session-int-01",
            turn_id="turn-allow-001",
            request_id="req-allow-001",
            message="Mở cửa xe ghế lái",
        )
        result = orchestrator.handle_message(request)

        self.assertEqual(result.status, TurnStatus.COMPLETED)
        self.assertEqual(result.state, TurnState.COMPLETED)
        self.assertEqual(self.executor_spy.execution_count, 1)
        self.assertEqual(self.actuator_spy.call_count, 1)
        self.assertIn(TurnState.COMPLETED, result.trace)

    def test_public_outcome_block_unsafe_calls_handler_zero_times(self) -> None:
        """Verify BLOCK_UNSAFE outcome prevents vehicle execution with ZERO handler calls."""
        client = self.get_client()
        router = MockModelRouter()
        orchestrator = AgentOrchestrator(
            model_router=router,
            mapper=self.mapper,
            guardrail=client,
            executor=self.executor_spy,
            id_factory=lambda prefix: f"prop-block-{prefix}-001",
        )

        request = TurnRequest(
            session_id="session-int-01",
            turn_id="turn-block-001",
            request_id="req-block-001",
            message="Mở cửa xe ghế lái",
        )
        result = orchestrator.handle_message(request)

        self.assertEqual(result.status, TurnStatus.BLOCKED)
        self.assertEqual(result.state, TurnState.BLOCKED)
        self.assertEqual(result.rule_id, "R002")
        self.assertEqual(self.executor_spy.execution_count, 0)
        self.assertEqual(self.actuator_spy.call_count, 0)

    def test_public_outcome_confirm_calls_handler_zero_times(self) -> None:
        """Verify CONFIRM outcome returns confirmation request with ZERO handler calls."""
        client = self.get_client()
        router = MockModelRouter()
        orchestrator = AgentOrchestrator(
            model_router=router,
            mapper=self.mapper,
            guardrail=client,
            executor=self.executor_spy,
            id_factory=lambda prefix: f"prop-confirm-{prefix}-001",
        )

        request = TurnRequest(
            session_id="session-int-01",
            turn_id="turn-confirm-001",
            request_id="req-confirm-001",
            message="Mở cửa xe ghế lái",
        )
        result = orchestrator.handle_message(request)

        self.assertEqual(result.status, TurnStatus.NEEDS_CONFIRMATION)
        self.assertEqual(result.state, TurnState.AWAITING_CONFIRMATION)
        self.assertEqual(self.executor_spy.execution_count, 0)
        self.assertEqual(self.actuator_spy.call_count, 0)

    def test_public_outcome_answer_calls_handler_zero_times(self) -> None:
        """Verify ANSWER outcome returns grounded response with ZERO handler calls."""
        client = self.get_client()
        router = MockModelRouter()
        orchestrator = AgentOrchestrator(
            model_router=router,
            mapper=self.mapper,
            guardrail=client,
            executor=self.executor_spy,
            id_factory=lambda prefix: f"prop-answer-{prefix}-001",
        )

        request = TurnRequest(
            session_id="session-int-01",
            turn_id="turn-answer-001",
            request_id="req-answer-001",
            message="Mở cửa xe ghế lái",
        )
        result = orchestrator.handle_message(request)

        self.assertEqual(result.status, TurnStatus.COMPLETED)
        self.assertEqual(result.state, TurnState.COMPLETED)
        self.assertEqual(result.message, "Phản hồi thông tin xe.")
        self.assertEqual(self.executor_spy.execution_count, 0)
        self.assertEqual(self.actuator_spy.call_count, 0)

    def test_permit_and_digest_compatibility(self) -> None:
        """Verify permit proposal_digest matching and rejection of mismatched permits."""
        client = self.get_client()
        proposal = copy.deepcopy(EXAMPLES["action_proposal"])
        expected_digest = proposal_digest(proposal)

        # Real evaluation returns matching permit digest
        res = client.evaluate(proposal)
        self.assertEqual(res["outcome"], "ALLOW")
        self.assertEqual(res["permit"]["proposal_digest"], expected_digest)

        # Mismatched permit digest on ALLOW must fail closed in client adapter
        mismatch_decision = copy.deepcopy(EXAMPLES["decisions"]["ALLOW"])
        mismatch_decision["permit"]["proposal_digest"] = "sha256:" + "f" * 64
        mismatch_decision["proposal_id"] = proposal["proposal_id"]

        with patch.object(client, "_post", return_value=mismatch_decision):
            with self.assertRaises(GuardrailAdapterError) as raised:
                client.evaluate(proposal)
            self.assertEqual(raised.exception.code, "PROPOSAL_MISMATCH")
            self.assertFalse(raised.exception.execution_allowed)
            self.assertEqual(self.actuator_spy.call_count, 0)

    def test_state_snapshot_and_monitor_confirm_compatibility(self) -> None:
        """Verify state version/snapshot compatibility across monitor and confirmation routes."""
        client = self.get_client()

        # Confirmation evaluation route
        confirm_res = client.confirm(
            confirmation_id="confirm-001",
            session_id="session-001",
            request_id="req-confirm-001",
        )
        self.assertEqual(confirm_res["outcome"], "ALLOW")
        self.assertIn("relevant_state", confirm_res)
        self.assertIn("speed", confirm_res["relevant_state"])
        validate_guardrail_result(confirm_res)

        # Monitor evaluation route
        monitor_req = copy.deepcopy(EXAMPLES["monitor_request"])
        monitor_res = client.evaluate_monitor(monitor_req)
        self.assertEqual(monitor_res["outcome"], "BLOCK_UNSAFE")
        self.assertEqual(monitor_res["state_version"], 13)
        validate_guardrail_result(monitor_res)

    def test_error_timeout_and_degraded_scenarios(self) -> None:
        """Verify timeout fail-closed on state-changing evaluations and retries on read-only queries."""
        client = GuardrailClientAdapter(
            GuardrailClientConfig(
                base_url="http://127.0.0.1:1",  # Unreachable port
                provider=GuardrailProvider.REAL,
                timeout_seconds=0.1,
                read_only_retries=2,
                retry_backoff_seconds=0.01,
            )
        )

        # State-changing evaluation is never retried and fails closed
        proposal = copy.deepcopy(EXAMPLES["action_proposal"])
        with patch("urllib.request.urlopen", side_effect=TimeoutError) as req_mock:
            with self.assertRaises(GuardrailAdapterError) as raised:
                client.evaluate(proposal)
            self.assertEqual(req_mock.call_count, 1)
            self.assertEqual(raised.exception.code, "GUARDRAIL_UNAVAILABLE")
            self.assertFalse(raised.exception.execution_allowed)
            self.assertFalse(raised.exception.retryable)

        # Read-only query evaluation uses bounded retries
        with patch("urllib.request.urlopen", side_effect=TimeoutError) as req_mock:
            with self.assertRaises(GuardrailAdapterError) as raised:
                client.evaluate_query({"request_id": "req-query-001"})
            self.assertEqual(req_mock.call_count, 3)  # 1 initial + 2 retries
            self.assertTrue(raised.exception.retryable)

        # Malformed HTTP response without typed error fails closed
        http_err = urllib.error.HTTPError(
            self.base_url, 500, "Internal Error", {}, None
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            with self.assertRaises(GuardrailAdapterError) as raised:
                client.evaluate(proposal)
            self.assertEqual(raised.exception.code, "MALFORMED_GUARDRAIL_RESPONSE")
            self.assertFalse(raised.exception.execution_allowed)

    def test_joint_trace_correlation(self) -> None:
        """Verify correlation of session_id, turn_id, proposal_id, request_id and trace steps."""
        client = self.get_client()
        router = MockModelRouter()
        orchestrator = AgentOrchestrator(
            model_router=router,
            mapper=self.mapper,
            guardrail=client,
            executor=self.executor_spy,
        )

        request = TurnRequest(
            session_id="sess-correlation-100",
            turn_id="turn-correlation-200",
            request_id="req-correlation-300",
            message="Mở cửa xe ghế lái",
        )

        result = orchestrator.handle_message(request)
        self.assertEqual(result.status, TurnStatus.COMPLETED)
        self.assertEqual(
            result.trace,
            (
                TurnState.RECEIVED,
                TurnState.RESOLVING,
                TurnState.PROPOSED,
                TurnState.AUTHORIZING,
                TurnState.EXECUTING,
                TurnState.COMPLETED,
            ),
        )

    def test_mock_and_real_provider_parity(self) -> None:
        """Verify MOCK and REAL providers share identical client interface and pass consumer contract."""
        mock_client = self.get_client(GuardrailProvider.MOCK)
        real_client = self.get_client(GuardrailProvider.REAL)

        for client in (mock_client, real_client):
            proposal = copy.deepcopy(EXAMPLES["action_proposal"])
            proposal["proposal_id"] = f"prop-{client.config.provider.value}"
            res = client.evaluate(proposal)
            self.assertEqual(res["outcome"], "ALLOW")
            self.assertIn("permit", res)
            validate_guardrail_result(res)

            query_res = client.evaluate_query({"request_id": f"query-{client.config.provider.value}"})
            self.assertEqual(query_res["outcome"], "ANSWER")
            validate_guardrail_result(query_res)


if __name__ == "__main__":
    unittest.main()
