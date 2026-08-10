"""SCN-03 — Scenario "Guardrail bảo vệ khi action đang chạy" (Guardrail
protects the vehicle while an action is still running).

Packages the canonical "operator state change stops a running active action"
scenario end-to-end: the Agent has genuinely started ``activate_hda``
(HERO-02) on the highway, the driver then takes their hand off the wheel — a
real ``SimulationController`` (SIM-01) operator control, never a bare
``VehicleStateMachine.apply()`` call — and that alone (no manual monitor tick)
must trigger Guardrail's monitor evaluation and stop HDA, flipping the real
vehicle state, not just an in-memory bookkeeping record.

Scope note, matching SCN-01/SCN-02's own scope notes: ``GroundTruthMonitorGuardrailClient``
below derives ``evaluate_monitor()``'s outcome *genuinely* from the
``hand_on_steeringwheel`` field of the flat PIP snapshot
(``VehicleState.to_guardrail_snapshot()``) in the payload SIM-01/MON-ADP-01
actually send — not a hardcoded outcome — so
``test_operator_state_change_triggers_guardrail_monitor_call`` is a real test
of "the operator's own action is what triggers monitor evaluation," not a
tautology: the same monitor client is queried automatically by
``SimulationController._trigger_monitor`` as a side effect of
``set_driver_attention()``, with no test code ever calling
``GuardrailMonitorAdapter.tick()`` directly.

This is not a new safety mechanism: it is the same wiring HERO-02 already
proved at the integration level (see
``tests/integration/hero/test_hero02_hda_aac.py::test_e2e_monitor_stop_flips_real_vehicle_state``,
which uses a manual ``monitor.tick()``). What this scenario adds:

- The state-change trigger is the *real* SIM-01 path
  (``SimulationController.set_driver_attention`` → ``VehicleStateMachine.apply``
  with ``ActorKind.OPERATOR`` → ``GuardrailMonitorAdapter.on_state_changed``
  automatically), matching how a genuine simulation/demo UI would drive this,
  not a hand-invoked ``monitor.tick()``.
- An explicit assertion that the operator's own state transition carries
  ``ActorKind.OPERATOR`` provenance — distinct from the ``ActorKind.AGENT``
  transition that started HDA and the ``ActorKind.SYSTEM`` transition the
  monitor-triggered stop later produces — so an audit trail can always tell
  "the driver did this" apart from "the Agent did this" apart from "the
  safety system did this" (``test_operator_state_change_has_distinct_provenance``).
- A formal expected event sequence, hand-built via ``AgentEventPipeline``
  (the orchestrator/registry do not emit *validated* events themselves in
  this scenario's fixtures — see the module-level note on ``execution_id``
  below), format-validated against the Agent-UI v1 contract schema, matching
  SCN-01's own event-sequence test.

Note on "qua gateway" (via the gateway) in this scenario's acceptance
criteria: HERO-02's own design notes (``active_driving_assist.py``) already
establish that a monitor-triggered emergency stop deliberately does **not**
round-trip through ``VehicleToolGateway``'s normal permit-issuing boundary —
that would make a fail-safe stop depend on a second live Guardrail call,
exactly the failure mode HERO-02 was built to avoid. "Qua gateway" here means
via the same registered actuation boundary every hero module's stop handler
uses (``ActiveActionRegistry`` stop handler → ``VehicleStateMachine.apply``),
not literally ``VehicleToolGateway.execute()`` — this scenario reuses that
established mechanism rather than inventing a new one.

Acceptance criteria:
- Operator action có provenance riêng.
- State change trigger Guardrail monitor call.
- Agent dừng action qua gateway và phát stop response/event.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Mapping
from unittest.mock import MagicMock

from vivi_agent.active_actions.registry import ActiveActionRegistry
from vivi_agent.adapters.monitor.adapter import GuardrailMonitorAdapter
from vivi_agent.behaviors.catalog import get_behavior_config
from vivi_agent.behaviors.hero import (
    AdasMonitorHeroBehavior,
    make_monitored_hda_aac_handler,
    register_hda_aac_stop_handlers,
)
from vivi_agent.catalog import load_manifest
from vivi_agent.contracts.agent_ui.v1.contract import CONTRACT_VERSION, validate_event_stream
from vivi_agent.contracts.guardrail.v1.contract import CONTRACT_VERSION as GUARDRAIL_CONTRACT_VERSION
from vivi_agent.events import AgentEventPipeline, AgentEventStore
from vivi_agent.model_providers import ModelActionProposal, ProviderMetadata, TurnBinding
from vivi_agent.orchestrator import (
    AgentOrchestrator,
    CancellationToken,
    ExecutionResult,
    TurnRequest,
    TurnStatus,
)
from vivi_agent.simulation import SimulationController, SimulationPresetId, get_simulation_preset
from vivi_agent.tools.mapping import load_default_mapper
from vivi_agent.tools.registry import load_registry
from vivi_agent.vehicle.execution import VehicleToolGateway
from vivi_agent.vehicle.state.events import ActorKind
from vivi_agent.vehicle.state.machine import VehicleStateMachine
from vivi_agent.vehicle.state.model import AccState, VehicleState

_NOW = datetime(2026, 8, 7, 14, 0, 0, tzinfo=timezone.utc)
META = ProviderMetadata("openai", "gpt-4o", "sha256:scn-03-test", 10)
_ZERO_CHECKSUM = "sha256:" + "0" * 64
_HDA_RULE_ID = "R073_HDA_SAFE"
_MONITOR_RULE_ID = "R073_HANDS_OFF"
_HDA_UTTERANCE = "Bật hỗ trợ lái trên cao tốc giúp tôi"
_HDA_PROPOSAL_ARGS = {"action": "activate", "target": "highway_drive_assist"}


class DummyModelRouter:
    """Deterministic model router proposing a single fixed tool call."""

    def __init__(self, tool_name: str, arguments: dict) -> None:
        self.mock_proposal = ModelActionProposal.action(tool_name, arguments, META)

    def propose_tool(self, messages: list[dict[str, str]], binding: TurnBinding) -> ModelActionProposal:
        binding.record_proposal(self.mock_proposal)
        return self.mock_proposal

    def compose_response(self, facts: Mapping[str, Any], turn: TurnBinding) -> ModelActionProposal:
        return ModelActionProposal.response("Phản hồi.", META)


class GroundTruthMonitorGuardrailClient:
    """Guardrail mock genuinely deriving its ``evaluate()``/``evaluate_monitor()``
    outcomes from real state — ``evaluate()`` always ALLOWs the initial
    ``activate_hda`` proposal (the scenario's precondition, not what's under
    test), while ``evaluate_monitor()`` reads the flat ``hand_on_steeringwheel``
    key of ``VehicleState.to_guardrail_snapshot()`` from the payload
    ``GuardrailMonitorAdapter`` actually sends: ALLOW while hands-on, stop
    (BLOCK_UNSAFE) the instant hands come off. Unlike a mock hardcoded to one
    outcome, this one only stops HDA because the operator's own state change
    made it genuinely unsafe.
    """

    def __init__(self, mapper) -> None:
        self.mapper = mapper
        self.evaluate_calls = 0
        self.evaluate_monitor_calls = 0

    def _base_decision(
        self, *, request_id: str, intent: str, rule_id: str, state_version: int
    ) -> dict[str, Any]:
        """Fields shared by every decision this mock returns (both
        ``evaluate()`` and both branches of ``evaluate_monitor()``) — factored
        out so a future field added to one path can't silently drift from
        the others."""
        return {
            "contract_version": GUARDRAIL_CONTRACT_VERSION,
            "kind": "decision",
            "request_id": request_id,
            "intent": intent,
            "rule_id": rule_id,
            "state_version": state_version,
            "policy_checksum": _ZERO_CHECKSUM,
            "relevant_state": {},
        }

    def evaluate(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        self.evaluate_calls += 1
        mapped = self.mapper.map_proposal(proposal)
        decision = self._base_decision(
            request_id=f"req-scn03-eval-{self.evaluate_calls}",
            intent=mapped.canonical_action.intent,
            rule_id=_HDA_RULE_ID,
            state_version=1,
        )
        decision.update(
            proposal_id=proposal["proposal_id"],
            outcome="ALLOW",
            reason_code="PERMITTED",
            permit={
                "permit_id": f"permit-scn03-{self.evaluate_calls}",
                "proposal_digest": mapped.proposal_digest,
                "intent": mapped.canonical_action.intent,
                "rule_id": _HDA_RULE_ID,
                "state_version": 1,
                "policy_checksum": _ZERO_CHECKSUM,
                "issued_at": _NOW.isoformat().replace("+00:00", "Z"),
                "expires_at": "2099-01-01T00:00:00Z",
                "single_use": True,
            },
        )
        return decision

    def evaluate_monitor(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.evaluate_monitor_calls += 1
        vehicle_state = payload.get("vehicle_state") or {}
        # ``vehicle_state`` is VehicleState.to_guardrail_snapshot()'s flat PIP
        # projection (top-level "hand_on_steeringwheel"/"state_version" keys,
        # not nested under "adas") — see vehicle/state/model.py.
        hands_on = bool(vehicle_state.get("hand_on_steeringwheel", True))
        decision = self._base_decision(
            request_id=payload["request_id"],
            intent=payload["intent"],
            rule_id=_MONITOR_RULE_ID,
            state_version=int(vehicle_state.get("state_version", 0)),
        )
        if hands_on:
            decision.update(outcome="ALLOW", reason_code="HANDS_ON_WHEEL")
        else:
            decision.update(outcome="BLOCK_UNSAFE", reason_code="HANDS_OFF_TIMEOUT")
        return decision


class SpyExecutor:
    """Executor proxy passing parameters through to the real gateway."""

    def __init__(self, gateway: VehicleToolGateway) -> None:
        self.gateway = gateway
        self.execution_count = 0

    def execute(
        self,
        proposal: Mapping[str, Any],
        decision: Mapping[str, Any],
        cancellation: CancellationToken,
    ) -> ExecutionResult:
        self.execution_count += 1
        return self.gateway.execute(proposal, decision, cancellation, current_time=_NOW)


@dataclass
class Scn03Environment:
    """Named bundle of one scenario's wired components — replaces a 9-tuple
    positional return so ``setUp()`` reads by field name instead of by
    position (mis-ordering two same-typed fields, e.g. the two MagicMock
    event pipelines, would otherwise be an easy, hard-to-spot mistake)."""

    state_machine: VehicleStateMachine
    registry: ActiveActionRegistry
    gateway: VehicleToolGateway
    spy_executor: SpyExecutor
    guardrail: GroundTruthMonitorGuardrailClient
    orchestrator: AgentOrchestrator
    monitor: GuardrailMonitorAdapter
    monitor_event_pipeline: MagicMock
    controller: SimulationController


def _build_scenario() -> Scn03Environment:
    """Wire one fresh environment: driving on the highway, ACC already active
    (a precondition ``activate_hda`` requires — HDA_REQUIRES_ACTIVE_ACC),
    hands genuinely on the wheel.
    """
    mapper = load_default_mapper(load_registry(), load_manifest())
    base = get_simulation_preset(SimulationPresetId.DRIVING, state_version=1, timestamp=_NOW)
    driving_acc_active = replace(base, adas=replace(base.adas, acc_state=AccState.ACTIVE))
    state_machine = VehicleStateMachine(driving_acc_active)

    event_pipeline = MagicMock()
    registry = ActiveActionRegistry(event_pipeline=event_pipeline)
    register_hda_aac_stop_handlers(registry, state_machine)

    gateway = VehicleToolGateway()
    gateway.registry.register(
        "activate_hda",
        make_monitored_hda_aac_handler(get_behavior_config("activate_hda"), state_machine, registry),
    )
    spy_executor = SpyExecutor(gateway)

    guardrail = GroundTruthMonitorGuardrailClient(mapper)
    router = DummyModelRouter("control_driver_assistance", dict(_HDA_PROPOSAL_ARGS))
    orchestrator = AgentOrchestrator(model_router=router, mapper=mapper, guardrail=guardrail, executor=spy_executor)

    monitor_event_pipeline = MagicMock()
    monitor = GuardrailMonitorAdapter(
        guardrail_client=guardrail,
        active_action_registry=registry,
        event_pipeline=monitor_event_pipeline,
    )
    controller = SimulationController(state_machine, monitor_adapter=monitor)

    return Scn03Environment(
        state_machine=state_machine,
        registry=registry,
        gateway=gateway,
        spy_executor=spy_executor,
        guardrail=guardrail,
        orchestrator=orchestrator,
        monitor=monitor,
        monitor_event_pipeline=monitor_event_pipeline,
        controller=controller,
    )


_SESSION_ID = "sess-scn03"


class Scn03GuardrailProtectsActiveActionTests(unittest.TestCase):
    def setUp(self) -> None:
        env = _build_scenario()
        self.state_machine = env.state_machine
        self.registry = env.registry
        self.gateway = env.gateway
        self.spy_executor = env.spy_executor
        self.guardrail = env.guardrail
        self.orchestrator = env.orchestrator
        self.monitor = env.monitor
        self.monitor_event_pipeline = env.monitor_event_pipeline
        self.controller = env.controller

        # 1. The Agent genuinely starts HDA through a real orchestrator turn
        #    (ActorKind.AGENT provenance on the resulting active_actions entry).
        turn_result = self.orchestrator.handle_message(
            TurnRequest(
                session_id=_SESSION_ID,
                turn_id="turn-scn03-1",
                request_id="req-scn03-1",
                message=_HDA_UTTERANCE,
            )
        )
        self.assertIsNone(turn_result.error, f"Turn failed: {turn_result.error}")
        self.assertEqual(turn_result.status, TurnStatus.COMPLETED)

        running = self.registry.get_active_actions(session_id=_SESSION_ID)
        self.assertEqual(len(running), 1)
        self.record = running[0]

        # 2. Vehicle telemetry confirms HDA actually engaged (the catalog
        #    intentionally leaves hda_active to real vehicle/monitor feedback
        #    — see behaviors/catalog.py's ADAS section comment), a SYSTEM-actor
        #    transition distinct from both the Agent's and the operator's.
        def set_hda_engaged(s: VehicleState) -> VehicleState:
            return replace(s, adas=replace(s.adas, hda_active=True))

        self.state_machine.apply(
            set_hda_engaged, actor_kind=ActorKind.SYSTEM, actor_id="telemetry", correlation_id="hda-engaged"
        )
        self.assertTrue(self.state_machine.snapshot().adas.hda_active)
        self.monitor_event_pipeline.reset_mock()

    def test_operator_state_change_has_distinct_provenance(self) -> None:
        """Acceptance criterion: 'Operator action có provenance riêng'.

        The driver taking their hand off the wheel — via the real SIM-01
        ``SimulationController`` — is recorded with ``ActorKind.OPERATOR`` and
        its own ``actor_id``, distinct from the ``ActorKind.AGENT`` transition
        that started HDA and the ``ActorKind.SYSTEM`` telemetry transition
        from setUp.
        """
        events_before = len(self.state_machine.event_store)

        result = self.controller.set_driver_attention(
            hand_on_wheel=False, operator_id="driver-001"
        )

        self.assertTrue(result.success)
        all_events = self.state_machine.event_store.list_all()
        new_events = all_events[events_before:]
        # Two transitions land from this single operator call: the driver's
        # own hand-off-wheel change, then the monitor-triggered HDA stop it
        # cascades into (a second, SYSTEM-actor transition) — both committed
        # before set_driver_attention() returns.
        self.assertEqual(len(new_events), 2)
        operator_events = [e for e in new_events if e.actor_kind is ActorKind.OPERATOR]
        self.assertEqual(len(operator_events), 1)
        operator_event = operator_events[0]
        self.assertEqual(operator_event.actor_id, "driver-001")

        # Distinct from the earlier AGENT (HDA start) and SYSTEM (telemetry)
        # transitions already on this same event log, and from the SYSTEM
        # transition the monitor-triggered stop itself produces right after.
        earlier_actor_kinds = {e.actor_kind for e in all_events[:events_before]}
        self.assertIn(ActorKind.AGENT, earlier_actor_kinds)
        self.assertIn(ActorKind.SYSTEM, earlier_actor_kinds)
        self.assertNotIn(ActorKind.OPERATOR, earlier_actor_kinds)
        cascaded_stop_events = [e for e in new_events if e.actor_kind is not ActorKind.OPERATOR]
        self.assertEqual(len(cascaded_stop_events), 1)
        self.assertEqual(cascaded_stop_events[0].actor_kind, ActorKind.SYSTEM)

    def test_operator_state_change_triggers_guardrail_monitor_call(self) -> None:
        """Acceptance criterion: 'State change trigger Guardrail monitor call'.

        No test code calls ``GuardrailMonitorAdapter.tick()`` anywhere in this
        scenario — the operator's own ``set_driver_attention`` call is what
        triggers ``evaluate_monitor()``, via
        ``SimulationController._trigger_monitor`` → ``on_state_changed``.
        """
        calls_before = self.guardrail.evaluate_monitor_calls

        result = self.controller.set_driver_attention(hand_on_wheel=False, operator_id="driver-001")

        self.assertTrue(result.success)
        self.assertEqual(self.guardrail.evaluate_monitor_calls, calls_before + 1)
        self.assertEqual(len(result.monitor_results), 1)
        self.assertEqual(result.monitor_results[0]["outcome"], "BLOCK_UNSAFE")

    def test_agent_stops_active_action_via_registered_gateway_and_emits_stop_events(self) -> None:
        """Acceptance criterion: 'Agent dừng action qua gateway và phát stop
        response/event'.

        The monitor-triggered stop reaches the real ``VehicleState`` (not just
        the in-memory ``ActiveActionRecord``) through the registered stop
        handler — the same actuation boundary HERO-02 wires for every hda/aac
        stop — and the Agent's grounded stop message cites Guardrail's actual
        rule_id/reason_code. Decision + execution + active_action(stopped)
        events are all published for the UI.
        """
        result = self.controller.set_driver_attention(hand_on_wheel=False, operator_id="driver-001")
        monitor_result = result.monitor_results[0]

        self.assertTrue(monitor_result["stopped"])
        self.assertFalse(self.state_machine.snapshot().adas.hda_active)  # real state flipped

        record = self.registry.list_all()[0]
        self.assertEqual(record.stop_reason, "monitor_stop:HANDS_OFF_TIMEOUT")

        message = AdasMonitorHeroBehavior.build_stop_message(record, monitor_result)
        self.assertIn("HANDS_OFF_TIMEOUT", message)
        self.assertIn(_MONITOR_RULE_ID, message)

        # UI must be able to tell "policy said stop" (decision) apart from
        # "execution/lifecycle transitioned" (execution + active_action).
        self.monitor_event_pipeline.emit_decision.assert_called_once()
        self.monitor_event_pipeline.emit_execution.assert_called_once()
        self.assertEqual(
            self.monitor_event_pipeline.emit_execution.call_args.kwargs["phase"], "stopped"
        )

        # The Agent never re-derives Guardrail's monitor policy itself — it
        # only relays the outcome (HERO-02's no-local-policy guarantee).
        outcome = AdasMonitorHeroBehavior.evaluate_monitor_result(monitor_result)
        self.assertTrue(outcome.stopped)
        self.assertEqual(outcome.reason_code, "HANDS_OFF_TIMEOUT")

    def test_expected_event_sequence_matches_agent_ui_contract(self) -> None:
        """'expected events' deliverable: start (proposal/decision/execution/
        active_action) followed by the monitor-triggered stop
        (decision/execution/active_action), hand-built via AgentEventPipeline
        and format-validated against the Agent-UI v1 contract schema —
        matching SCN-01's own event-sequence test. Hand-built rather than
        captured from the fixtures' own MagicMock pipelines: neither
        ``ActiveActionRegistry`` nor the orchestrator emits a schema-validated
        stream in this test's wiring (see ``event_pipeline=MagicMock()``
        above, matching HERO-02's own integration test) — this is the formal,
        contract-checked shape those raw call args correspond to.
        """
        result = self.controller.set_driver_attention(hand_on_wheel=False, operator_id="driver-001")
        monitor_result = result.monitor_results[0]

        store = AgentEventStore()
        pipeline = AgentEventPipeline(store=store)
        session_id, turn_id, request_id = "sess-scn03-events", "turn-scn03-events", "req-scn03-events"

        proposal_event = pipeline.emit_proposal(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            intent="activate_hda",
            summary=_HDA_UTTERANCE,
        )
        start_decision = pipeline.emit_decision(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=proposal_event["proposal_id"],
            outcome="ALLOW",
            reason_code="PERMITTED",
            rule_id=_HDA_RULE_ID,
            state_version=1,
            actor="GUARDRAIL",
        )
        start_execution = pipeline.emit_execution(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=proposal_event["proposal_id"],
            execution_id="exec-scn03-hda-1",
            intent="activate_hda",
            phase="started",
        )
        pipeline.emit_active_action(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=proposal_event["proposal_id"],
            execution_id=start_execution["execution_id"],
            active_action_id=self.record.action_id,
            intent="activate_hda",
            phase="started",
        )
        # The active_action "stopped" event must be emitted while its
        # execution is still tracked as "started" — validate_event_stream
        # requires active_action events to correlate to a not-yet-terminal
        # execution (ACTIVE_ACTION_BEFORE_EXECUTION otherwise) — so the
        # execution's own terminal "stopped" transition comes last.
        stop_active_action = pipeline.emit_active_action(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=proposal_event["proposal_id"],
            execution_id=start_execution["execution_id"],
            active_action_id=self.record.action_id,
            intent="activate_hda",
            phase="stopped",
        )
        stop_execution = pipeline.emit_execution(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=proposal_event["proposal_id"],
            execution_id=start_execution["execution_id"],
            intent="activate_hda",
            phase="stopped",
            detail={"reason_code": monitor_result["reason_code"]},
        )

        events = store.get_events(session_id)
        self.assertEqual(len(events), 6)
        validate_event_stream(events)
        self.assertEqual(start_decision["outcome"], "ALLOW")
        self.assertEqual(stop_execution["phase"], "stopped")
        self.assertEqual(stop_active_action["phase"], "stopped")
        self.assertEqual(stop_active_action["active_action_id"], self.record.action_id)


if __name__ == "__main__":
    unittest.main()
