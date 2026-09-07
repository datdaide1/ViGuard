"""Guardrail policy core — condition evaluation + constraint engine.

Clean rebuild against the canonical 109-rule workbook
(``policy/constraints.csv`` == ``golden-dataset/.../data/rules.json``).
Replaces the lossy hand-authored ``config/safety_rules.yaml`` +
``src/safety_engine.py`` (see ``docs/DECISIONS.md``).

The AST evaluator and manual-rewrite table are lifted from
``golden-dataset/driver-constraints/tools/derive_witness_states.py`` — the same
closed, ``eval()``-free evaluator already proven on all 109 conditions.
"""

from .conditions import (
    MANUAL_REWRITES,
    ConditionError,
    evaluate_condition,
    normalize,
    prepare_condition,
)
from .engine import Decision, PolicyEngine, PolicyError
from .rules import Rule, RuleSet
from .state import CONDITION_VARIABLES, VehicleState

__all__ = [
    "MANUAL_REWRITES",
    "ConditionError",
    "evaluate_condition",
    "normalize",
    "prepare_condition",
    "Decision",
    "PolicyEngine",
    "PolicyError",
    "Rule",
    "RuleSet",
    "CONDITION_VARIABLES",
    "VehicleState",
]
