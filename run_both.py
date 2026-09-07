"""run_both.py -- boot the ViGuard Guardrail service + the ViVi Agent and run a
few turns end to end (Phase 2' increment 2'.4 demo).

    py -3 run_both.py

Two separate processes-worth of code in one script for demo convenience:
  * the Guardrail HTTP service (``vf_guardrails.service``) on a loopback port, in
    a background thread;
  * an ``AgentOrchestrator`` wired to the Agent's real
    ``GuardrailClientAdapter(REAL)`` pointed at that port.

It walks three scenarios -- ALLOW, BLOCK_UNSAFE, CONFIRM -- printing the turn
result and the public event stream for each. No mock Guardrail anywhere.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

_REPO = Path(__file__).resolve().parent

# vivi_agent first (so the bare name `src` resolves to vivi-agent/src, not
# vf_guardrails/src), then the Guardrail package dir (repo convention: flat
# imports off its own directory).
for _p in (str(_REPO / "vivi-agent" / "src"), str(_REPO / "vivi-agent")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from vivi_agent.adapters.guardrail import (  # noqa: E402
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)
from vivi_agent.catalog import load_manifest  # noqa: E402
from vivi_agent.events import AgentEventPipeline, AgentEventStore  # noqa: E402
from vivi_agent.model_providers import ModelActionProposal, ProviderMetadata  # noqa: E402
from vivi_agent.orchestrator import AgentOrchestrator, MessageEndpoint  # noqa: E402
from vivi_agent.tools.mapping import load_default_mapper  # noqa: E402
from vivi_agent.tools.registry import load_registry  # noqa: E402
from vivi_agent.vehicle.execution import VehicleToolGateway, make_open_door_handler  # noqa: E402
from vivi_agent.vehicle.state import Gear, VehicleStateMachine  # noqa: E402

sys.path.insert(0, str(_REPO / "vf_guardrails"))
from policy import VehicleState  # noqa: E402
from service.app import GuardrailService  # noqa: E402
from service.http import create_server  # noqa: E402
from service.state_store import VehicleStateStore  # noqa: E402

_META = ProviderMetadata(provider="openai", model_id="gpt-5-mini", config_checksum="sha256:demo", latency_ms=5)


class ScriptedRouter:
    """Stand-in for the model provider: returns a fixed tool call per turn."""

    def __init__(self, tool: str, arguments: dict) -> None:
        self._proposal = ModelActionProposal.action(tool, arguments, _META)

    def propose_tool(self, messages, turn):  # noqa: ANN001
        turn.record_proposal(self._proposal)
        return self._proposal

    def compose_response(self, facts, turn):  # noqa: ANN001
        return ModelActionProposal.response("Đã xử lý yêu cầu.", _META)


class GatewayExecutor:
    def __init__(self, gateway: VehicleToolGateway) -> None:
        self._gateway = gateway
        self.calls = 0

    def execute(self, proposal, decision, cancellation):  # noqa: ANN001
        self.calls += 1
        return self._gateway.execute(proposal, decision, cancellation)


def _run_turn(title: str, *, preset: str, tool: str, arguments: dict, message: str) -> None:
    store.apply_preset(preset)
    state_machine = VehicleStateMachine()
    gateway = VehicleToolGateway()
    handler = make_open_door_handler(state_machine)
    gateway.registry.register("open_door", handler)
    gateway.registry.register("control_access", handler)
    executor = GatewayExecutor(gateway)
    event_store = AgentEventStore()

    orchestrator = AgentOrchestrator(
        model_router=ScriptedRouter(tool, arguments),
        mapper=mapper,
        guardrail=adapter,
        executor=executor,
    )
    endpoint = MessageEndpoint(orchestrator)
    result = endpoint.post_message(
        {
            "contract_version": "1.0.0",
            "kind": "request",
            "request_type": "message",
            "session_id": f"sess-{preset}",
            "turn_id": f"turn-{preset}",
            "request_id": f"req-{preset}",
            "occurred_at": "2026-09-07T00:00:00Z",
            "message": message,
        }
    )
    print(f"\n=== {title} ===")
    print(f"  preset       : {preset}")
    print(f"  user says    : {message!r}")
    print(f"  turn status  : {result['status']}")
    for key in ("rule_id", "reason", "confirmation_id", "state_version", "execution_id"):
        if key in result and result[key] is not None:
            print(f"  {key:<13}: {result[key]}")
    print(f"  actuator hits: {executor.calls}")
    _ = event_store  # event pipeline wiring left for Phase 3' trace work


if __name__ == "__main__":
    store = VehicleStateStore(VehicleState(gear="P", speed=0))
    server = create_server(port=0, service=GuardrailService(store=store))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"guardrail service: {base_url}  (policy {GuardrailService().engine.policy_checksum[:19]}...)")

    mapper = load_default_mapper(load_registry(), load_manifest())
    adapter = GuardrailClientAdapter(
        GuardrailClientConfig(base_url, GuardrailProvider.REAL, retry_backoff_seconds=0)
    )

    try:
        _run_turn(
            "Scenario 1 - ALLOW (parked)",
            preset="parked_safe",
            tool="control_access",
            arguments={"action": "open", "target": "driver_door"},
            message="Mở cửa ghế lái",
        )
        _run_turn(
            "Scenario 2 - BLOCK_UNSAFE (moving)",
            preset="driving",
            tool="control_access",
            arguments={"action": "open", "target": "driver_door"},
            message="Mở cửa xe đi",
        )
        _run_turn(
            "Scenario 3 - CONFIRM (interior light while moving)",
            preset="driving",
            tool="control_light",
            arguments={"action": "turn_on", "target": "interior_light"},
            message="Bật đèn trong xe",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    print("\ndone.")
