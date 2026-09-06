import os
import yaml
from typing import Dict, Any, List, Optional
from src.models import VehicleState

class SafetyEngine:
    def __init__(self, rules_path: str):
        self.rules_path = rules_path
        self.policies = []
        self._load_rules()

    def _load_rules(self):
        if not os.path.exists(self.rules_path):
            raise FileNotFoundError(f"Safety rules config file not found: {self.rules_path}")
            
        with open(self.rules_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        self.policies = config.get("policies", [])

    def evaluate_condition(self, val: Any, op: str, expected: Any) -> bool:
        try:
            # Chuyển đổi kiểu dữ liệu sang float nếu so sánh số học để tránh lỗi sai kiểu (ví dụ: float vs int)
            if isinstance(val, (int, float)) and isinstance(expected, (int, float)):
                val = float(val)
                expected = float(expected)
                
            if op == "==":
                return val == expected
            elif op == "!=":
                return val != expected
            elif op == ">":
                return val > expected
            elif op == "<":
                return val < expected
            elif op == ">=":
                return val >= expected
            elif op == "<=":
                return val <= expected
            else:
                return False
        except Exception:
            return False

    def evaluate(self, intent: str, state: VehicleState) -> Optional[Dict[str, Any]]:
        # Tìm các chính sách áp dụng cho intent này
        matching_policies = [p for p in self.policies if p.get("intent") == intent]
        
        for policy in matching_policies:
            target_state = policy.get("target_state", {})
            logic = policy.get("logic", "AND").upper()
            
            cond_results = []
            state_dict = state.model_dump()
            
            for field, cond in target_state.items():
                if field not in state_dict:
                    cond_results.append(False)
                    continue
                
                op = cond.get("operator")
                expected = cond.get("value")
                actual_val = state_dict[field]
                
                res = self.evaluate_condition(actual_val, op, expected)
                cond_results.append(res)
            
            # Kết hợp kết quả điều kiện theo logic AND/OR
            if not cond_results:
                triggered = True
            elif logic == "OR":
                triggered = any(cond_results)
            else:  # Mặc định là AND
                triggered = all(cond_results)
                
            if triggered:
                enforcement = policy.get("enforcement", {})
                action = enforcement.get("action", "BLOCK")
                reason = enforcement.get("reason", "SAFETY_VIOLATION")
                msg_template = enforcement.get("message_template", "Yêu cầu bị chặn vì lý do an toàn.")
                
                # Format động message template bằng các thuộc tính của VehicleState
                try:
                    message = msg_template.format(**state_dict)
                except Exception:
                    message = msg_template
                    
                return {
                    "action": action,
                    "reason": reason,
                    "response": message
                }
                
        return None
