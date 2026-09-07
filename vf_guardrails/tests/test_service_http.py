"""Phase 2' 2'.1 — HTTP contract layer: routing, status codes, fail-closed."""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_REPO = _ROOT.parent
sys.path.insert(0, str(_ROOT))

from policy import VehicleState  # noqa: E402
from service.app import GuardrailService  # noqa: E402
from service.envelope import proposal_digest  # noqa: E402
from service.http import create_server  # noqa: E402
from service.state_store import VehicleStateStore  # noqa: E402

_EXAMPLES = json.loads(
    (_REPO / "vivi-agent/src/vivi_agent/integrations/viguard/wire/examples.json").read_text(
        encoding="utf-8"
    )
)


def _proposal(**over):
    p = json.loads(json.dumps(_EXAMPLES["action_proposal"]))
    p.update(over)
    return p


@pytest.fixture
def server():
    store = VehicleStateStore(VehicleState(gear="P", speed=0))
    srv = create_server(port=0, service=GuardrailService(store=store))
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    srv.store = store  # test handle
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=2)


def _post(srv, path, payload):
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.server_address[1]}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


# --------------------------------------------------------------------- action
def test_action_parked_returns_allow_with_bound_permit(server):
    status, body = _post(server, "/v1/evaluate/action", _proposal())
    assert status == 200
    assert body["outcome"] == "ALLOW"
    assert body["proposal_id"] == _EXAMPLES["action_proposal"]["proposal_id"]
    assert body["permit"]["proposal_digest"] == proposal_digest(_EXAMPLES["action_proposal"])
    assert body["permit"]["single_use"] is True
    for f in ("intent", "rule_id", "state_version", "policy_checksum"):
        assert body["permit"][f] == body[f]


def test_action_moving_returns_block_without_permit(server):
    server.store.apply_preset("driving")
    status, body = _post(server, "/v1/evaluate/action", _proposal())
    assert status == 200
    assert body["outcome"] == "BLOCK_UNSAFE"
    assert "permit" not in body


def test_contract_version_mismatch_is_409_typed_error(server):
    status, body = _post(server, "/v1/evaluate/action", _proposal(contract_version="0.9.0"))
    assert status == 409
    assert body["kind"] == "error"
    assert body["error"]["code"] == "CONTRACT_VERSION_MISMATCH"
    assert "permit" not in body


def test_malformed_proposal_is_400_typed_error(server):
    bad = _proposal()
    bad.pop("session_id")
    status, body = _post(server, "/v1/evaluate/action", bad)
    assert status == 400
    assert body["kind"] == "error"


def test_unsupported_tool_mapping_fails_closed(server):
    bad = _proposal(arguments={"action": "open", "target": "passenger_door"})
    status, body = _post(server, "/v1/evaluate/action", bad)
    assert status == 422
    assert body["error"]["code"] == "UNSUPPORTED_TOOL_MAPPING"


def test_unknown_route_is_404(server):
    status, body = _post(server, "/v1/evaluate/nope", _proposal())
    assert status == 404
    assert body["error"]["code"] == "ROUTE_NOT_FOUND"


def test_confirm_and_monitor_routes_reject_missing_fields(server):
    for path, code in (
        ("/v1/confirmations/confirm", "INVALID_CONFIRMATION"),
        ("/v1/monitor/evaluate", "INVALID_MONITOR_REQUEST"),
    ):
        status, body = _post(server, path, {"contract_version": "1.0.0", "request_id": "r1"})
        assert status == 400
        assert body["error"]["code"] == code


def test_invalid_json_body_is_400(server):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}/v1/evaluate/action",
        data=b"{not json",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=2)
        raise AssertionError("expected HTTP 400")
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        assert json.loads(exc.read())["error"]["code"] == "INVALID_JSON"


def test_healthz(server):
    with urllib.request.urlopen(
        f"http://127.0.0.1:{server.server_address[1]}/healthz", timeout=2
    ) as resp:
        assert json.loads(resp.read())["status"] == "ok"


# --------------------------------------------------------------------- query
def test_query_path_answers_from_state(server):
    payload = {
        "contract_version": "1.0.0",
        "request_id": "q-1",
        "tool": "query_vehicle_state",
        "arguments": {"action": "get", "target": "current_speed"},
    }
    status, body = _post(server, "/v1/evaluate/query", payload)
    assert status == 200
    assert body["intent"] == "get_current_speed"
    assert "permit" not in body


# --------------------------------------------------------------- state store
def test_state_version_increments_and_snapshot_is_stable():
    store = VehicleStateStore(VehicleState(gear="P"))
    s1, v1 = store.snapshot()
    store.mutate(speed=30)
    s2, v2 = store.snapshot()
    assert v2 == v1 + 1
    assert s1.speed == 0 and s2.speed == 30
    assert store.apply_preset("low_battery")[1] == v2 + 1
