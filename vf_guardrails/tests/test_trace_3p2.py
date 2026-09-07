"""Phase 3' 3'.2 — Guardrail request trace (PRD FR-14 / §16)."""
from __future__ import annotations

import copy
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
from service.http import create_server  # noqa: E402
from service.state_store import VehicleStateStore  # noqa: E402
from service.trace import EVENT_TYPES, TraceRecorder  # noqa: E402

_EXAMPLES = json.loads(
    (_REPO / "vivi-agent/src/vivi_agent/integrations/viguard/wire/examples.json").read_text(
        encoding="utf-8"
    )
)


def _proposal(**over):
    p = copy.deepcopy(_EXAMPLES["action_proposal"])
    p.update(over)
    return p


def _svc(state: VehicleState) -> GuardrailService:
    return GuardrailService(store=VehicleStateStore(state))


# --------------------------------------------------------------- event stream
def test_action_trace_has_the_full_stage_sequence():
    svc = _svc(VehicleState(gear="P", speed=0))
    p = _proposal(proposal_id="t-allow")
    svc.handle("/v1/evaluate/action", p)
    trace = svc.trace.get("t-allow")
    assert [e["event_type"] for e in trace["events"]] == [
        "guardrail_started", "tool_mapped", "constraint_evaluated", "guardrail_completed"
    ]
    for e in trace["events"]:
        assert e["session_id"] == p["session_id"]
        assert e["policy_checksum"] == svc.engine.policy_checksum
        assert e["timestamp"] and e["stage"]
    assert trace["events"][-1]["end_to_end_ms"] >= 0
    assert trace["events"][-1]["http_status"] == 200


def test_block_still_completes_the_trace():
    svc = _svc(VehicleState(gear="D", speed=50))
    svc.handle("/v1/evaluate/action", _proposal(proposal_id="t-block"))
    ev = svc.trace.get("t-block")["events"]
    assert ev[-1]["event_type"] == "guardrail_completed"
    assert ev[-1]["outcome"] == "BLOCK_UNSAFE"
    assert any(e["event_type"] == "constraint_evaluated" and e["rule_id"] == "R002" for e in ev)


def test_mapping_failure_is_traced_as_error():
    svc = _svc(VehicleState())
    svc.handle("/v1/evaluate/action", _proposal(proposal_id="t-badmap",
               arguments={"action": "open", "target": "passenger_door"}))
    ev = svc.trace.get("t-badmap")["events"]
    assert any(e["event_type"] == "mapping_failed" for e in ev)
    assert ev[-1]["event_type"] == "guardrail_error"
    assert ev[-1]["error_code"] == "UNSUPPORTED_TOOL_MAPPING"


def test_confirm_trace_records_the_confirmation_lifecycle():
    store = VehicleStateStore(VehicleState(gear="D", speed=40))
    svc = GuardrailService(store=store)
    p = _proposal(proposal_id="t-cfm", tool="control_light",
                  arguments={"action": "turn_on", "target": "interior_light"})
    _, body = svc.handle("/v1/evaluate/action", p)
    cid = body["confirmation"]["confirmation_id"]
    assert any(e["event_type"] == "confirmation_requested" for e in svc.trace.get("t-cfm")["events"])

    store.mutate(speed=0)
    svc.handle("/v1/confirmations/confirm",
               {"contract_version": "1.0.0", "request_id": "t-cfm-r",
                "confirmation_id": cid, "session_id": p["session_id"]})
    ev = svc.trace.get("t-cfm-r")["events"]
    assert any(e["event_type"] == "confirmation_resolved" for e in ev)
    assert ev[-1]["event_type"] == "guardrail_completed"


def test_monitor_trace_records_monitor_evaluated():
    svc = _svc(VehicleState(hand_off_wheel_duration_seconds=20))
    svc.handle("/v1/monitor/evaluate", {"contract_version": "1.0.0", "request_id": "t-mon",
               "active_action_id": "a1", "intent": "activate_hda"})
    ev = svc.trace.get("t-mon")["events"]
    assert any(e["event_type"] == "monitor_evaluated" and e["rule_id"] == "R073" for e in ev)


def test_no_secrets_or_prompts_in_events():
    svc = _svc(VehicleState())
    svc.handle("/v1/evaluate/action", _proposal(proposal_id="t-sec"))
    blob = json.dumps(svc.trace.get("t-sec"))
    for banned in ("system prompt", "password", "api_key", "authorization"):
        assert banned not in blob.lower()


# --------------------------------------------------------------- recorder unit
def test_recorder_rejects_unknown_event_type():
    rec = TraceRecorder()
    rec.begin("r1", "s1", "/x")
    with pytest.raises(ValueError):
        rec.record("r1", "not_a_real_event", stage="x")


def test_recorder_capacity_evicts_oldest():
    rec = TraceRecorder(capacity=2)
    for i in range(4):
        rec.begin(f"r{i}", "s", "/x")
    assert rec.get("r0") is None and rec.get("r1") is None
    assert rec.get("r3") is not None


def test_all_recorded_event_types_are_declared():
    svc = _svc(VehicleState())
    svc.handle("/v1/evaluate/action", _proposal(proposal_id="t-decl"))
    for e in svc.trace.get("t-decl")["events"]:
        assert e["event_type"] in EVENT_TYPES


# --------------------------------------------------------------- HTTP read-back
def test_trace_endpoint_returns_the_trace_over_http():
    store = VehicleStateStore(VehicleState(gear="P", speed=0))
    srv = create_server(port=0, service=GuardrailService(store=store))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        req = urllib.request.Request(
            f"{base}/v1/evaluate/action",
            data=json.dumps(_proposal(proposal_id="http-tr")).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=2).read()
        with urllib.request.urlopen(f"{base}/v1/trace/http-tr", timeout=2) as resp:
            trace = json.loads(resp.read())
        assert trace["request_id"] == "http-tr"
        assert trace["events"][-1]["event_type"] == "guardrail_completed"
        try:
            urllib.request.urlopen(f"{base}/v1/trace/nope", timeout=2)
            raise AssertionError("expected 404")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=2)
