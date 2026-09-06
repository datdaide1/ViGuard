"""VinFast Guardrail facade — phân loại intent + đánh giá constraint.

Bất biến FAIL-CLOSED (PRD_Guardrail_FINAL §3.3, §7.3; BR-02, BR-04, BR-09; FR-03, FR-07):
  1. Text không phân giải được intent -> LỖI PHÂN LOẠI. Không đánh giá constraint,
     không gọi actuator, KHÔNG BAO GIỜ trả ALLOW. Đây không phải outcome policy;
     Pha 1 map thành GuardrailError (kind="error").
  2. Intent hợp lệ nhưng KHÔNG rule gate nào match -> fail closed. Không suy ra ALLOW
     ngầm. ALLOW chỉ đến từ một rule ALLOW tường minh trong workbook
     (Driver_constraints.xlsx: R001, R003, R005, ... — 45 rule ALLOW; Pha 1 nạp đủ).

Trước fix 2026-09-06 (commit fail-open), nhánh `else` cuối trả ALLOW cho mọi
trường hợp không match — vi phạm trực tiếp FR-07 / BR-09.
"""
import os
import time

from src.intent_classifier import IntentClassifier
from src.models import GuardrailResult, VehicleState
from src.safety_engine import SafetyEngine

# Giá trị IntentClassifier.classify() trả khi không phân giải được intent.
_UNRESOLVED_INTENTS = {None, "", "INTENT_UNKNOWN"}

# Query intent trả lời từ state snapshot (FR-12). Pha 1 / D2: thay việc trả chuỗi
# bằng facts có cấu trúc `answer={grounded, facts}` sinh từ rule ANSWER
# (R099/R104/R106/R108); guardrail KHÔNG soạn câu tiếng Việt hoàn chỉnh — đó là
# việc của ViVi Agent.
_QUERY_FACTS = {
    "get_current_speed": lambda s: {"speed_kmh": s.speed_kmh},
    "get_battery_pct": lambda s: {"battery_pct": s.battery_level},
    "get_gear": lambda s: {"gear": s.gear},
    "get_door_lock_status": lambda s: {"doors_locked": s.doors_locked},
    "get_avh_status": lambda s: {"avh": s.avh},
}


class VinFastGuardrail:
    def __init__(self, keywords_path: str = None, rules_path: str = None):
        # Mặc định tìm các tệp cấu hình trong thư mục config cùng cấp với thư mục src
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if keywords_path is None:
            keywords_path = os.path.join(base_dir, "config", "intent_keywords.json")
        if rules_path is None:
            rules_path = os.path.join(base_dir, "config", "safety_rules.yaml")

        self.classifier = IntentClassifier(keywords_path)
        self.safety_engine = SafetyEngine(rules_path)

    def process(
        self, user_query: str, state: VehicleState, intent: str = None
    ) -> GuardrailResult:
        start_time = time.perf_counter()

        # Bước 1: Phân loại ý định của tài xế (nếu chưa truyền vào)
        if intent is None:
            intent = self.classifier.classify(user_query)

        # Fail closed 1: lỗi phân loại — dừng trước khi đánh giá constraint (BR-02, §7.3)
        if intent in _UNRESOLVED_INTENTS:
            return self._result(
                intent="INTENT_UNKNOWN",
                action="CLASSIFICATION_ERROR",  # KHÔNG phải 1 trong 7 outcome; Pha 1 -> GuardrailError
                reason="INTENT_UNRESOLVED",
                response="ViVi chưa hiểu yêu cầu này, bạn vui lòng diễn đạt lại.",
                start_time=start_time,
            )

        # Bước 2: Đánh giá ràng buộc an toàn dựa trên ý định và trạng thái xe
        eval_result = self.safety_engine.evaluate(intent, state)
        if eval_result:
            return self._result(
                intent=intent,
                action=eval_result["action"],
                reason=eval_result["reason"],
                response=eval_result["response"],
                start_time=start_time,
            )

        # Bước 3a: Query intent — trả facts từ snapshot, không actuator (FR-12)
        if intent in _QUERY_FACTS:
            return self._result(
                intent=intent,
                action="ANSWER",
                reason="STATE_VALUE_AVAILABLE",
                response=str(_QUERY_FACTS[intent](state)),  # Pha 1: answer={grounded, facts}
                start_time=start_time,
            )

        # Bước 3b: Fail closed 2 — intent hợp lệ nhưng KHÔNG rule gate nào match.
        # KHÔNG suy ra ALLOW. Khi Pha 1 nạp đủ 109 rule (kèm 45 rule ALLOW), một
        # intent hợp lệ ở state hợp lệ sẽ match rule ALLOW tường minh; còn không
        # match nghĩa là thiếu policy / mâu thuẫn -> fail closed (FR-07, BR-09).
        return self._result(
            intent=intent,
            action="BLOCK_UNAVAILABLE",
            reason="NO_MATCHING_POLICY",
            response="Tính năng hiện chưa khả dụng trong trạng thái xe hiện tại.",
            start_time=start_time,
        )

    @staticmethod
    def _result(
        *, intent: str, action: str, reason: str, response: str, start_time: float
    ) -> GuardrailResult:
        return GuardrailResult(
            intent=intent,
            action=action,
            response=response,
            reason=reason,
            latency_ms=round((time.perf_counter() - start_time) * 1000.0, 3),
        )
