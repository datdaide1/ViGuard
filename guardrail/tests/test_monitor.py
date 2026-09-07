"""the HTTP layer — : Monitor path over the real contract.

  AC-19  a monitored action is active, a monitor rule fires a block ->
         the decision is that block outcome + its rule_id (fail-safe stop)

Plus: "no monitor rule triggers" and "an explicit monitor ALLOW" both read as
"keep running" (``outcome == 'ALLOW'``) to the Agent's monitor adapter; a
non-monitored intent and any engine fail-closed become a typed error, which the
adapter turns into a fail-safe stop.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_REPO = _ROOT.parent
sys.path.insert(0, str(_ROOT))

if not (_REPO / "agent" / "src").is_dir():  # pragma: no cover
    pytest.skip("agent not present", allow_module_level=True)

from policy import RuleSet, VehicleState  # noqa: E402
from service.active_actions import MONITORED_INTENTS  # noqa: E402
from service.app import GuardrailService  # noqa: E402
from service.http import create_server  # noqa: E402
from service.state_store import VehicleStateStore  # noqa: E402

from vehicle_agent.adapters.guardrail import (  # noqa: E402
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)
from vehicle_agent.catalog.manifest import MONITORED_INTENTS as AGENT_MONITORED  # noqa: E402


def _wire(state: VehicleState):
    store = VehicleStateStore(state)
    srv = create_server(port=0, service=GuardrailService(store=store))
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    adapter = GuardrailClientAdapter(
        GuardrailClientConfig(
            f"http://127.0.0.1:{srv.server_address[1]}",
            GuardrailProvider.REAL,
            retry_backoff_seconds=0,
        )
    )
    return store, adapter, srv, thread


def _payload(active_action_id: str, intent: str) -> dict:
    return {
        "contract_version": "1.0.0",
        "request_id": f"req-mon-{active_action_id}",
        "active_action_id": active_action_id,
        "intent": intent,
    }


@pytest.fixture
def factory():
    servers = []

    def _make(state: VehicleState):
        store, adapter, srv, thread = _wire(state)
        servers.append((srv, thread))
        return store, adapter

    yield _make
    for srv, thread in servers:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=2)


def test_monitored_intent_sets_match_the_workbook():
    workbook_monitor = {r.intent for r in RuleSet.load().all() if r.check_mode == "monitor"}
    assert MONITORED_INTENTS == workbook_monitor == set(AGENT_MONITORED)


def test_ac19_monitor_rule_fires_a_block_with_rule_id(factory):
    _store, adapter = factory(VehicleState(hand_off_wheel_duration_seconds=20))
    result = adapter.evaluate_monitor(_payload("hda-1", "activate_hda"))
    assert result["kind"] == "decision"
    assert result["outcome"] == "BLOCK_UNSAFE"
    assert result["rule_id"] == "R073"
    assert "permit" not in result


def test_low_battery_stops_camp_mode(factory):
    _store, adapter = factory(VehicleState(battery_pct=10))
    result = adapter.evaluate_monitor(_payload("camp-1", "activate_campmode"))
    assert result["outcome"] == "BLOCK_UNAVAILABLE"
    assert result["rule_id"] == "R033"


def test_no_trigger_reads_as_keep_running(factory):
    _store, adapter = factory(VehicleState(hand_off_wheel_duration_seconds=0))
    result = adapter.evaluate_monitor(_payload("hda-2", "activate_hda"))
    assert result["outcome"] == "ALLOW"  # adapter: ALLOW == keep running


def test_explicit_monitor_allow_reads_as_keep_running(factory):
    _store, adapter = factory(VehicleState(acc_state="ACTIVE", speed=0))
    result = adapter.evaluate_monitor(_payload("aac-1", "activate_aac"))
    assert result["outcome"] == "ALLOW"
    assert result["rule_id"] == "R070"


def test_wrong_typed_vehicle_state_field_is_a_typed_400_not_a_crash(factory):
    _store, adapter = factory(VehicleState())
    payload = _payload("hda-bad", "activate_hda")
    payload["vehicle_state"] = {"speed": "fast"}  # wrong JSON type
    result = adapter.evaluate_monitor(payload)
    assert result["kind"] == "error"
    assert result["error"]["code"] == "INVALID_VEHICLE_STATE"


def test_unknown_vehicle_state_field_is_a_typed_400(factory):
    _store, adapter = factory(VehicleState())
    payload = _payload("hda-bad2", "activate_hda")
    payload["vehicle_state"] = {"speeed": 10}
    result = adapter.evaluate_monitor(payload)
    assert result["kind"] == "error"
    assert result["error"]["code"] == "INVALID_VEHICLE_STATE"


def test_non_monitored_intent_is_typed_error(factory):
    _store, adapter = factory(VehicleState())
    result = adapter.evaluate_monitor(_payload("door-1", "open_door"))
    assert result["kind"] == "error"
    assert result["error"]["code"] == "NOT_A_MONITORED_INTENT"


def test_agent_supplied_vehicle_state_is_honoured(factory):
    store, adapter = factory(VehicleState())  # store says hands-on-wheel
    payload = _payload("hda-3", "activate_hda")
    payload["vehicle_state"] = {"hand_off_wheel_duration_seconds": 30}
    result = adapter.evaluate_monitor(payload)
    assert result["outcome"] == "BLOCK_UNSAFE"  # used the agent snapshot, not the store


def test_active_action_registry_tracks_authorized_monitored_actions():
    base = json.loads(
        (_REPO / "agent/src/vehicle_agent/integrations/aegis/wire/examples.json").read_text(
            encoding="utf-8"
        )
    )["action_proposal"]
    svc = GuardrailService(store=VehicleStateStore(VehicleState(gear="P", speed=0)))
    proposal = {
        **base,
        "proposal_id": "autopark-run",
        "tool": "control_driver_assistance",
        "arguments": {"action": "activate", "target": "auto_park"},
    }
    status, body = svc.handle("/v1/evaluate/action", proposal)
    assert status == 200 and body["outcome"] == "ALLOW"
    assert svc.active_actions.is_active("autopark-run")
    # a monitor stop deregisters it
    svc.handle("/v1/monitor/evaluate", {
        "contract_version": "1.0.0", "request_id": "r", "active_action_id": "autopark-run",
        "intent": "activate_autopark", "vehicle_state": {"autopark_state": "ACTIVE", "speed": 40},
    })
    assert not svc.active_actions.is_active("autopark-run")
