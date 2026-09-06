import pytest
import os
import sys

# Bổ sung thư mục gốc vào sys.path để import src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import VehicleState, GuardrailResult
from src.intent_classifier import IntentClassifier
from src.safety_engine import SafetyEngine
from src.guardrail import VinFastGuardrail

# Định nghĩa các đường dẫn cấu hình mặc định dùng cho test
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYWORDS_PATH = os.path.join(BASE_DIR, "config", "intent_keywords.json")
RULES_PATH = os.path.join(BASE_DIR, "config", "safety_rules.yaml")

def test_intent_classifier():
    classifier = IntentClassifier(KEYWORDS_PATH)
    
    # 1. Khớp từ khóa chuẩn Tầng 1 (Action + Entity)
    assert classifier.classify("mở cốp sau") == "open_trunk"
    assert classifier.classify("bật nắp capo") == "OPEN_BONNET"
    assert classifier.classify("ngả ghế lái") == "ad_driverseat_angle"
    assert classifier.classify("tắt đèn pha") == "turnoff_highbeam"
    
    # 2. Khớp ngữ nghĩa tự do Tầng 2 (PhoBERT ONNX Semantic Fallback)
    if classifier.model_loaded:
        assert classifier.classify("Trời nóng quá mở cốp sau ra giúp tôi với") == "open_trunk"
        assert classifier.classify("Bật cho tôi cái cốp phía sau xe nhé") == "open_trunk"
        assert classifier.classify("Cốp sau xe có mở được không") == "open_trunk"
        assert classifier.classify("lùi ghế lái ra sau một chút") == "ad_driverseat_angle"
        assert classifier.classify("tắt bớt đèn phía trước xe") == "turnoff_highbeam"
    
    # 3. Không khớp (Fallback về INTENT_UNKNOWN)
    assert classifier.classify("bật nhạc Sơn Tùng") == "INTENT_UNKNOWN"
    assert classifier.classify("") == "INTENT_UNKNOWN"

def test_safety_engine():
    engine = SafetyEngine(RULES_PATH)
    
    # 1. Test mở cốp sau (open_trunk)
    state_stopped = VehicleState(speed_kmh=0.0, gear="P")
    assert engine.evaluate("open_trunk", state_stopped) is None
    
    state_moving = VehicleState(speed_kmh=10.0, gear="D")
    res = engine.evaluate("open_trunk", state_moving)
    assert res is not None
    assert res["action"] == "BLOCK_UNSAFE"
    assert res["reason"] == "OPEN_TRUNK_UNSAFE"
    assert "Xe đang chạy với tốc độ 10.0 km/h." in res["response"]
    
    # 2. Test ngả ghế lái (ad_driverseat_angle)
    state_seat_safe = VehicleState(speed_kmh=50.0, gear="D", driver_seat_angle_deg=95.0)
    assert engine.evaluate("ad_driverseat_angle", state_seat_safe) is None
    
    state_seat_unsafe = VehicleState(speed_kmh=50.0, gear="D", driver_seat_angle_deg=120.0)
    res = engine.evaluate("ad_driverseat_angle", state_seat_unsafe)
    assert res is not None
    assert res["action"] == "BLOCK_UNSAFE"
    assert res["reason"] == "SEAT_ANGLE_UNSAFE"

    # 3. Test xác nhận mở cổng sạc khi trời mưa
    state_rain = VehicleState(speed_kmh=0.0, gear="P", rain_sensor=True)
    res = engine.evaluate("open_chargeport", state_rain)
    assert res is not None
    assert res["action"] == "CONFIRM"
    assert res["reason"] == "CHARGEPORT_RAIN_WARNING"

    # 4. Test các luật an toàn mới (R100, R101, R102)
    # R100: poweroff_vehicle (tắt nguồn xe)
    state_poweroff_safe = VehicleState(speed_kmh=0.0, gear="P")
    assert engine.evaluate("poweroff_vehicle", state_poweroff_safe) is None
    
    state_poweroff_unsafe = VehicleState(speed_kmh=60.0, gear="D")
    res = engine.evaluate("poweroff_vehicle", state_poweroff_unsafe)
    assert res is not None
    assert res["action"] == "BLOCK_UNSAFE"
    assert res["reason"] == "POWEROFF_UNSAFE"
    
    # R101: start_charging (sạc pin)
    assert engine.evaluate("start_charging", state_poweroff_safe) is None
    res = engine.evaluate("start_charging", state_poweroff_unsafe)
    assert res is not None
    assert res["action"] == "BLOCK_UNSAFE"
    assert res["reason"] == "CHARGING_UNSAFE"
    
    # R102: activate_cc (Cruise Control ga tự động)
    state_cc_safe = VehicleState(speed_kmh=45.0, gear="D")
    assert engine.evaluate("activate_cc", state_cc_safe) is None
    
    state_cc_unsafe_speed = VehicleState(speed_kmh=15.0, gear="D")
    res = engine.evaluate("activate_cc", state_cc_unsafe_speed)
    assert res is not None
    assert res["action"] == "BLOCK_UNAVAILABLE"
    assert res["reason"] == "CC_UNAVAILABLE"

def test_guardrail_facade():
    guardrail = VinFastGuardrail(KEYWORDS_PATH, RULES_PATH)
    
    # Test BLOCK_UNSAFE
    state_night_moving = VehicleState(speed_kmh=45.0, gear="D", ambient_light="NIGHT")
    result = guardrail.process("tắt đèn pha đi", state_night_moving)
    assert isinstance(result, GuardrailResult)
    assert result.intent == "turnoff_highbeam"
    assert result.action == "CONFIRM"
    assert result.reason == "NIGHT_LIGHT_CONFIRM"
    
    # Fail closed: intent hợp lệ nhưng chưa có rule gate nào match (safety_rules.yaml
    # hiện thiếu toàn bộ 45 rule ALLOW). KHÔNG được suy ra ALLOW ngầm — xem
    # docs/guardrail-integration/PHASE0_RULE_DIFF.md. ALLOW thật đến ở Pha 1 khi
    # parser condition nạp đủ 109 rule từ Driver_constraints.xlsx.
    state_day_stopped = VehicleState(speed_kmh=0.0, gear="P", ambient_light="DAY")
    result_nomatch = guardrail.process("tắt đèn pha đi", state_day_stopped)
    assert result_nomatch.action == "BLOCK_UNAVAILABLE"
    assert result_nomatch.reason == "NO_MATCHING_POLICY"

    # Test ANSWER (query intent trả facts từ snapshot, không actuator).
    # Truyền intent tường minh để không phụ thuộc T2 (PhoBERT có thể chưa nạp).
    result_speed = guardrail.process(
        "xe đang chạy tốc độ bao nhiêu", state_night_moving, intent="get_current_speed"
    )
    assert result_speed.action == "ANSWER"
    assert result_speed.reason == "STATE_VALUE_AVAILABLE"
    assert "45.0" in result_speed.response

    # Fail closed: lỗi phân loại không phải outcome policy, không đánh giá constraint
    result_unknown = guardrail.process("bật nhạc Sơn Tùng", state_day_stopped)
    assert result_unknown.action == "CLASSIFICATION_ERROR"
    assert result_unknown.reason == "INTENT_UNRESOLVED"
