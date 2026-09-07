"""Phase 2' — GATE 2'.1.

The Agent's real ``GuardrailClientAdapter(REAL)`` talks to our live HTTP service
(in-process ``ThreadingHTTPServer``) and the two acceptance criteria hold over
the wire:

  AC-9   open_door, parked  -> ALLOW + a permit bound to the exact proposal
  AC-10  open_door, moving  -> BLOCK_UNSAFE, no permit

The adapter itself enforces digest binding and proposal-id correlation and
raises ``GuardrailAdapterError`` (never authorizes) on any mismatch, so a green
run here means the contract holds end to end.
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

# vivi-agent path + `src` shim are set up by tests/conftest.py.
if not (_REPO / "vivi-agent" / "src").is_dir():  # pragma: no cover
    pytest.skip("vivi-agent not present", allow_module_level=True)

from policy import VehicleState  # noqa: E402
from service.http import create_server  # noqa: E402
from service.app import GuardrailService  # noqa: E402
from service.state_store import VehicleStateStore  # noqa: E402

from vivi_agent.adapters.guardrail import (  # noqa: E402
    GuardrailAdapterError,
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)

_PROPOSAL = json.loads(
    (_REPO / "vivi-agent/src/vivi_agent/integrations/viguard/wire/examples.json").read_text(
        encoding="utf-8"
    )
)["action_proposal"]


@pytest.fixture
def wired():
    store = VehicleStateStore(VehicleState(gear="P", speed=0))
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
    try:
        yield store, adapter
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=2)


def test_ac9_open_door_parked_allows_with_bound_permit(wired):
    store, adapter = wired
    store.apply_preset("parked_safe")
    result = adapter.evaluate(json.loads(json.dumps(_PROPOSAL)))
    assert result["kind"] == "decision"
    assert result["outcome"] == "ALLOW"
    assert result["intent"] == "open_door"
    assert result["permit"]["single_use"] is True
    # adapter already verified permit.proposal_digest == proposal_digest(proposal)


def test_ac10_open_door_moving_blocks_with_no_permit(wired):
    store, adapter = wired
    store.apply_preset("driving")
    result = adapter.evaluate(json.loads(json.dumps(_PROPOSAL)))
    assert result["kind"] == "decision"
    assert result["outcome"] == "BLOCK_UNSAFE"
    assert "permit" not in result


def test_state_change_between_calls_flips_the_decision(wired):
    store, adapter = wired
    store.apply_preset("parked_safe")
    assert adapter.evaluate(json.loads(json.dumps(_PROPOSAL)))["outcome"] == "ALLOW"
    store.apply_preset("driving")
    assert adapter.evaluate(json.loads(json.dumps(_PROPOSAL)))["outcome"] == "BLOCK_UNSAFE"


def test_unsupported_tool_call_never_authorizes(wired):
    store, adapter = wired
    bad = json.loads(json.dumps(_PROPOSAL))
    bad["arguments"] = {"action": "open", "target": "passenger_door"}
    result = adapter.evaluate(bad)
    # server replies 422 + typed error; adapter surfaces it as a non-authorizing envelope
    assert result["kind"] == "error"
    assert result["error"]["code"] == "UNSUPPORTED_TOOL_MAPPING"
