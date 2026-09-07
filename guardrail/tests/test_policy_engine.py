"""Phase 1' — constraint engine + condition evaluator + workbook loader."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from policy import PolicyEngine, RuleSet, VehicleState  # noqa: E402
from policy.conditions import ConditionError, evaluate_condition, normalize, prepare_condition  # noqa: E402
from policy.rules import PolicyLoadError  # noqa: E402
from policy.state import REQUEST_PARAMS  # noqa: E402

_DATASET = _ROOT.parent / "golden-dataset/driver-constraints/output/pipeline/dataset.jsonl"


# --------------------------------------------------------------------- conditions
def test_evaluate_basic_and_chained():
    assert evaluate_condition("gear == 'P' and speed == 0", {"gear": "P", "speed": 0})
    assert not evaluate_condition("gear == 'P' and speed == 0", {"gear": "D", "speed": 0})
    assert evaluate_condition("20 < speed < 150", {"speed": 80})
    assert not evaluate_condition("20 < speed < 150", {"speed": 10})
    assert evaluate_condition("not ( speed == 0 )", {"speed": 5})


def test_evaluate_unknown_variable_raises():
    with pytest.raises(ConditionError):
        evaluate_condition("mystery == 1", {"speed": 0})


def test_normalize_speed_collapse_and_keywords():
    assert normalize("( speed < 3 ) AND gear == 'P'") == "( speed == 0 ) and gear == 'P'"
    assert normalize("speed < 10") == "speed < 10"          # other thresholds untouched
    assert normalize("NOT ( rain_sensor == TRUE )") == "not ( rain_sensor == True )"


def test_prepare_condition_uses_manual_rewrites():
    assert prepare_condition("R042", "( speed = 0 ) AND gear != 'D'") == "speed == 0 and gear != 'D'"
    assert prepare_condition("R108", "kb_has_feature(feature_id) == True") == "kb_has_feature == True"


# --------------------------------------------------------------------- loader
def test_ruleset_load_shape_and_checksum():
    rs = RuleSet.load()
    assert len(rs) == 109
    assert sum(r.check_mode == "gate" for r in rs.all()) == 104
    assert sum(r.check_mode == "monitor" for r in rs.all()) == 5
    assert len(rs.intents) == 53
    assert rs.policy_checksum.startswith("sha256:")
    assert RuleSet.load().policy_checksum == rs.policy_checksum  # deterministic


def test_ruleset_load_fails_closed_on_short_workbook(tmp_path: Path):
    bad = tmp_path / "rules.csv"
    bad.write_text("rule_id,intent,condition,check_mode,outcome\nR001,open_door,TRUE,gate,ALLOW\n", encoding="utf-8")
    with pytest.raises(PolicyLoadError):
        RuleSet.load(bad)


# --------------------------------------------------------------------- engine
@pytest.fixture(scope="module")
def engine() -> PolicyEngine:
    return PolicyEngine(RuleSet.load())


def test_open_door_parked_allows(engine: PolicyEngine):
    d = engine.evaluate("open_door", VehicleState(gear="P", speed=0))
    assert d.outcome == "ALLOW" and d.rule_id == "R001" and d.execution_allowed


def test_open_door_moving_blocks(engine: PolicyEngine):
    d = engine.evaluate("open_door", VehicleState(gear="D", speed=50))
    assert d.outcome == "BLOCK_UNSAFE" and d.rule_id == "R002" and not d.execution_allowed


def test_unknown_intent_fails_closed(engine: PolicyEngine):
    d = engine.evaluate("teleport_vehicle", VehicleState())
    assert d.is_fail_closed and d.outcome is None and d.reason_code == "INTENT_NOT_IN_CATALOG"


def test_mode_exclusion_precedence(engine: PolicyEngine):
    # Valet eligible by profile (R039=ALLOW) but camp mode already active (R041=BLOCK_UNAVAILABLE).
    d = engine.evaluate("activate_valetmode", VehicleState(profile="OWNER", camp_mode_active=True))
    assert d.outcome == "BLOCK_UNAVAILABLE" and d.rule_id == "R041"
    assert "precedence" in d.reason_code


def test_monitor_no_trigger_is_not_fail_closed(engine: PolicyEngine):
    # autopark monitor R048 only fires when speed leaves the safe band.
    d = engine.evaluate("activate_autopark", VehicleState(autopark_state="ACTIVE", speed=5), check_mode="monitor")
    assert d.outcome is None and not d.is_fail_closed and d.reason_code == "NO_MONITOR_TRIGGER"


# --------------------------------------------------------------------- oracle
@pytest.mark.skipif(not _DATASET.exists(), reason="golden dataset not present")
def test_engine_matches_golden_dataset_exactly(engine: PolicyEngine):
    mode = {r.rule_id: r.check_mode for r in engine.ruleset.all()}
    rows = [json.loads(l) for l in _DATASET.read_text(encoding="utf-8").splitlines() if l.strip()]
    wrong = []
    for row in rows:
        vs = row.get("vehicle_state") or {}
        params = {k: v for k, v in vs.items() if k in REQUEST_PARAMS}
        state = VehicleState.from_partial({k: v for k, v in vs.items() if k not in REQUEST_PARAMS})
        d = engine.evaluate(
            row["intent"], state,
            check_mode=mode.get(row["rule_id"], "gate"),
            request_params=params,
        )
        if d.outcome != row["expected_outcome"]:
            wrong.append((row["sample_id"], row["expected_outcome"], d.outcome or d.reason_code))
    assert not wrong, f"{len(wrong)}/{len(rows)} mismatched, e.g. {wrong[:5]}"
