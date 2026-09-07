"""HERO-04 — Confirmation hero behavior (``open_window``).

CNF-01 (:class:`~vehicle_agent.confirmation.manager.ConfirmationManager`) already
implements the full pending-confirmation lifecycle correctly at the unit
level — register/confirm/cancel/expiry/replay-rejection all had passing
tests. What was missing was the same category of gap HERO-02/HERO-03 closed
for their own modules: the already-built lifecycle logic was never actually
reachable end-to-end. Two real bugs/gaps, both fixed alongside this module:

1. **Never registered.** ``AgentOrchestrator.handle_message()`` validated a
   Guardrail ``CONFIRM`` decision (:meth:`_validate_confirmation`) and
   returned a ``NEEDS_CONFIRMATION`` :class:`TurnResult`, but never called
   ``ConfirmationManager.register_pending(...)``. A later
   ``ConfirmationManager.confirm(confirmation_id, ...)`` call for that exact
   ``confirmation_id`` would always fail with ``CONFIRMATION_NOT_FOUND`` —
   the confirm/cancel lifecycle was completely disconnected from the turn
   that created it. Fixed by adding an optional ``confirmation_manager`` DI
   port to ``AgentOrchestrator`` (mirrors the existing ``guardrail``/
   ``executor`` ports), registered right where the ``CONFIRM`` result is
   built.
2. **Wrong executor call.** ``ConfirmationManager.confirm()`` called
   ``executor.execute(proposal, decision, fresh_permit)`` — passing the raw
   permit dict as the third positional argument. Every real executor
   (``orchestrator.ActionExecutor`` Protocol, ``VehicleToolGateway.execute``)
   expects ``execute(proposal, decision, cancellation)`` — a cancellation
   token (or ``None``), not a permit; the permit already lives inside
   ``decision["permit"]``. Against CNF-01's own ``unittest.mock.MagicMock()``
   executor this never surfaced (a `MagicMock` accepts anything); against a
   real gateway it would have failed on the very first confirmed execution.
   Fixed by threading an actual (optional) cancellation token through.
3. **Non-dict execution result.** ``ConfirmationManager.confirm()`` did
   ``exec_result.to_dict() if hasattr(exec_result, "to_dict") else
   dict(exec_result)`` — but the real ``ExecutionResult``
   (``orchestrator.orchestrator.ExecutionResult``) is a plain frozen
   dataclass with **no** ``to_dict()`` and is not iterable, so
   ``dict(exec_result)`` raised ``TypeError: 'ExecutionResult' object is not
   iterable``. Every existing CNF-01 test masked this by having its executor
   mock return a plain dict directly (already trivially dict-convertible).
   Fixed with a normalizing helper that shallow-extracts dataclass fields
   instead of ``dataclasses.asdict()`` — ``asdict()`` recursively deep-copies
   every field and crashes on ``ExecutionResult.facts``
   (a ``MappingProxyType``) with ``TypeError: cannot pickle 'mappingproxy'
   object``.

Not in this ticket's scope: the public Agent-UI v1 contract already defines
``confirmRequest``/``cancelRequest`` wire shapes
(``contracts/agent_ui/v1/agent-ui.schema.json``), but
``orchestrator.endpoint.MessageEndpoint.post_message`` only ever handles
``request_type == "message"`` — there is still no code path that receives a
public confirm/cancel HTTP request and calls
``ConfirmationManager.confirm()``/``.cancel()``. This module's tests call the
manager directly (the actual business-logic layer), matching how HERO-02's
``GuardrailMonitorAdapter`` is also not wired into any endpoint/bootstrap.
Wiring the public endpoint is future INT-0x/ORC-0x scope.

``open_window`` is the demonstration intent (a simple ``TOGGLE`` behavior —
see ``behaviors/catalog.py`` — with no compound/enum state, unlike HERO-02/03's
active actions), chosen over ``open_sunroof`` only because window control has
the same aggregate-bool shape and either would demonstrate the flow equally;
picking one avoids doubling the test fixtures for no additional coverage.
"""

from __future__ import annotations

from typing import Any

from vehicle_agent.confirmation.models import PendingConfirmation

CONFIRMATION_HERO_INTENT = "open_window"


class ConfirmationHeroBehavior:
    """Reference confirmation-lifecycle behavior for ``open_window``.

    Deliberately thin: the actual lifecycle policy (single-use enforcement,
    expiry, session-scoping, fresh re-evaluation) lives entirely in
    :class:`~vehicle_agent.confirmation.manager.ConfirmationManager` — this
    class only builds telemetry-facing facts, matching the pattern
    :class:`~vehicle_agent.behaviors.hero.open_door.OpenDoorHeroBehavior` uses
    for HERO-01.
    """

    INTENT_ID = CONFIRMATION_HERO_INTENT

    @classmethod
    def build_pending_facts(
        cls, pending: PendingConfirmation, *, intent: str = INTENT_ID
    ) -> dict[str, Any]:
        """Canonical facts dict for a NEEDS_CONFIRMATION turn (UI/audit).

        ``PendingConfirmation.to_dict()`` already carries every stored field;
        this adds ``intent`` — the canonical mapped intent isn't stored on
        the record itself (only the raw ``action_proposal["tool"]`` name is),
        so a caller that already knows it (e.g. from the same
        ``ToolMapper.map_proposal(...)`` call that produced the original
        proposal) supplies it explicitly rather than this method
        re-deriving it via a second mapper call.
        """
        facts = pending.to_dict()
        facts["intent"] = intent
        return facts
