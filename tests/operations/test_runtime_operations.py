from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import threading
import json

import pytest

from vivi_agent.authorization import authorization_request_digest
from vivi_agent.operations import HealthRegistry, OperationsEndpoint, RuntimeOperations, RuntimeResetError, UIConnectionRegistry
from vivi_agent.vehicle.execution import HandlerRegistry, InvalidPermitError, PermitStore, PermitVerifier, VehicleToolGateway


NOW = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)


class FakeEvents:
    def __init__(self) -> None:
        self.streams = {"s1": [{"sequence": 1}, {"sequence": 2}], "s2": [{"sequence": 1}]}

    def clear(self, session_id=None):
        if session_id is None:
            self.streams.clear()
        else:
            self.streams.pop(session_id, None)

    def get_events(self, session_id, since_sequence=0):
        return [event.copy() for event in self.streams.get(session_id, ()) if event["sequence"] > since_sequence]


class FakeActions:
    def __init__(self) -> None:
        self.sessions = ["s1", "s2"]

    def reset_and_cleanup(self, session_id=None):
        stopped = [value for value in self.sessions if session_id is None or value == session_id]
        self.sessions = [value for value in self.sessions if value not in stopped]
        return stopped


class FakeConfirmations:
    def __init__(self) -> None:
        self.sessions = ["s1", "s2"]

    def cancel_pending_for_reset(self, session_id=None):
        cancelled = [value for value in self.sessions if session_id is None or value == session_id]
        self.sessions = [value for value in self.sessions if value not in cancelled]
        return len(cancelled)


@dataclass
class SimulationResult:
    success: bool = True
    error: str | None = None


class FakeSimulation:
    def __init__(self) -> None:
        self.calls = 0

    def reset(self, **_kwargs):
        self.calls += 1
        return SimulationResult()


def make_runtime():
    events = FakeEvents()
    ui = UIConnectionRegistry(events)
    permits = PermitStore()
    simulation = FakeSimulation()
    runtime = RuntimeOperations(active_actions=FakeActions(), confirmations=FakeConfirmations(),
        permit_store=permits, agent_events=events, ui_connections=ui,
        simulation=simulation, clock=lambda: NOW)
    return runtime, events, ui, permits, simulation


def test_session_reset_revokes_old_permits_and_preserves_other_sessions():
    runtime, events, _ui, permits, simulation = make_runtime()
    result = runtime.reset("session", session_id="s1")

    assert result.stopped_actions == result.cancelled_confirmations == 1
    assert not result.vehicle_reset
    assert "s1" not in events.streams and "s2" in events.streams
    assert permits.is_revoked("s1", NOW - timedelta(seconds=1))
    assert not permits.is_revoked("s2", NOW - timedelta(seconds=1))
    assert simulation.calls == 0


def test_verifier_rejects_an_unconsumed_permit_issued_before_reset():
    proposal = {
        "contract_version": "1.0.0",
        "proposal_id": "proposal-before-reset",
        "session_id": "s1",
        "source_turn_id": "turn-1",
        "tool": "control_access",
        "arguments": {"action": "open", "target": "driver_door"},
        "model_provider": "openai",
        "model_id": "test-model",
    }
    issued_at = NOW - timedelta(seconds=1)
    permit = {
        "permit_id": "permit-before-reset",
        "proposal_digest": authorization_request_digest(proposal),
        "intent": "open_door",
        "rule_id": "R001",
        "state_version": 1,
        "policy_checksum": "sha256:" + "a" * 64,
        "issued_at": issued_at.isoformat(),
        "expires_at": (NOW + timedelta(minutes=1)).isoformat(),
        "single_use": True,
    }
    store = PermitStore()
    store.revoke_before(NOW, "s1")

    with pytest.raises(InvalidPermitError, match="revoked by runtime reset"):
        PermitVerifier(store).verify(proposal, permit, current_time=NOW)


def test_all_reset_cleans_agent_and_resets_vehicle():
    runtime, events, _ui, permits, simulation = make_runtime()
    result = runtime.reset("all")

    assert result.stopped_actions == result.cancelled_confirmations == 2
    assert result.vehicle_reset and not events.streams and simulation.calls == 1
    assert permits.is_revoked("any-session", NOW)


def test_simulator_reset_invalidates_all_snapshot_dependent_state():
    runtime, events, _ui, permits, simulation = make_runtime()
    result = runtime.reset("simulator")

    assert result.stopped_actions == result.cancelled_confirmations == 2
    assert result.vehicle_reset and not events.streams and simulation.calls == 1
    assert permits.is_revoked("any-session", NOW)


def test_reset_waits_for_in_flight_gateway_execution():
    runtime, _events, _ui, permits, _simulation = make_runtime()
    handler_started = threading.Event()
    release_handler = threading.Event()
    reset_finished = threading.Event()
    reset_entered = threading.Event()

    def handler(_proposal):
        handler_started.set()
        assert release_handler.wait(timeout=2)
        return {"state_version": 2, "message": "done"}

    registry = HandlerRegistry()
    registry.register("control_access", handler)
    gateway = VehicleToolGateway(PermitVerifier(permits), registry)
    proposal = {
        "contract_version": "1.0.0", "proposal_id": "proposal-race",
        "session_id": "s1", "source_turn_id": "turn-race",
        "tool": "control_access", "arguments": {"action": "open", "target": "driver_door"},
        "model_provider": "openai", "model_id": "test-model",
    }
    permit = {
        "permit_id": "permit-race", "proposal_digest": authorization_request_digest(proposal),
        "intent": "open_door", "rule_id": "R001", "state_version": 1,
        "policy_checksum": "sha256:" + "a" * 64,
        "issued_at": (NOW - timedelta(seconds=1)).isoformat(),
        "expires_at": (NOW + timedelta(minutes=1)).isoformat(), "single_use": True,
    }

    execution = threading.Thread(target=lambda: gateway.execute(proposal, permit, current_time=NOW))
    def run_reset():
        reset_entered.set()
        runtime.reset("session", session_id="s1")
        reset_finished.set()

    reset = threading.Thread(target=run_reset)
    execution.start()
    assert handler_started.wait(timeout=2)
    reset.start()
    assert reset_entered.wait(timeout=2)
    assert not reset_finished.is_set()
    release_handler.set()
    execution.join(timeout=2)
    reset.join(timeout=2)
    assert reset_finished.is_set()


def test_vehicle_reset_failure_raises_typed_error():
    runtime, _events, _ui, _permits, simulation = make_runtime()
    simulation.reset = lambda **_kwargs: SimulationResult(False, "vehicle offline")

    with pytest.raises(RuntimeResetError) as raised:
        runtime.reset("simulator")

    assert raised.value.to_dict() == {
        "code": "VEHICLE_RESET_FAILED",
        "scope": "simulator",
        "reason": "vehicle offline",
    }


def test_ui_reconnect_returns_only_unacknowledged_events():
    _runtime, _events, ui, _permits, _simulation = make_runtime()
    ui.acknowledge("s1", "browser-1", 1)

    result = ui.reconnect("s1", "browser-1")

    assert [event["sequence"] for event in result.events] == [2]
    assert result.next_sequence == 2


def test_readiness_names_unavailable_dependencies():
    health = HealthRegistry()
    health.report("model", True)
    health.report("authorization", False, "timeout")
    health.report("ui", True)

    snapshot = health.snapshot()
    assert snapshot["live"] is True and snapshot["ready"] is False
    assert snapshot["unavailable_dependencies"] == ("authorization",)


def test_operations_endpoint_exposes_contract_valid_reset_and_health():
    runtime, _events, ui, _permits, _simulation = make_runtime()
    health = HealthRegistry()
    for dependency in ("model", "authorization", "ui"):
        health.report(dependency, True)
    endpoint = OperationsEndpoint(runtime, health, ui, clock=lambda: NOW)

    response = endpoint.post_reset({
        "contract_version": "1.1.0", "kind": "request", "request_type": "reset",
        "session_id": "s1", "request_id": "reset-1",
        "occurred_at": NOW.isoformat().replace("+00:00", "Z"), "scope": "session",
    })

    assert response["status"] == "completed" and response["turn_id"] == "reset-1"
    assert endpoint.get_health()["ready"] is True
    json.dumps(endpoint.get_health())
    json.dumps(endpoint.reconnect("s1", "browser-1"))
