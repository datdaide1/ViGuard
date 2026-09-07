"""Guardrail facade — text -> intent -> constraint outcome.

    from classifier import IntentResolver
    from gateway import Guardrail
    from policy import VehicleState

    g = Guardrail()
    g.process("mở cốp sau giùm", VehicleState(speed=0, gear="P"))

Pipeline (see docs/ARCHITECTURE.md):
  1. IntentResolver (T2 = TF-IDF, primary) -> a catalog intent, or INTENT_UNKNOWN
  2. PolicyEngine (109-rule workbook) -> exactly one of the 7 outcomes, or fail-closed

FAIL CLOSED :
  - intent unresolved      -> CLASSIFICATION_ERROR (not an outcome; never ALLOW)
  - engine fail-closed      -> outcome is None, execution not allowed

This module knows nothing about the HTTP contract / permits / the Agent —
that wrapping is the HTTP layer (see AUDIT.md §6).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from classifier import UNKNOWN, IntentResolver
from policy import Decision, PolicyEngine, RuleSet, VehicleState


@dataclass(frozen=True)
class GuardrailResult:
    intent: str
    tier: str                       # "T2" | "T2_ABSTAIN" | "explicit"
    outcome: str | None             # one of the 7 workbook outcomes, or None when fail-closed
    rule_id: str | None
    reason_code: str
    relevant_state: dict[str, Any] = field(default_factory=dict)
    error: str | None = None        # set iff fail-closed / classification error; NOT an outcome
    latency_ms: float = 0.0

    @property
    def execution_allowed(self) -> bool:
        return self.outcome == "ALLOW"

    @property
    def is_fail_closed(self) -> bool:
        return self.error is not None


class Guardrail:
    def __init__(
        self,
        resolver: IntentResolver | None = None,
        engine: PolicyEngine | None = None,
    ) -> None:
        self.resolver = resolver or IntentResolver()
        self.engine = engine or PolicyEngine(RuleSet.load())

    @property
    def policy_checksum(self) -> str:
        return self.engine.policy_checksum

    def process(
        self,
        user_query: str,
        state: VehicleState,
        *,
        check_mode: str = "gate",
        request_params: dict[str, Any] | None = None,
        intent: str | None = None,
    ) -> GuardrailResult:
        start = time.perf_counter()

        if intent is None:
            res = self.resolver.resolve(user_query)
            intent, tier = res.intent, res.tier
        else:
            tier = "explicit"

        if intent == UNKNOWN:
            return self._done(
                intent=UNKNOWN, tier=tier, outcome=None, rule_id=None,
                reason_code="INTENT_UNRESOLVED",
                error="classifier could not resolve an in-catalogue intent",
                relevant_state={}, start=start,
            )

        decision: Decision = self.engine.evaluate(
            intent, state, check_mode=check_mode, request_params=request_params
        )
        return self._done(
            intent=decision.intent, tier=tier, outcome=decision.outcome,
            rule_id=decision.rule_id, reason_code=decision.reason_code,
            relevant_state=decision.relevant_state, error=decision.error, start=start,
        )

    @staticmethod
    def _done(*, start: float, **kw: Any) -> GuardrailResult:
        return GuardrailResult(latency_ms=round((time.perf_counter() - start) * 1000.0, 3), **kw)
