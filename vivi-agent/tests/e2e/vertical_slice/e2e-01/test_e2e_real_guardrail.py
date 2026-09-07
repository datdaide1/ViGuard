"""E2E-01 against the REAL ViGuard service (Phase 2' increment 2'.4).

Same vertical slice as ``test_e2e_01`` (user message -> proposal -> mapper ->
Guardrail -> execution), but ``env.guardrail`` is swapped for the Agent's real
``GuardrailClientAdapter(REAL)`` pointed at an in-process ``vf_guardrails``
HTTP service. Proves the two separate services (decision D1) actually integrate
over the wire: permit digest binding, decision/intent correlation, and the
CONFIRM handshake all hold with no mock in the path.
"""
from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

from vivi_agent.adapters.guardrail import (
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)
from vivi_agent.catalog import load_manifest
from vivi_agent.model_providers import ModelActionProposal, ProviderMetadata
from vivi_agent.orchestrator import AgentOrchestrator, MessageEndpoint
from vivi_agent.tools.mapping import load_default_mapper
from vivi_agent.tools.registry import load_registry
from vivi_agent.vehicle.state import Gear

from .fixtures import E2EMockModelRouter, create_e2e_environment

# vf_guardrails uses the repo convention: its package dir on sys.path, flat
# imports. Added AFTER vivi_agent is fully imported so the bare name ``src``
# (vf_guardrails/src, the T1 classifier) can't shadow vivi_agent's own.
_VF = Path(__file__).resolve().parents[5] / "vf_guardrails"
if _VF.is_dir() and str(_VF) not in sys.path:
    sys.path.insert(0, str(_VF))

try:
    from policy import VehicleState  # noqa: E402
    from service.app import GuardrailService  # noqa: E402
    from service.http import create_server  # noqa: E402
    from service.state_store import VehicleStateStore  # noqa: E402

    _HAVE_SERVICE = True
except Exception:  # pragma: no cover - guardrail package not resolvable
    _HAVE_SERVICE = False

_META = ProviderMetadata(provider="openai", model_id="gpt-4o", config_checksum="sha256:e2e", latency_ms=5)


@unittest.skipUnless(_HAVE_SERVICE, "vf_guardrails service not importable")
class E2ERealGuardrailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapper = load_default_mapper(load_registry(), load_manifest())
        self.store = VehicleStateStore(VehicleState(gear="P", speed=0))
        self.server = create_server(port=0, service=GuardrailService(store=self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.adapter = GuardrailClientAdapter(
            GuardrailClientConfig(
                f"http://127.0.0.1:{self.server.server_address[1]}",
                GuardrailProvider.REAL,
                retry_backoff_seconds=0,
            )
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _endpoint(self, env) -> MessageEndpoint:
        return MessageEndpoint(
            AgentOrchestrator(
                model_router=env.model_router,
                mapper=self.mapper,
                guardrail=self.adapter,
                executor=env.spy_executor,
            )
        )

    def _msg(self, **over):
        base = {
            "contract_version": "1.0.0",
            "kind": "request",
            "request_type": "message",
            "session_id": "sess-real",
            "turn_id": "turn-1",
            "request_id": "req-1",
            "occurred_at": "2026-09-07T00:00:00Z",
            "message": "Mở cửa ghế lái",
        }
        base.update(over)
        return base

    def test_allow_path_executes_once_through_real_service(self) -> None:
        env = create_e2e_environment(speed=0.0, gear=Gear.PARK)
        response = self._endpoint(env).post_message(self._msg())
        self.assertEqual(response["status"], "completed")
        self.assertEqual(env.spy_actuator.call_count, 1)
        self.assertEqual(env.state_machine.snapshot().state_version, 1)

    def test_moving_state_blocks_with_zero_actuator_calls(self) -> None:
        env = create_e2e_environment(speed=40.0, gear=Gear.DRIVE)
        self.store.apply_preset("driving")
        response = self._endpoint(env).post_message(
            self._msg(session_id="sess-blk", turn_id="turn-blk", request_id="req-blk")
        )
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["rule_id"], "R002")
        self.assertEqual(env.spy_actuator.call_count, 0)

    def test_confirm_path_returns_needs_confirmation_and_executes_nothing(self) -> None:
        env = create_e2e_environment(speed=40.0, gear=Gear.DRIVE)
        env.model_router = E2EMockModelRouter(
            ModelActionProposal.action(
                "control_light", {"action": "turn_on", "target": "interior_light"}, _META
            )
        )
        self.store.apply_preset("driving")
        response = self._endpoint(env).post_message(
            self._msg(
                message="Bật đèn trong xe",
                session_id="sess-cfm",
                turn_id="turn-cfm",
                request_id="req-cfm",
            )
        )
        self.assertEqual(response["status"], "needs_confirmation")
        self.assertIn("confirmation_id", response)
        self.assertEqual(env.spy_actuator.call_count, 0)


if __name__ == "__main__":
    unittest.main()
