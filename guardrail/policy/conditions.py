"""Closed, ``eval()``-free evaluator for workbook ``condition`` expressions.

Lifted from ``golden-dataset/driver-constraints/tools/derive_witness_states.py``
(``evaluate_condition``, ``normalize``, ``MANUAL_REWRITES``) — already proven on
all 109 canonical conditions with 0 eval errors. Kept semantically identical so
the runtime and the evaluation oracle never drift.

``normalize`` applies the PM-ratified clarification ``speed < 3`` -> ``speed == 0``
(PLAN.md §6a): every rule that gates on "speed < 3" means "vehicle fully
stationary" — 1-2 km/h creep is not a safe state for door/trunk/chargeport/seat
actions, and this makes each ALLOW/CONFIRM rule partition cleanly against its
``NOT ( speed < 3 )`` complement with no 1-2 km/h gap. The golden dataset is
labelled under this same rule, so the runtime must apply it too.
"""
from __future__ import annotations

import ast
import operator
import re
from typing import Any

# Rules whose literal workbook text needs a rewrite before parsing: '=' vs '=='
# typos, and pseudo-function calls standing in for derived/KB signals. Kept
# byte-identical to the golden-dataset table so both stay in sync.
MANUAL_REWRITES: dict[str, str] = {
    "R042": "speed == 0 and gear != 'D'",
    "R044": "speed == 0",
    "R052": "rain_sensor == True and speed <= 80",
    "R061": "rain_sensor == True and speed <= 80",
    "R073": "hand_off_wheel_duration_seconds > 15",
    "R108": "kb_has_feature == True",
    "R109": "kb_has_feature == False",
}

_COMPARE_OPERATORS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}


class ConditionError(ValueError):
    """Parse/eval failure. The engine treats this as FAIL CLOSED, never a pass."""


def normalize(cond: str) -> str:
    """Workbook syntax -> Python, byte-identical to the golden-dataset copy."""
    if cond is True:
        return "True"
    cond = str(cond).strip()
    cond = re.sub(r"\bAND\b", "and", cond)
    cond = re.sub(r"\bOR\b", "or", cond)
    cond = re.sub(r"\bNOT\b", "not", cond)
    cond = re.sub(r"\bTRUE\b", "True", cond)
    cond = re.sub(r"\bFALSE\b", "False", cond)
    # PM decision (PLAN.md §6a): "speed < 3" means "fully stationary". Applied
    # to the golden-dataset labels, so applied here too. Only this exact
    # literal; other thresholds (10, 15, 16, 40, 80, 150) untouched.
    cond = re.sub(r"speed\s*<\s*3\b", "speed == 0", cond)
    return cond


def prepare_condition(rule_id: str, raw_condition: str) -> str:
    """Return the Python-parseable form of a rule's condition."""
    if rule_id in MANUAL_REWRITES:
        return MANUAL_REWRITES[rule_id]
    return normalize(raw_condition)


def evaluate_condition(condition: str, values: dict[str, Any]) -> bool:
    """Evaluate *condition* against *values* with a closed, call-free AST.

    Raises ConditionError on unsupported syntax or an unknown variable — the
    caller must fail closed, not treat the raise as a non-match.
    """

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(
            node.value, (bool, int, float, str, type(None))
        ):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise ConditionError(f"unknown condition variable: {node.id}")
            return values[node.id]
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            resolved = [bool(visit(value)) for value in node.values]
            return all(resolved) if isinstance(node.op, ast.And) else any(resolved)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not bool(visit(node.operand))
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            for operation_node, comparator_node in zip(node.ops, node.comparators):
                operation = _COMPARE_OPERATORS.get(type(operation_node))
                if operation is None:
                    raise ConditionError(
                        f"unsupported comparison: {type(operation_node).__name__}"
                    )
                right = visit(comparator_node)
                if not operation(left, right):
                    return False
                left = right
            return True
        raise ConditionError(f"unsupported condition syntax: {type(node).__name__}")

    try:
        tree = ast.parse(condition, mode="eval")
    except SyntaxError as exc:
        raise ConditionError(f"cannot parse condition {condition!r}: {exc}") from exc
    return bool(visit(tree))
