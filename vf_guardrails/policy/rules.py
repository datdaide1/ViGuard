"""Load and index the canonical 109-rule policy workbook.

Source of truth (D3): ``Driver_constraints.xlsx`` sheet ``Constraints``. The CSV
export ``vf_guardrails/Driver_constraints(Constraints).csv`` is committed and
byte-verified equal to ``golden-dataset/.../data/rules.json``.

Loads all-or-nothing and FAILS CLOSED (raises) unless the workbook has exactly
109 rules / 53 intents / 104 gate / 5 monitor and every condition parses
(PRD FR-06, AC-1, AC-12, BR-09).
"""
from __future__ import annotations

import ast
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .conditions import ConditionError, prepare_condition

_DEFAULT_CSV = Path(__file__).resolve().parents[1] / "Driver_constraints(Constraints).csv"

_EXPECTED = {"rules": 109, "intents": 53, "gate": 104, "monitor": 5}
_OUTCOMES = frozenset(
    {"ALLOW", "BLOCK_UNSAFE", "BLOCK_UNAVAILABLE", "CONFIRM", "NOT_VOICE_ACTIONABLE", "ANSWER", "UNKNOWN"}
)
_CHECK_MODES = frozenset({"gate", "monitor"})


class PolicyLoadError(RuntimeError):
    """Workbook is missing, malformed, or fails a completeness check. Fail closed."""


@dataclass(frozen=True)
class Rule:
    rule_id: str
    intent: str
    raw_condition: str
    check_mode: str
    outcome: str
    prepared: str  # Python-parseable condition (MANUAL_REWRITES or normalize_syntax)


class RuleSet:
    def __init__(self, rules: list[Rule], *, policy_checksum: str) -> None:
        self._rules = rules
        self.policy_checksum = policy_checksum
        self._by_intent_mode: dict[tuple[str, str], list[Rule]] = {}
        for r in rules:
            self._by_intent_mode.setdefault((r.intent, r.check_mode), []).append(r)
        self.intents = frozenset(r.intent for r in rules)

    def for_intent(self, intent: str, check_mode: str) -> list[Rule]:
        return self._by_intent_mode.get((intent, check_mode), [])

    def __len__(self) -> int:
        return len(self._rules)

    def all(self) -> list[Rule]:
        return list(self._rules)

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, csv_path: str | Path | None = None) -> "RuleSet":
        path = Path(csv_path) if csv_path else _DEFAULT_CSV
        if not path.exists():
            raise PolicyLoadError(f"policy workbook not found: {path}")

        rows = cls._read_rows(path)
        rules: list[Rule] = []
        seen_ids: set[str] = set()
        problems: list[str] = []

        for i, row in enumerate(rows, start=2):  # header is line 1
            rid = (row.get("rule_id") or "").strip()
            intent = (row.get("intent") or "").strip()
            cond = (row.get("condition") or "").strip()
            mode = (row.get("check_mode") or "").strip()
            outcome = (row.get("outcome") or "").strip()
            if not rid and not intent:
                continue  # trailing blank line
            if rid in seen_ids:
                problems.append(f"line {i}: duplicate rule_id {rid}")
            seen_ids.add(rid)
            if mode not in _CHECK_MODES:
                problems.append(f"{rid}: bad check_mode {mode!r}")
            if outcome not in _OUTCOMES:
                problems.append(f"{rid}: bad outcome {outcome!r}")
            prepared = prepare_condition(rid, cond)
            try:
                ast.parse(prepared, mode="eval")
            except SyntaxError as exc:
                problems.append(f"{rid}: condition does not parse: {exc}")
            rules.append(Rule(rid, intent, cond, mode, outcome, prepared))

        counts = {
            "rules": len(rules),
            "intents": len({r.intent for r in rules}),
            "gate": sum(r.check_mode == "gate" for r in rules),
            "monitor": sum(r.check_mode == "monitor" for r in rules),
        }
        for key, expected in _EXPECTED.items():
            if counts[key] != expected:
                problems.append(f"expected {expected} {key}, got {counts[key]}")

        if problems:
            raise PolicyLoadError(
                "policy workbook rejected (fail closed):\n  - " + "\n  - ".join(problems)
            )

        return cls(rules, policy_checksum=cls._checksum(rules))

    @staticmethod
    def _read_rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))

    @staticmethod
    def _checksum(rules: list[Rule]) -> str:
        canonical = json.dumps(
            [[r.rule_id, r.intent, r.raw_condition, r.check_mode, r.outcome] for r in rules],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
