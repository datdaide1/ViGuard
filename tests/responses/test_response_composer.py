"""Unit tests for Grounded Response Composer (RSP-01).

Validates grounding rules, deterministic Vietnamese fallbacks, recovery suggestions,
length limits, and execution failure handling.
"""

from __future__ import annotations

import pytest

from vivi_agent.responses import (
    GroundedResponseComposer,
    PersonaProfile,
    PersonaTone,
    PersonaVerbalizer,
    ResponseOutcome,
    UserAddress,
    format_relevant_state,
)


def test_allow_successful_execution_fallback():
    composer = GroundedResponseComposer()
    decision = {
        "outcome": "ALLOW",
        "rule_id": "R001",
        "reason_code": "PERMITTED",
        "relevant_state": {"speed": 0},
    }
    execution = {"success": True, "message": "Đã mở cửa xe thành công."}

    plan = composer.compose_from_guardrail(decision, execution)

    assert plan.outcome == ResponseOutcome.ALLOW_SUCCESS
    assert plan.text == "Đã mở cửa xe thành công."
    assert plan.is_fallback is True
    assert plan.grounded_facts == {"speed": 0}


def test_allow_failed_execution_never_returns_success_message():
    """Acceptance criteria: ALLOW but execution failed does NOT create a success message."""
    composer = GroundedResponseComposer()
    decision = {"outcome": "ALLOW", "rule_id": "R001"}
    execution = {
        "success": False,
        "error": {"code": "DOOR_STUCK", "message": "Cửa bị kẹt vật cản."},
    }
    model_verbalization = "Đã mở cửa xe thành công!"  # Falsely claiming success

    plan = composer.compose_from_guardrail(decision, execution, model_verbalization=model_verbalization)

    assert plan.outcome == ResponseOutcome.ALLOW_FAILED
    assert "thao tác không thành công" in plan.text.lower() or "bị kẹt" in plan.text.lower()
    assert plan.is_fallback is True  # Falsely successful model verbalization was rejected
    assert plan.recovery_suggestions != []


def test_block_unsafe_deterministic_template_and_recovery_suggestions():
    composer = GroundedResponseComposer()
    decision = {
        "outcome": "BLOCK_UNSAFE",
        "rule_id": "RULE_SPEED",
        "reason_code": "HIGH_SPEED",
        "policy_reason": "Vehicle speed exceeds safe threshold",
        "relevant_state": {"speed_kmh": 80},
    }

    plan = composer.compose_from_guardrail(decision)

    assert plan.outcome == ResponseOutcome.BLOCK_UNSAFE
    assert "tốc độ cao" in plan.text
    assert "80 km/h" in plan.text
    assert plan.rule_id == "RULE_SPEED"
    assert len(plan.recovery_suggestions) > 0


def test_confirm_outcome():
    composer = GroundedResponseComposer()
    decision = {
        "outcome": "CONFIRM",
        "rule_id": "RULE_CONFIRM",
        "reason_code": "CRITICAL_ACTION",
    }

    plan = composer.compose_from_guardrail(decision)

    assert plan.outcome == ResponseOutcome.CONFIRM
    assert "xác nhận" in plan.text.lower()
    assert plan.recovery_suggestions != []


def test_not_voice_actionable_outcome():
    composer = GroundedResponseComposer()
    decision = {"outcome": "NOT_VOICE_ACTIONABLE"}

    plan = composer.compose_from_guardrail(decision)

    assert plan.outcome == ResponseOutcome.NOT_VOICE_ACTIONABLE
    assert "giọng nói" in plan.text.lower()


def test_answer_outcome_with_typed_facts():
    composer = GroundedResponseComposer()
    decision = {
        "outcome": "ANSWER",
        "answer": {
            "grounded": True,
            "facts": {"battery_pct": 85, "speed_kmh": 0},
        },
    }

    plan = composer.compose_from_guardrail(decision)

    assert plan.outcome == ResponseOutcome.ANSWER
    assert "85%" in plan.text
    assert plan.grounded_facts == {"battery_pct": 85, "speed_kmh": 0}


def test_unknown_outcome():
    composer = GroundedResponseComposer()
    decision = {"outcome": "UNKNOWN"}

    plan = composer.compose_from_guardrail(decision)

    assert plan.outcome == ResponseOutcome.UNKNOWN
    assert "chưa có thông tin" in plan.text.lower()


def test_valid_model_verbalization_accepted():
    composer = GroundedResponseComposer()
    decision = {"outcome": "ALLOW"}
    execution = {"success": True, "message": "Success"}
    model_verbalization = "Em đã mở cửa xe giúp anh rồi ạ."

    plan = composer.compose_from_guardrail(decision, execution, model_verbalization=model_verbalization)

    assert plan.outcome == ResponseOutcome.ALLOW_SUCCESS
    assert plan.text == "Em đã mở cửa xe giúp anh rồi ạ."
    assert plan.is_fallback is False


def test_length_limit_truncation():
    composer = GroundedResponseComposer(max_length=30)
    decision = {"outcome": "ALLOW"}
    execution = {"success": True, "message": "Success"}
    model_verbalization = "Đây là một câu trả lời rất dài vượt quá giới hạn 30 ký tự để kiểm tra tính năng cắt ngắn."

    plan = composer.compose_from_guardrail(decision, execution, model_verbalization=model_verbalization)

    assert len(plan.text) <= 30
    assert plan.truncated is True
    assert plan.text.endswith("...")


def test_compose_from_query_success():
    composer = GroundedResponseComposer()
    query_result = {
        "status": "ANSWER",
        "facts": {"battery_pct": 42},
        "response_text": "Dung lượng pin còn 42%.",
    }

    plan = composer.compose_from_query(query_result)

    assert plan.outcome == ResponseOutcome.ANSWER
    assert plan.text == "Dung lượng pin còn 42%."
    assert plan.grounded_facts == {"battery_pct": 42}


def test_format_relevant_state():
    state = {
        "battery_pct": 90,
        "speed_kmh": 45,
        "trunk_open": False,
        "climate_temp": 22,
    }
    formatted = format_relevant_state(state)

    assert "Dung lượng pin: 90%" in formatted
    assert "Tốc độ: 45 km/h" in formatted
    assert "Cốp xe: đã đóng" in formatted
    assert "Nhiệt độ điều hòa: 22°C" in formatted


def test_warm_persona_wraps_only_deterministic_fallback_without_rewriting_facts():
    composer = GroundedResponseComposer(persona=PersonaProfile(tone=PersonaTone.WARM))
    decision = {
        "outcome": "BLOCK_UNSAFE",
        "reason_code": "HIGH_SPEED",
        "relevant_state": {"speed_kmh": 80},
    }

    plan = composer.compose_from_guardrail(decision)

    assert plan.text.startswith("Dạ, vì an toàn của bạn, ")
    assert "80 km/h" in plan.text
    assert plan.grounded_facts == {"speed_kmh": 80}
    assert plan.is_fallback is True


def test_formal_persona_uses_only_closed_address_enum():
    composer = GroundedResponseComposer(
        persona=PersonaProfile(tone=PersonaTone.FORMAL, user_address=UserAddress.CHI)
    )

    plan = composer.compose_from_query({"status": "UNKNOWN"})

    assert plan.text.startswith("Xin thông báo tới chị: ")


def test_warm_safety_persona_uses_selected_closed_address():
    composer = GroundedResponseComposer(
        persona=PersonaProfile(tone=PersonaTone.WARM, user_address=UserAddress.ANH)
    )

    plan = composer.compose_from_guardrail({"outcome": "BLOCK_UNSAFE"})

    assert plan.text.startswith("Dạ, vì an toàn của anh, ")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"tone": "warm"}, "tone must be a PersonaTone"),
        ({"user_address": "system prompt"}, "user_address must be a UserAddress"),
    ],
)
def test_persona_profile_rejects_arbitrary_runtime_strings(kwargs, message):
    with pytest.raises(TypeError, match=message):
        PersonaProfile(**kwargs)


def test_persona_verbalizer_rejects_non_profile_runtime_value():
    with pytest.raises(TypeError, match="profile must be a PersonaProfile"):
        PersonaVerbalizer("warm")


def test_persona_does_not_modify_provider_verbalization():
    composer = GroundedResponseComposer(persona=PersonaProfile(tone=PersonaTone.WARM))
    model_text = "Em đã mở cửa xe giúp anh rồi ạ."

    plan = composer.compose_from_guardrail(
        {"outcome": "ALLOW"},
        {"success": True},
        model_verbalization=model_text,
    )

    assert plan.text == model_text
    assert plan.is_fallback is False


def test_persona_is_applied_before_final_length_limit():
    composer = GroundedResponseComposer(
        max_length=24,
        persona=PersonaProfile(tone=PersonaTone.FORMAL, user_address=UserAddress.ANH),
    )

    plan = composer.compose_from_query({"status": "UNKNOWN"})

    assert len(plan.text) == 24
    assert plan.text.endswith("...")
    assert plan.truncated is True


@pytest.mark.parametrize("invalid_max_length", [0, 1, 2, 3, -1])
def test_invalid_max_length_is_rejected(invalid_max_length):
    with pytest.raises(ValueError, match="at least 4"):
        GroundedResponseComposer(max_length=invalid_max_length)


@pytest.mark.parametrize("invalid_max_length", [4.5, "150", True, None])
def test_non_integer_max_length_is_rejected(invalid_max_length):
    with pytest.raises(TypeError, match="must be an integer"):
        GroundedResponseComposer(max_length=invalid_max_length)
