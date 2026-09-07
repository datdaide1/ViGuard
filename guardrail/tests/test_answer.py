"""the demo phase 3'.1 — ANSWER / UNKNOWN fact-shaping.

The Guardrail reads the owned state and returns **structured facts**
(``answer={grounded, facts}``); the Agent verbalizes. Query intents reach the
Guardrail through /v1/evaluate/action (that's how the orchestrator routes them),
so the shaping is tested there and through the query endpoint.
"""
from __future__ import annotations

import copy
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

from policy import VehicleState  # noqa: E402
from service.answer_facts import QUERY_FIELD, kb_has_feature, shape_answer  # noqa: E402
from service.app import GuardrailService  # noqa: E402
from service.http import create_server  # noqa: E402
from service.state_store import VehicleStateStore  # noqa: E402

from vehicle_agent.adapters.guardrail import (  # noqa: E402
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)

_BASE = json.loads(
    (_REPO / "agent/src/vehicle_agent/integrations/aegis/wire/examples.json").read_text(
        encoding="utf-8"
    )
)["action_proposal"]


def _proposal(pid: str, tool: str, arguments: dict) -> dict:
    p = copy.deepcopy(_BASE)
    p.update(proposal_id=pid, tool=tool, arguments=arguments)
    return p


@pytest.fixture
def adapter_for():
    servers = []

    def _make(state: VehicleState):
        srv = create_server(port=0, service=GuardrailService(store=VehicleStateStore(state)))
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        servers.append((srv, t))
        return GuardrailClientAdapter(
            GuardrailClientConfig(
                f"http://127.0.0.1:{srv.server_address[1]}",
                GuardrailProvider.REAL,
                retry_backoff_seconds=0,
            )
        )

    yield _make
    for srv, t in servers:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=2)


_QUERY_TOOL = "query_vehicle_state"
_QUERIES = {
    "current_speed": ("get_current_speed", "speed"),
    "battery_percentage": ("get_battery_pct", "battery_pct"),
    "gear": ("get_gear", "gear"),
    "door_lock_status": ("get_door_lock_status", "door_lock_state"),
    "auto_vehicle_hold_status": ("get_avh_status", "avh"),
}


def test_every_state_query_answers_with_its_canonical_field(adapter_for):
    adapter = adapter_for(VehicleState(speed=55, battery_pct=63, gear="D"))
    for target, (intent, field) in _QUERIES.items():
        result = adapter.evaluate(_proposal(f"q-{target}", _QUERY_TOOL, {"action": "get", "target": target}))
        assert result["outcome"] == "ANSWER", target
        assert result["intent"] == intent
        assert result["answer"]["grounded"] is True
        assert field in result["answer"]["facts"]
        assert "permit" not in result


def test_unavailable_field_is_unknown_not_a_guess(adapter_for):
    adapter = adapter_for(VehicleState(battery_pct=None, avh=None))
    for target in ("battery_percentage", "auto_vehicle_hold_status"):
        result = adapter.evaluate(_proposal(f"u-{target}", _QUERY_TOOL, {"action": "get", "target": target}))
        assert result["outcome"] == "UNKNOWN"
        assert result["answer"]["grounded"] is False
        assert "permit" not in result


def test_explain_known_feature_is_grounded(adapter_for):
    adapter = adapter_for(VehicleState())
    result = adapter.evaluate(
        _proposal("e-1", "explain_vehicle_feature", {"action": "explain", "target": "highway_drive_assist"})
    )
    assert result["outcome"] == "ANSWER"
    assert result["intent"] == "explain_feature"
    assert result["answer"]["facts"] == {"feature": "highway_drive_assist", "kb_has_feature": True}


def test_explain_unmapped_feature_fails_closed(adapter_for):
    adapter = adapter_for(VehicleState())
    result = adapter.evaluate(
        _proposal("e-2", "explain_vehicle_feature", {"action": "explain", "target": "teleport_mode"})
    )
    assert result["kind"] == "error"
    assert result["error"]["code"] == "UNSUPPORTED_TOOL_MAPPING"


def test_query_endpoint_matches_action_path_shaping(adapter_for):
    adapter = adapter_for(VehicleState(speed=12))
    result = adapter.evaluate_query(
        {"tool": _QUERY_TOOL, "arguments": {"action": "get", "target": "current_speed"}, "request_id": "q-ep"}
    )
    assert result["outcome"] == "ANSWER"
    assert result["answer"]["facts"] == {"speed": 12}
    assert "permit" not in result


# --------------------------------------------------------------- unit-level
def test_shape_answer_unit():
    st = VehicleState(speed=0, battery_pct=None)
    assert shape_answer("get_current_speed", "ANSWER", st, None, {}) == {
        "grounded": True, "facts": {"speed": 0}
    }
    assert shape_answer("get_battery_pct", "UNKNOWN", st, None, {}) == {
        "grounded": False, "facts": {"battery_pct": None}
    }
    assert shape_answer("open_door", "ALLOW", st, None, {}) is None


def test_kb_has_feature_unit():
    assert kb_has_feature({"target": "pet_mode"}) is True
    assert kb_has_feature({"target": "nope"}) is False
    assert kb_has_feature(None) is False


def test_query_field_map_covers_all_five_state_queries():
    assert set(QUERY_FIELD) == {v[0] for v in _QUERIES.values()}
