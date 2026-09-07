"""run_both.py -- boot the ViGuard Guardrail service + the ViVi Agent and walk
the full outcome set end to end (Phase 2'/3' demo).

    py -3 run_both.py

Two separate services (decision D1) in one process for demo convenience:
  * the Guardrail HTTP service (``vf_guardrails.service``) on a loopback port, in
    a background thread, with its request trace enabled;
  * an ``AgentOrchestrator`` wired to the Agent's real
    ``GuardrailClientAdapter(REAL)`` pointing at that port.

For each scenario it prints the Agent turn trace, the Guardrail request trace
(PRD FR-14 / §16), and the end-to-end latency. No mock Guardrail anywhere.

*** MÔ PHỎNG — không phải xe thật, không có xác nhận an toàn của OEM ***
"""
from __future__ import annotations

import sys
import time
import threading
from pathlib import Path

_REPO = Path(__file__).resolve().parent
for _p in (str(_REPO / "vivi-agent" / "src"), str(_REPO / "vivi-agent")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from vivi_agent.adapters.guardrail import (  # noqa: E402
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)
from vivi_agent.catalog import load_manifest  # noqa: E402
from vivi_agent.model_providers import ModelActionProposal, ProviderMetadata  # noqa: E402
from vivi_agent.orchestrator import AgentOrchestrator, MessageEndpoint  # noqa: E402
from vivi_agent.tools.mapping import load_default_mapper  # noqa: E402
from vivi_agent.tools.registry import load_registry  # noqa: E402
from vivi_agent.vehicle.execution import VehicleToolGateway, make_open_door_handler  # noqa: E402
from vivi_agent.vehicle.state import VehicleStateMachine  # noqa: E402

sys.path.insert(0, str(_REPO / "vf_guardrails"))
from policy import VehicleState  # noqa: E402
from service.app import GuardrailService  # noqa: E402
from service.http import create_server  # noqa: E402
from service.state_store import VehicleStateStore  # noqa: E402

_META = ProviderMetadata(provider="openai", model_id="gpt-5-mini", config_checksum="sha256:demo", latency_ms=5)
_BANNER = "*** MÔ PHỎNG — không phải xe thật, không có xác nhận an toàn của OEM ***"


class ScriptedRouter:
    def __init__(self, tool: str, arguments: dict) -> None:
        self._proposal = ModelActionProposal.action(tool, arguments, _META)

    def propose_tool(self, messages, turn):  # noqa: ANN001
        turn.record_proposal(self._proposal)
        return self._proposal

    def compose_response(self, facts, turn):  # noqa: ANN001
        return ModelActionProposal.response("Đã xử lý yêu cầu (mô phỏng).", _META)


class GatewayExecutor:
    def __init__(self, gateway: VehicleToolGateway) -> None:
        self._gateway = gateway
        self.calls = 0

    def execute(self, proposal, decision, cancellation):  # noqa: ANN001
        self.calls += 1
        return self._gateway.execute(proposal, decision, cancellation)


def _print_guardrail_trace(svc: GuardrailService, request_id: str) -> None:
    trace = svc.trace.get(request_id)
    if trace is None:
        print("    guardrail trace: (none)")
        return
    print(f"    guardrail trace  [{trace['route']}]  end_to_end={trace['events'][-1].get('end_to_end_ms', '?')} ms")
    for e in trace["events"]:
        extra = {
            k: e[k]
            for k in ("intent", "outcome", "rule_id", "reason_code", "monitor_outcome",
                      "confirmation_id", "reevaluated_outcome", "error_code", "http_status")
            if k in e and e[k] is not None
        }
        print(f"      · {e['event_type']:<22} {e['stage']:<13} {extra}")


def _slug(title: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in title.split("(")[0].strip().lower())[:20].strip("-")


def _run_turn(svc, store, adapter, mapper, title, *, tool, arguments, message,
              preset=None, mutate=None):
    slug = _slug(title)
    if preset:
        store.apply_preset(preset)
    if mutate:
        store.mutate(**mutate)

    sm = VehicleStateMachine()
    gateway = VehicleToolGateway()
    handler = make_open_door_handler(sm)
    gateway.registry.register("open_door", handler)
    gateway.registry.register("control_access", handler)
    _stub = lambda proposal: {"state_version": 1, "facts": {}, "message": "ok (mô phỏng)"}  # noqa: E731
    for _name in ("control_driver_assistance", "control_light", "activate_autopark", "turnon_interiorlight"):
        gateway.registry.register(_name, _stub)
    executor = GatewayExecutor(gateway)

    endpoint = MessageEndpoint(
        AgentOrchestrator(model_router=ScriptedRouter(tool, arguments), mapper=mapper,
                          guardrail=adapter, executor=executor)
    )
    t0 = time.perf_counter()
    result = endpoint.post_message({
        "contract_version": "1.0.0", "kind": "request", "request_type": "message",
        "session_id": f"sess-{slug}", "turn_id": f"turn-{slug}",
        "request_id": f"req-{slug}", "occurred_at": "2026-09-07T00:00:00Z",
        "message": message,
    })
    wall_ms = round((time.perf_counter() - t0) * 1000, 2)

    print(f"\n=== {title} ===")
    print(f"    user           : {message!r}")
    print(f"    agent turn      : {result['status']}")
    for k in ("rule_id", "reason", "confirmation_id", "state_version", "execution_id"):
        if result.get(k) is not None:
            print(f"    {k:<15}: {result[k]}")
    print(f"    actuator hits   : {executor.calls}")
    print(f"    end-to-end      : {wall_ms} ms (agent+guardrail, in-process)")
    if result.get("proposal_id"):
        _print_guardrail_trace(svc, result["proposal_id"])
    return result


def main() -> int:
    store = VehicleStateStore(VehicleState(gear="P", speed=0))
    svc = GuardrailService(store=store)
    server = create_server(port=0, service=svc)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    mapper = load_default_mapper(load_registry(), load_manifest())
    adapter = GuardrailClientAdapter(
        GuardrailClientConfig(base_url, GuardrailProvider.REAL, retry_backoff_seconds=0)
    )

    print(_BANNER)
    print(f"guardrail: {base_url}   policy {svc.engine.policy_checksum[:19]}...")

    try:
        _run_turn(svc, store, adapter, mapper, "ALLOW (đỗ xe)",
                  tool="control_access", arguments={"action": "open", "target": "driver_door"},
                  message="Mở cửa ghế lái", preset="parked_safe")

        _run_turn(svc, store, adapter, mapper, "BLOCK_UNSAFE (đang chạy)",
                  tool="control_access", arguments={"action": "open", "target": "driver_door"},
                  message="Mở cửa xe đi", preset="driving")

        confirm = _run_turn(svc, store, adapter, mapper, "CONFIRM (đèn nội thất khi chạy)",
                            tool="control_light", arguments={"action": "turn_on", "target": "interior_light"},
                            message="Bật đèn trong xe", preset="driving")
        cid = confirm.get("confirmation_id")
        if cid:
            store.mutate(speed=0)  # driver stops, then confirms
            resolved = adapter.confirm(cid, session_id=f"sess-{_slug('CONFIRM')}", request_id="req-confirm-c")
            print(f"    -> confirm resolved: {resolved.get('outcome')}  (permit={'yes' if 'permit' in resolved else 'no'})")
            _print_guardrail_trace(svc, "req-confirm-c")

        _run_turn(svc, store, adapter, mapper, "ANSWER (hỏi tốc độ)",
                  tool="query_vehicle_state", arguments={"action": "get", "target": "current_speed"},
                  message="Xe đang chạy bao nhiêu?", mutate={"speed": 32})

        # MONITOR: authorize an autopark, then a monitor tick with a bad state.
        _run_turn(svc, store, adapter, mapper, "MONITOR setup (activate autopark)",
                  tool="control_driver_assistance", arguments={"action": "activate", "target": "auto_park"},
                  message="Bật tự động đỗ xe", preset="parked_safe")
        mon = adapter.evaluate_monitor({
            "contract_version": "1.0.0", "request_id": "req-MON", "active_action_id": "autopark-run",
            "intent": "activate_autopark", "vehicle_state": {"autopark_state": "ACTIVE", "speed": 40},
        })
        print(f"\n=== MONITOR tick (autopark active @ 40 km/h) ===")
        print(f"    monitor outcome : {mon.get('outcome')}  rule={mon.get('rule_id')}")
        _print_guardrail_trace(svc, "req-MON")
    finally:
        server.shutdown()
        server.server_close()
    print(f"\n{_BANNER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
