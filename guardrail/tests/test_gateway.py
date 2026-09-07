"""End-to-end Guardrail facade: text -> IntentResolver (TF-IDF) -> PolicyEngine."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from classifier import UNKNOWN  # noqa: E402
from gateway import Guardrail, GuardrailResult  # noqa: E402
from policy import VehicleState  # noqa: E402

_MODEL = _ROOT / "classifier/model_tfidf.pkl"
pytestmark = pytest.mark.skipif(not _MODEL.exists(), reason="run classifier/train.py first")


@pytest.fixture(scope="module")
def g() -> Guardrail:
    return Guardrail()


def test_checksum_is_stable(g: Guardrail):
    assert g.policy_checksum.startswith("sha256:")
    assert Guardrail().policy_checksum == g.policy_checksum


def test_open_trunk_parked_allows(g: Guardrail):
    r = g.process("mở cốp sau giùm cái", VehicleState(speed=0, gear="P"))
    assert isinstance(r, GuardrailResult)
    assert r.intent == "open_trunk"
    assert r.outcome == "ALLOW" and r.execution_allowed
    assert r.tier == "T2"


def test_open_trunk_moving_blocks(g: Guardrail):
    r = g.process("mở cốp sau giùm cái", VehicleState(speed=45, gear="D"))
    assert r.intent == "open_trunk"
    assert r.outcome == "BLOCK_UNSAFE" and not r.execution_allowed


def test_state_query_answers(g: Guardrail):
    r = g.process("xe đang chạy tốc độ bao nhiêu", VehicleState(speed=60), intent="get_current_speed")
    assert r.outcome == "ANSWER" and r.tier == "explicit"


def test_not_voice_actionable(g: Guardrail):
    r = g.process("tắt cân bằng điện tử ESC đi", VehicleState())
    assert r.intent == "deactivate_esc"
    assert r.outcome == "NOT_VOICE_ACTIONABLE" and not r.execution_allowed


def test_mode_exclusion_precedence(g: Guardrail):
    r = g.process("bật chế độ giao xe valet", VehicleState(profile="OWNER", camp_mode_active=True),
                  intent="activate_valetmode")
    assert r.outcome == "BLOCK_UNAVAILABLE" and r.rule_id == "R041"


def test_unresolved_intent_fails_closed(g: Guardrail):
    r = g.process("asdfghjkl qwerty zxcvbnm", VehicleState())
    assert r.intent == UNKNOWN
    assert r.outcome is None and r.is_fail_closed
    assert r.reason_code == "INTENT_UNRESOLVED"
    assert not r.execution_allowed
