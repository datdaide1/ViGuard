from pydantic import BaseModel, Field
from car_status import VehicleState

class GuardrailResult(BaseModel):
    intent: str
    action: str          # "ALLOW", "BLOCK_UNSAFE", "BLOCK_UNAVAILABLE", "CONFIRM", "NOT_VOICE_ACTIONABLE", "ANSWER", "UNKNOWN"
    response: str        # Phản hồi bằng ngôn ngữ tự nhiên từ động cơ Guardrail
    reason: str          # Mã định danh lý do lỗi (Reason Code)
    latency_ms: float    # Độ trễ thực thi (miliseconds)
