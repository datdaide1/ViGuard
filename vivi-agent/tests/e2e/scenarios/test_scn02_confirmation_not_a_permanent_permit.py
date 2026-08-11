"""SCN-02 — Scenario "Confirmation không phải giấy phép vĩnh viễn" (a
confirmation is not a permanent permit).

Packages the canonical "state moved between propose and confirm" scenario
end-to-end: the vehicle is genuinely parked when Guardrail issues a
``CONFIRM`` decision for ``open_window`` (HERO-04's reference confirmation
intent), the driver then actually drives off *before* tapping confirm, and
the Agent must re-authorize against the vehicle's real state at confirm time
— never against the original (now-stale) ``CONFIRM`` decision.

Scope note, matching SCN-01's own scope note: ``GroundTruthConfirmationGuardrailClient``
below does not parse conversation text at all — it derives ``evaluate()``'s
``CONFIRM`` outcome unconditionally (opening a window always requires driver
confirmation, by policy) and derives ``confirm()``'s fresh outcome
*genuinely* from ``state_machine.snapshot().motion.speed_kph`` at the moment
confirm() is called — not from the original proposal, not from a hardcoded
outcome. This is what makes ``test_state_change_before_confirm_blocks_via_fresh_reevaluation``
a real test of "the Agent re-evaluates," not a tautology: the exact same
``confirmation_id`` is confirmed twice across this module's tests (once in a
still-parked world, once in a since-driving-off world) and gets two
different outcomes.

Architectural note this scenario surfaces (see ``ConfirmationManager.confirm()``
in ``src/vivi_agent/confirmation/manager.py``, already covered at the
integration level by
``tests/integration/hero/test_hero04_confirmation.py::test_e2e_state_change_before_confirm_uses_fresh_decision_not_stale``):
a Guardrail ``CONFIRM`` decision deliberately never carries a permit (only a
later ``ALLOW`` does) — so there is no "old permit" a confirm-time replay
could smuggle back in. The "not a permanent permit" guarantee instead rests
on two things this module proves directly:

1. ``ConfirmationManager.confirm()`` always calls ``guardrail_client.confirm()``
   for a fresh decision — the original ``CONFIRM`` decision is never reused
   as if it were an authorization (``test_state_change_before_confirm_blocks_via_fresh_reevaluation``).
2. Once a confirmation is ``CONSUMED`` (successfully resolved, in either
   direction), a replay of the exact same ``confirmation_id`` is rejected
   before ever touching Guardrail or the executor again — even after the
   vehicle becomes safe again (``test_replay_after_consumption_is_rejected_even_when_state_is_safe_again``).

This is not a new safety mechanism: it is the same lifecycle CNF-01's
``ConfirmationManager`` and HERO-04's wiring already implement at the unit/
integration level — this module packages it as the formal SCN-02 preset
sequence + expected event deliverable (see
using a real ``SimulationController``
(SIM-01) for the driver's own "state changed before I could confirm" state
transition (``ActorKind.OPERATOR`` — never ``ActorKind.AGENT``) rather than
mutating the state machine directly.

Acceptance criteria:
- Agent gọi Guardrail re-evaluation.
- Permit/decision cũ không được tái sử dụng.
- Action bị block khi state mới không phù hợp.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from vivi_agent.behaviors.catalog import get_behavior_config
from vivi_agent.behaviors.hero import CONFIRMATION_HERO_INTENT, ConfirmationHeroBehavior
from vivi_agent.catalog import load_manifest
from vivi_agent.confirmation import ConfirmationManager, ConfirmationState
from vivi_agent.contracts.agent_ui.v1.contract import validate_event_stream
from vivi_agent.contracts.guardrail.v1.contract import CONTRACT_VERSION, proposal_digest
from vivi_agent.contracts.agent_ui.v1.contract import CONTRACT_VERSION as AGENT_UI_CONTRACT_VERSION
from vivi_agent.events import AgentEventPipeline, AgentEventStore
from vivi_agent.model_providers import ModelActionProposal, ProviderMetadata, TurnBinding
from vivi_agent.orchestrator import (
    AgentOrchestrator,
    CancellationToken,
    ExecutionResult,
    MessageEndpoint,
)
from vivi_agent.simulation import SimulationController, SimulationPresetId, get_simulation_preset
from vivi_agent.tools.mapping import load_default_mapper
from vivi_agent.tools.registry import load_registry
from vivi_agent.vehicle.execution import VehicleToolGateway
from vivi_agent.vehicle.execution.generic import ToggleHandler
from vivi_agent.vehicle.state.machine import VehicleStateMachine

_NOW = datetime(2026, 8, 7, 13, 0, 0, tzinfo=timezone.utc)
META = ProviderMetadata("openai", "gpt-4o", "sha256:scn-02-test", 10)
_ZERO_CHECKSUM = "sha256:" + "0" * 64
_RULE_ID = "R_WINDOW_CONFIRM"

_WINDOW_UTTERANCE = "Mở cửa sổ giúp tôi"
_WINDOW_PROPOSAL_ARGS = {"action": "open", "target": "driver_window"}
_CONFIRMATION_ID = "confirm-scn02-01"
_EXPIRES_AT = "2099-01-01T00:00:00Z"
_PROMPT = "Xe cần dừng hẳn trước khi mở cửa sổ khi đang chạy. Bạn có chắc chắn muốn mở cửa sổ không?"


class DeterministicModelRouter:
    """Always proposes ``open_window`` — mirrors SCN-01's ``DeceptiveModelRouter``
    shape (module docstring's scope note): this scenario is not about what the
    model proposes, only about what happens to a proposal once Guardrail has
    already asked for confirmation.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.proposal = ModelActionProposal.action("control_cabin", dict(_WINDOW_PROPOSAL_ARGS), META)

    def propose_tool(self, messages: list[dict[str, str]], binding: TurnBinding) -> ModelActionProposal:
        self.calls += 1
        binding.record_proposal(self.proposal)
        return self.proposal

    def compose_response(self, facts: Mapping[str, Any], turn: TurnBinding) -> ModelActionProposal:
        return ModelActionProposal.response("Phản hồi.", META)


class GroundTruthConfirmationGuardrailClient:
    """Guardrail mock whose ``confirm()`` genuinely re-derives its outcome from
    ``state_machine.snapshot().motion.speed_kph`` at call time — ALLOW (with a
    fresh, single-use permit tied to the *current* ``state_version``) while
    parked, BLOCK_UNSAFE while moving. ``evaluate()`` always returns CONFIRM
    for ``open_window`` (a window-while-driving policy always requires driver
    confirmation, regardless of the state at propose time) — the state
    dependency this scenario tests lives entirely in ``confirm()``, matching
    the acceptance criteria's focus on re-evaluation, not on the initial
    proposal.
    """

    def __init__(self, state_machine: VehicleStateMachine) -> None:
        self.state_machine = state_machine
        self.evaluate_calls = 0
        self.confirm_calls = 0
        self._last_proposal: Mapping[str, Any] | None = None
        # The CONFIRM decision handed back by the most recent evaluate() call
        # — kept so tests can assert directly on it (e.g. "did the original
        # decision itself carry a permit"), since PendingConfirmation only
        # stores the proposal, never the decision that created it.
        self.last_confirm_decision: dict[str, Any] | None = None

    def _base_decision(self, *, request_id: str, state_version: int) -> dict[str, Any]:
        """Fields shared by every decision this mock returns (both
        ``evaluate()`` and ``confirm()``) — factored out so a future field
        added to one can't silently drift from the other."""
        return {
            "contract_version": CONTRACT_VERSION,
            "kind": "decision",
            "request_id": request_id,
            "intent": "open_window",
            "rule_id": _RULE_ID,
            "state_version": state_version,
            "policy_checksum": _ZERO_CHECKSUM,
        }

    def evaluate(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        self.evaluate_calls += 1
        self._last_proposal = proposal
        decision = self._base_decision(
            request_id=f"req-scn02-eval-{self.evaluate_calls}",
            state_version=self.state_machine.snapshot().state_version,
        )
        decision.update(
            proposal_id=proposal["proposal_id"],
            outcome="CONFIRM",
            reason_code="DRIVER_CONFIRMATION_REQUIRED",
            relevant_state={},
            confirmation={
                "confirmation_id": _CONFIRMATION_ID,
                "proposal_id": proposal["proposal_id"],
                "prompt": _PROMPT,
                "expires_at": _EXPIRES_AT,
                "single_use": True,
            },
        )
        self.last_confirm_decision = decision
        return decision

    def confirm(
        self, confirmation_id: str, session_id: str, request_id: str | None = None
    ) -> dict[str, Any]:
        self.confirm_calls += 1
        snapshot = self.state_machine.snapshot()
        moving = snapshot.motion.speed_kph > 0.0
        base = self._base_decision(
            request_id=f"req-scn02-confirm-{self.confirm_calls}", state_version=snapshot.state_version
        )
        base["relevant_state"] = {"speed": snapshot.motion.speed_kph}
        if moving:
            base.update(outcome="BLOCK_UNSAFE", reason_code="VEHICLE_MOVING")
            return base

        assert self._last_proposal is not None, "confirm() called before evaluate()"
        permit = {
            "permit_id": f"permit-scn02-{self.confirm_calls}",
            "proposal_digest": proposal_digest(self._last_proposal),
            "intent": "open_window",
            "rule_id": _RULE_ID,
            "state_version": snapshot.state_version,
            "policy_checksum": _ZERO_CHECKSUM,
            "issued_at": _NOW.isoformat().replace("+00:00", "Z"),
            "expires_at": _EXPIRES_AT,
            "single_use": True,
        }
        base.update(outcome="ALLOW", reason_code="CONFIRMATION_REEVALUATED_ALLOW", permit=permit)
        return base


class SpyExecutor:
    """ActionExecutor wrapper proxying to the real VehicleToolGateway."""

    def __init__(self, gateway: VehicleToolGateway) -> None:
        self.gateway = gateway
        self.call_count = 0

    def execute(
        self,
        proposal: Mapping[str, Any],
        decision: Mapping[str, Any],
        cancellation: CancellationToken | None,
    ) -> ExecutionResult:
        self.call_count += 1
        return self.gateway.execute(proposal, decision, cancellation, current_time=_NOW)


@dataclass
class Scn02Environment:
    """Named bundle of one scenario's wired components — replaces an 8-tuple
    positional return so ``setUp()`` reads by field name instead of by
    position (mis-ordering two same-typed fields silently would otherwise be
    an easy, hard-to-spot mistake as this wiring grows)."""

    state_machine: VehicleStateMachine
    gateway: VehicleToolGateway
    spy_executor: SpyExecutor
    guardrail: GroundTruthConfirmationGuardrailClient
    router: DeterministicModelRouter
    confirmation_manager: ConfirmationManager
    controller: SimulationController
    endpoint: MessageEndpoint


def _build_scenario() -> Scn02Environment:
    """Wire one fresh environment — vehicle starts genuinely PARKED (safe)."""
    mapper = load_default_mapper(load_registry(), load_manifest())
    preset_state = get_simulation_preset(SimulationPresetId.PARKED, state_version=1, timestamp=_NOW)
    state_machine = VehicleStateMachine(preset_state)

    gateway = VehicleToolGateway()
    gateway.registry.register(
        CONFIRMATION_HERO_INTENT,
        ToggleHandler(get_behavior_config(CONFIRMATION_HERO_INTENT), state_machine),
    )
    spy_executor = SpyExecutor(gateway)

    guardrail = GroundTruthConfirmationGuardrailClient(state_machine)
    router = DeterministicModelRouter()
    confirmation_manager = ConfirmationManager()
    controller = SimulationController(state_machine)
    orchestrator = AgentOrchestrator(
        model_router=router,
        mapper=mapper,
        guardrail=guardrail,
        executor=spy_executor,
        confirmation_manager=confirmation_manager,
    )
    endpoint = MessageEndpoint(orchestrator)

    return Scn02Environment(
        state_machine=state_machine,
        gateway=gateway,
        spy_executor=spy_executor,
        guardrail=guardrail,
        router=router,
        confirmation_manager=confirmation_manager,
        controller=controller,
        endpoint=endpoint,
    )


def _request_payload(session_id: str, turn_id: str, request_id: str) -> dict[str, Any]:
    return {
        "contract_version": AGENT_UI_CONTRACT_VERSION,
        "kind": "request",
        "request_type": "message",
        "session_id": session_id,
        "turn_id": turn_id,
        "request_id": request_id,
        "occurred_at": "2026-08-07T13:00:00Z",
        "message": _WINDOW_UTTERANCE,
    }


class Scn02ConfirmationNotAPermanentPermitTests(unittest.TestCase):
    def setUp(self) -> None:
        env = _build_scenario()
        self.state_machine = env.state_machine
        self.gateway = env.gateway
        self.spy_executor = env.spy_executor
        self.guardrail = env.guardrail
        self.router = env.router
        self.confirmation_manager = env.confirmation_manager
        self.controller = env.controller
        self.endpoint = env.endpoint

        response = self.endpoint.post_message(
            _request_payload("sess-scn02", "turn-scn02-1", "req-scn02-1")
        )
        self.assertEqual(response["status"], "needs_confirmation")
        self.assertEqual(response["confirmation_id"], _CONFIRMATION_ID)
        self.assertEqual(self.guardrail.evaluate_calls, 1)

    def test_confirmation_registered_while_state_still_safe(self) -> None:
        """Sanity check on the preset sequence: the CONFIRM decision was
        registered while the vehicle genuinely was parked, and — critically —
        carries no permit at all (only a fresh ALLOW ever would), so there is
        nothing "old" a later replay could smuggle back in."""
        pending = self.confirmation_manager.get_pending(_CONFIRMATION_ID)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.state, ConfirmationState.PENDING)
        self.assertEqual(self.state_machine.snapshot().motion.speed_kph, 0.0)
        # Checked against the actual CONFIRM decision Guardrail returned
        # (not pending.action_proposal — the proposal envelope structurally
        # never carries a "permit" key regardless of guardrail behavior, so
        # asserting against it wouldn't catch a decision that wrongly
        # embedded one).
        self.assertIsNotNone(self.guardrail.last_confirm_decision)
        self.assertNotIn("permit", self.guardrail.last_confirm_decision)

        facts = ConfirmationHeroBehavior.build_pending_facts(pending, intent=CONFIRMATION_HERO_INTENT)
        self.assertEqual(facts["confirmation_id"], _CONFIRMATION_ID)
        self.assertEqual(self.spy_executor.call_count, 0)

    def test_state_change_before_confirm_blocks_via_fresh_reevaluation(self) -> None:
        """Acceptance criteria: 'Agent gọi Guardrail re-evaluation' + 'Action
        bị block khi state mới không phù hợp'.

        Between the CONFIRM decision and the driver actually tapping confirm,
        the driver pulls away (an OPERATOR-provenance state change via the
        real SimulationController — SIM-01 — not a bare state-machine patch).
        The fresh confirm-time re-evaluation must reflect that, not the
        parked-world CONFIRM decision from setUp.
        """
        original_state_version = self.state_machine.snapshot().state_version
        sim_result = self.controller.set_speed(30.0, operator_id="driver-001")
        self.assertTrue(sim_result.success)
        self.assertGreater(self.state_machine.snapshot().state_version, original_state_version)
        self.assertGreater(self.state_machine.snapshot().motion.speed_kph, 0.0)

        result = self.confirmation_manager.confirm(
            confirmation_id=_CONFIRMATION_ID,
            session_id="sess-scn02",
            guardrail_client=self.guardrail,
        )

        self.assertEqual(self.guardrail.confirm_calls, 1)  # fresh re-evaluation actually happened
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.decision["outcome"], "BLOCK_UNSAFE")
        self.assertEqual(result.decision["reason_code"], "VEHICLE_MOVING")
        # The fresh BLOCK decision cites the real, current state_version —
        # never the stale one the original CONFIRM decision was issued
        # against — proof this is a live re-evaluation, not a replay.
        self.assertEqual(result.decision["state_version"], self.state_machine.snapshot().state_version)
        self.assertGreater(result.decision["state_version"], original_state_version)
        self.assertNotIn("permit", result.decision)

        # Handler call count is zero: no window ever opened while blocked.
        self.assertFalse(self.state_machine.snapshot().cabin.windows_open)

    def test_confirm_succeeds_with_fresh_permit_when_state_still_safe(self) -> None:
        """Contrast case: with no intervening state change, the fresh
        re-evaluation still happens (Guardrail is asked again, not skipped)
        and this time genuinely allows — proving ALLOW isn't hardcoded either."""
        pre_confirm_version = self.state_machine.snapshot().state_version
        result = self.confirmation_manager.confirm(
            confirmation_id=_CONFIRMATION_ID,
            session_id="sess-scn02",
            guardrail_client=self.guardrail,
            executor=self.spy_executor,
        )

        self.assertEqual(self.guardrail.confirm_calls, 1)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.decision["outcome"], "ALLOW")
        # The fresh permit is tied to the state_version at the moment of
        # re-evaluation (before execution bumps it again) — not a stale
        # value carried over from the original CONFIRM decision.
        self.assertEqual(result.decision["permit"]["state_version"], pre_confirm_version)
        self.assertTrue(self.state_machine.snapshot().cabin.windows_open)
        self.assertEqual(self.spy_executor.call_count, 1)

    def test_replay_after_consumption_is_rejected_even_when_state_is_safe_again(self) -> None:
        """Once CONSUMED, this exact confirmation_id must never be resolved a
        second time — even if a later attacker/replay finds the vehicle
        parked again. Single-use is about the confirmation record, not the
        vehicle's instantaneous state."""
        self.controller.set_speed(30.0, operator_id="driver-001")
        first = self.confirmation_manager.confirm(
            confirmation_id=_CONFIRMATION_ID, session_id="sess-scn02", guardrail_client=self.guardrail
        )
        self.assertEqual(first.status, "blocked")
        self.assertEqual(self.guardrail.confirm_calls, 1)

        # Vehicle becomes safe again — must not resurrect the old confirmation.
        self.controller.set_speed(0.0, operator_id="driver-001")
        replay = self.confirmation_manager.confirm(
            confirmation_id=_CONFIRMATION_ID,
            session_id="sess-scn02",
            guardrail_client=self.guardrail,
            executor=self.spy_executor,
        )

        self.assertEqual(replay.status, "failed")
        self.assertEqual(replay.error["code"], "CONFIRMATION_ALREADY_CONSUMED")
        self.assertEqual(self.guardrail.confirm_calls, 1)  # no additional re-evaluation
        self.assertEqual(self.spy_executor.call_count, 0)

    def test_expected_event_sequence_matches_agent_ui_contract(self) -> None:
        """'expected events' deliverable: the proposal + CONFIRM decision pair
        for this scenario, attributed to GUARDRAIL, format-validated against
        the Agent-UI v1 contract schema. Hand-built via AgentEventPipeline,
        matching SCN-01's own event-sequence test (the orchestrator does not
        emit events itself — see EVT-01).

        Only one decision event is emitted per proposal_id here — not two —
        because ``validate_event_stream`` enforces exactly one decision per
        proposal (``DUPLICATE_DECISION``), and the public Agent-UI v1 wire
        contract has no confirm/cancel request path yet (see HERO-04's own
        documented scope note in ``confirmation.py``). The confirm-time fresh
        re-evaluation this scenario is actually about is therefore a backend-
        internal Guardrail call today, asserted directly against
        ``ConfirmationResult.decision`` in the tests above — not (yet) a
        second event on this public stream.
        """
        store = AgentEventStore()
        pipeline = AgentEventPipeline(store=store)
        session_id, turn_id, request_id = "sess-scn02-events", "turn-scn02-events", "req-scn02-events"

        proposal_event = pipeline.emit_proposal(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            intent="open_window",
            summary=_WINDOW_UTTERANCE,
        )
        decision_event = pipeline.emit_decision(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=proposal_event["proposal_id"],
            outcome="CONFIRM",
            reason_code="DRIVER_CONFIRMATION_REQUIRED",
            rule_id=_RULE_ID,
            state_version=1,
            actor="GUARDRAIL",
        )

        events = store.get_events(session_id)
        self.assertEqual(len(events), 2)  # proposal + CONFIRM only, no execution
        validate_event_stream(events)
        self.assertEqual(decision_event["outcome"], "CONFIRM")
        self.assertEqual(decision_event["actor"], "GUARDRAIL")

        # The scenario's actual "not a permanent permit" proof — a second,
        # state-derived re-evaluation overriding the first — happens here,
        # off the public event stream:
        self.controller.set_speed(30.0, operator_id="driver-001")
        confirm_result = self.confirmation_manager.confirm(
            confirmation_id=_CONFIRMATION_ID, session_id="sess-scn02", guardrail_client=self.guardrail
        )
        self.assertEqual(confirm_result.status, "blocked")
        self.assertEqual(confirm_result.decision["outcome"], "BLOCK_UNSAFE")
        self.assertGreater(confirm_result.decision["state_version"], decision_event["state_version"])


if __name__ == "__main__":
    unittest.main()
