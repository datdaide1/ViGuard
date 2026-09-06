import os
import time
from src.models import VehicleState, GuardrailResult
from src.intent_classifier import IntentClassifier
from src.safety_engine import SafetyEngine

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

    def process(self, user_query: str, state: VehicleState, intent: str = None) -> GuardrailResult:
        start_time = time.perf_counter()
        
        # Bước 1: Phân loại ý định của tài xế (nếu chưa truyền vào)
        if intent is None:
            intent = self.classifier.classify(user_query)
        
        # Bước 2: Đánh giá ràng buộc an toàn dựa trên ý định và trạng thái xe
        eval_result = self.safety_engine.evaluate(intent, state)
        
        # Bước 3: Xác định kết quả hành động cuối cùng
        if eval_result:
            action = eval_result["action"]
            reason = eval_result["reason"]
            response = eval_result["response"]
        else:
            # Hỗ trợ sinh câu trả lời tự động cho các truy vấn thông tin (ANSWER)
            if intent == "get_current_speed":
                action = "ANSWER"
                reason = "INFO_RETRIEVAL"
                response = f"Tốc độ hiện tại của xe là {state.speed_kmh} km/h."
            elif intent == "get_battery_pct":
                action = "ANSWER"
                reason = "INFO_RETRIEVAL"
                response = f"Dung lượng pin hiện tại là {state.battery_level}%."
            elif intent == "get_gear":
                action = "ANSWER"
                reason = "INFO_RETRIEVAL"
                response = f"Cần số xe đang ở vị trí {state.gear}."
            elif intent == "get_door_lock_status":
                action = "ANSWER"
                reason = "INFO_RETRIEVAL"
                response = "Các cửa hiện đang được khóa." if state.doors_locked else "Các cửa hiện đang được mở khóa."
            elif intent == "get_avh_status":
                action = "ANSWER"
                reason = "INFO_RETRIEVAL"
                response = "Hệ thống giữ xe tự động AVH đang bật." if state.avh else "Hệ thống giữ xe tự động AVH đang tắt."
            elif intent == "explain_feature":
                action = "ANSWER"
                reason = "INFO_RETRIEVAL"
                response = "Tính năng này được hỗ trợ đầy đủ trên hệ thống xe điện thông minh của VinFast."
            else:
                action = "ALLOW"
                reason = "NO_SAFETY_VIOLATION"
                response = "Yêu cầu hợp lệ và an toàn. Đang gửi lệnh thực thi..."
            
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        
        return GuardrailResult(
            intent=intent,
            action=action,
            response=response,
            reason=reason,
            latency_ms=round(latency_ms, 3)
        )
