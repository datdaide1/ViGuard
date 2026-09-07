"""the HTTP layer — : CONFIRM lifecycle over the real contract.

  AC-14  a CONFIRM decision carries no permit (nothing can execute yet)
  AC-15  if state worsens between CONFIRM and confirm -> block, still no permit
  AC-16  a confirmation is single-use: the second confirm is rejected

Driven through the Agent's real ``GuardrailClientAdapter(REAL)`` and, for AC-16,
its ``ConfirmationManager`` too.
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
from service.app import GuardrailService  # noqa: E402
from service.http import create_server  # noqa: E402
from service.state_store import VehicleStateStore  # noqa: E402

from vehicle_agent.adapters.guardrail import (  # noqa: E402
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)
from vehicle_agent.confirmation.manager import ConfirmationManager  # noqa: E402

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
def wired():
    store = VehicleStateStore(VehicleState(gear="D", speed=40))
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


_INTERIOR_LIGHT = ("control_light", {"action": "turn_on", "target": "interior_light"})
_SUNROOF = ("control_cabin", {"action": "open", "target": "sunroof"})


def test_ac14_confirm_decision_has_no_permit(wired):
    _store, adapter = wired
    result = adapter.evaluate(_proposal("p-il-1", *_INTERIOR_LIGHT))
    assert result["outcome"] == "CONFIRM"
    assert "permit" not in result
    conf = result["confirmation"]
    assert conf["single_use"] is True
    assert conf["proposal_id"] == "p-il-1"


def test_ac15_state_worsening_before_confirm_blocks(wired):
    store, adapter = wired
    store.apply_preset("rainy")  # gear D, speed 40, rain -> open_sunroof CONFIRM
    confirm = adapter.evaluate(_proposal("p-sr-1", *_SUNROOF))
    assert confirm["outcome"] == "CONFIRM"
    cid = confirm["confirmation"]["confirmation_id"]

    store.mutate(speed=120)  # now > 80 -> R051 BLOCK_UNSAFE
    result = adapter.confirm(cid, session_id="demo-01", request_id="req-c15")
    assert result["outcome"] == "BLOCK_UNSAFE"
    assert "permit" not in result


def test_ac16_confirmation_is_single_use(wired):
    store, adapter = wired
    confirm = adapter.evaluate(_proposal("p-il-2", *_INTERIOR_LIGHT))
    cid = confirm["confirmation"]["confirmation_id"]

    store.mutate(speed=0)  # parked -> R090 ALLOW on re-eval
    first = adapter.confirm(cid, session_id="demo-01", request_id="req-c16a")
    assert first["outcome"] == "ALLOW"
    assert first["permit"]["single_use"] is True

    second = adapter.confirm(cid, session_id="demo-01", request_id="req-c16b")
    assert second["kind"] == "error"
    assert second["error"]["code"] == "CONFIRMATION_NOT_ACTIVE"
    assert "permit" not in second


def test_unknown_confirmation_id_is_not_active(wired):
    _store, adapter = wired
    result = adapter.confirm("confirm-does-not-exist", session_id="demo-01", request_id="r")
    assert result["kind"] == "error"
    assert result["error"]["code"] == "CONFIRMATION_NOT_ACTIVE"


def test_confirm_from_a_different_session_is_rejected_without_burning_the_token(wired):
    store, adapter = wired
    confirm = adapter.evaluate(_proposal("p-il-x", *_INTERIOR_LIGHT))  # session_id demo-01
    cid = confirm["confirmation"]["confirmation_id"]

    stolen = adapter.confirm(cid, session_id="attacker-session", request_id="req-atk")
    assert stolen["kind"] == "error"
    assert stolen["error"]["code"] == "CONFIRMATION_SESSION_MISMATCH"
    assert "permit" not in stolen

    # the rightful session can still confirm -> token was not consumed
    store.mutate(speed=0)
    ok = adapter.confirm(cid, session_id="demo-01", request_id="req-ok")
    assert ok["outcome"] == "ALLOW"


def test_confirmation_manager_end_to_end_zero_pre_auth_execution(wired):
    store, adapter = wired
    proposal = _proposal("p-il-3", *_INTERIOR_LIGHT)
    confirm = adapter.evaluate(proposal)
    assert confirm["outcome"] == "CONFIRM"

    manager = ConfirmationManager()
    manager.register_pending(confirm, proposal, turn_id="turn-1")

    executed: list = []

    class _Executor:
        def execute(self, prop, decision, cancellation):  # noqa: ANN001
            executed.append(decision["permit"]["permit_id"])
            return {"success": True, "message": "done"}

    store.mutate(speed=0)
    res = manager.confirm(
        confirm["confirmation"]["confirmation_id"],
        session_id="demo-01",
        authorization_client=adapter,
        executor=_Executor(),
        request_id="req-mgr",
    )
    assert res.status == "completed"
    assert len(executed) == 1  # executed exactly once, only after a fresh ALLOW
