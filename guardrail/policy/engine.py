"""Constraint engine — resolve ``(intent, vehicle state)`` to exactly one outcome.

Deterministic, fail-closed :

  - intent not in the workbook            -> fail closed (INTENT_NOT_IN_CATALOG)
  - a candidate rule cannot be evaluated  -> fail closed (CONDITION_EVAL_ERROR)
  - no gate rule matches                  -> fail closed (NO_MATCHING_POLICY)
  - rules match with conflicting outcomes -> fail closed (POLICY_AMBIGUITY)
  - exactly one outcome                   -> that outcome

"Fail closed" == ``outcome`` is None and ``execution_allowed`` is False; the
HTTP layer (Phase 2) maps these to a typed GuardrailError, never to an outcome.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

from .conditions import ConditionError, evaluate_condition
from .rules import Rule, RuleSet
from .state import CONDITION_VARIABLES, VehicleState


class PolicyError(RuntimeError):
    pass


# COVERAGE_SPEC.md "Confirmed precedence": mode-exclusion gate rules outrank the
# corresponding mode-eligibility rules. If Camp/Pet/Valet mode is already active
# the effective outcome is BLOCK_UNAVAILABLE (R034 > R031/R032, R038 > R035/R036,
# R041 > R039/R040). Only these three; every other multi-outcome match is a
# genuine POLICY_AMBIGUITY (a release blocker per the same spec).
_RULE_PRIORITY: dict[str, int] = {"R034": 10, "R038": 10, "R041": 10}


@dataclass(frozen=True)
class Decision:
    intent: str
    check_mode: str
    outcome: str | None            # one of the 7 workbook outcomes, or None when fail-closed
    rule_id: str | None
    reason_code: str
    relevant_state: dict[str, Any] = field(default_factory=dict)
    error: str | None = None       # set iff fail-closed; not a policy outcome
    matched_rule_ids: tuple[str, ...] = ()

    @property
    def execution_allowed(self) -> bool:
        return self.outcome == "ALLOW"

    @property
    def is_fail_closed(self) -> bool:
        return self.error is not None


def _vars_in(rule: Rule) -> set[str]:
    tree = ast.parse(rule.prepared, mode="eval")
    return {
        n.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id not in ("True", "False", "None")
    }


class PolicyEngine:
    def __init__(self, ruleset: RuleSet) -> None:
        self.ruleset = ruleset

    @property
    def policy_checksum(self) -> str:
        return self.ruleset.policy_checksum

    def evaluate(
        self,
        intent: str,
        state: VehicleState,
        *,
        check_mode: str = "gate",
        request_params: dict[str, Any] | None = None,
    ) -> Decision:
        if intent not in self.ruleset.intents:
            return self._fail(
                intent, check_mode, "INTENT_NOT_IN_CATALOG",
                f"intent {intent!r} has no rule in the workbook",
            )

        rules = self.ruleset.for_intent(intent, check_mode)
        if not rules:
            # intent exists but not in this phase (e.g. no monitor rules) -> nothing to do
            return self._fail(
                intent, check_mode, "NO_RULE_FOR_PHASE",
                f"intent {intent!r} has no {check_mode} rule",
            )

        values = dict(state.as_condition_values())
        for k, v in (request_params or {}).items():
            if k not in CONDITION_VARIABLES:
                return self._fail(
                    intent, check_mode, "UNKNOWN_REQUEST_PARAM",
                    f"unknown request parameter {k!r}",
                )
            values[k] = v

        matches: list[Rule] = []
        for rule in rules:
            try:
                if evaluate_condition(rule.prepared, values):
                    matches.append(rule)
            except ConditionError as exc:
                return self._fail(
                    intent, check_mode, "CONDITION_EVAL_ERROR",
                    f"{rule.rule_id}: {exc}",
                )

        if not matches:
            if check_mode == "monitor":
                # No monitor condition holds -> valid NO_MONITOR_TRIGGER, not a
                # gap and not an 8th outcome (COVERAGE_SPEC.md "State coverage").
                return Decision(
                    intent=intent, check_mode=check_mode, outcome=None, rule_id=None,
                    reason_code="NO_MONITOR_TRIGGER",
                    relevant_state=self._relevant(rules, values),
                )
            return self._fail(
                intent, check_mode, "NO_MATCHING_POLICY",
                f"no {check_mode} rule matched for {intent!r}",
                relevant_state=self._relevant(rules, values),
            )

        outcomes = {r.outcome for r in matches}
        precedence_note = ""
        if len(outcomes) > 1:
            top = max(_RULE_PRIORITY.get(r.rule_id, 0) for r in matches)
            winners = [r for r in matches if _RULE_PRIORITY.get(r.rule_id, 0) == top]
            if top == 0 or len({r.outcome for r in winners}) > 1:
                return self._fail(
                    intent, check_mode, "POLICY_AMBIGUITY",
                    "conflicting outcomes: "
                    + ", ".join(f"{r.rule_id}={r.outcome}" for r in matches),
                    relevant_state=self._relevant(matches, values),
                )
            suppressed = [r.rule_id for r in matches if r not in winners]
            precedence_note = f" (precedence over {', '.join(suppressed)})"
            matches = winners

        chosen = matches[0]
        return Decision(
            intent=intent,
            check_mode=check_mode,
            outcome=chosen.outcome,
            rule_id=chosen.rule_id,
            reason_code=f"POLICY_{chosen.outcome}" + precedence_note,
            relevant_state=self._relevant(matches, values),
            matched_rule_ids=tuple(r.rule_id for r in matches),
        )

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _relevant(rules: list[Rule], values: dict[str, Any]) -> dict[str, Any]:
        keys: set[str] = set()
        for r in rules:
            keys |= _vars_in(r)
        return {k: values[k] for k in sorted(keys) if k in values}

    @staticmethod
    def _fail(
        intent: str,
        check_mode: str,
        code: str,
        message: str,
        *,
        relevant_state: dict[str, Any] | None = None,
    ) -> Decision:
        return Decision(
            intent=intent,
            check_mode=check_mode,
            outcome=None,
            rule_id=None,
            reason_code=code,
            relevant_state=relevant_state or {},
            error=message,
        )
