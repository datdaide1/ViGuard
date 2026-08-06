"""Deterministic Vietnamese response catalog and state formatting (RSP-01).

Provides fallback template strings, approved recovery suggestions, and natural language
formatters for relevant vehicle state and query facts.
"""

from __future__ import annotations

from typing import Any, Mapping

from vivi_agent.responses.models import RecoverySuggestion

# Keywords that indicate false success claims when execution has failed
SUCCESS_CLAIM_KEYWORDS: tuple[str, ...] = (
    "thành công",
    "hoàn tất",
    "đã mở",
    "đã đóng",
    "đã bật",
    "đã tắt",
    "succeeded",
)

# Deterministic template catalog indexed by outcome and optional reason_code
VIETNAMESE_RESPONSE_CATALOG: dict[str, str] = {
    # Allow execution outcomes
    "ALLOW_SUCCESS": "Đã thực hiện yêu cầu thành công.",
    "ALLOW_FAILED": "Không thể thực hiện thao tác do lỗi thiết bị hoặc hệ thống.",
    # Guardrail block outcomes
    "BLOCK_UNSAFE": "Không thể thực hiện yêu cầu do lý do an toàn.",
    "BLOCK_UNSAFE.HIGH_SPEED": "Không thể thực hiện khi xe đang di chuyển ở tốc độ cao.",
    "BLOCK_UNSAFE.GEAR_NOT_PARK": "Vui lòng chuyển xe về vị trí đỗ (P) trước khi thực hiện.",
    "BLOCK_UNSAFE.SAFETY_INTERLOCK": "Thao tác bị chặn bởi hệ thống khóa an toàn của xe.",
    "BLOCK_UNAVAILABLE": "Tính năng hiện tại không khả dụng hoặc chưa được hỗ trợ.",
    "BLOCK_UNAVAILABLE.HARDWARE_FAULT": "Tính năng không khả dụng do cảm biến/thành phần xe gặp lỗi.",
    "BLOCK_UNAVAILABLE.FEATURE_DISABLED": "Tính năng này đã bị tắt trong phần cài đặt của xe.",
    # Confirmation outcomes
    "CONFIRM": "Yêu cầu cần được xác nhận trước khi thực hiện. Bạn có chắc chắn muốn tiếp tục không?",
    "CONFIRM.CRITICAL_ACTION": "Đây là thao tác ảnh hưởng trực tiếp đến xe. Vui lòng xác nhận để tiếp tục.",
    # Not voice actionable outcomes
    "NOT_VOICE_ACTIONABLE": "Thao tác này không thể thực hiện bằng giọng nói. Vui lòng sử dụng màn hình trung tâm.",
    # Query / Answer outcomes
    "ANSWER": "{answer_text}",
    "UNKNOWN": "Tôi chưa có thông tin về nội dung này hoặc không tìm thấy dữ liệu phù hợp.",
    # General / execution errors
    "EXECUTION_ERROR": "Đã xảy ra lỗi trong quá trình xử lý yêu cầu.",
    "DEGRADED_RESPONSE": "Hệ thống phản hồi ở chế độ giới hạn.",
}

# Approved recovery suggestions indexed by outcome or reason_code
APPROVED_RECOVERY_SUGGESTIONS: dict[str, list[RecoverySuggestion]] = {
    "BLOCK_UNSAFE": [
        RecoverySuggestion(
            code="REDUCE_SPEED",
            message_vi="Vui lòng giảm tốc độ hoặc dừng xe an toàn trước khi thực hiện.",
        ),
        RecoverySuggestion(
            code="SHIFT_PARK",
            message_vi="Chuyển số về P và bật phanh tay trước khi kích hoạt tính năng này.",
        ),
    ],
    "BLOCK_UNSAFE.HIGH_SPEED": [
        RecoverySuggestion(
            code="REDUCE_SPEED",
            message_vi="Giảm tốc độ xe xuống dưới mức cho phép để tiếp tục.",
        ),
    ],
    "BLOCK_UNSAFE.GEAR_NOT_PARK": [
        RecoverySuggestion(
            code="SHIFT_PARK",
            message_vi="Dừng xe và gạt cần số về vị trí P (Đỗ).",
        ),
    ],
    "BLOCK_UNAVAILABLE": [
        RecoverySuggestion(
            code="CHECK_SETTINGS",
            message_vi="Kiểm tra lại trạng thái kết nối hoặc cài đặt xe trên màn hình trung tâm.",
        ),
        RecoverySuggestion(
            code="CONTACT_SERVICE",
            message_vi="Liên hệ trung tâm dịch vụ VinFast nếu lỗi tiếp tục xảy ra.",
        ),
    ],
    "CONFIRM": [
        RecoverySuggestion(
            code="CONFIRM_UI_OR_VOICE",
            message_vi="Nhấn xác nhận trên màn hình trung tâm hoặc trả lời 'Có' / 'Xác nhận'.",
        ),
        RecoverySuggestion(
            code="CANCEL_VOICE",
            message_vi="Nói 'Hủy' nếu bạn muốn bỏ qua yêu cầu này.",
        ),
    ],
    "NOT_VOICE_ACTIONABLE": [
        RecoverySuggestion(
            code="USE_TOUCHSCREEN",
            message_vi="Thực hiện thao tác trực tiếp trên màn hình cảm ứng trung tâm.",
        ),
    ],
    "ALLOW_FAILED": [
        RecoverySuggestion(
            code="RETRY_LATER",
            message_vi="Thử lại thao tác sau ít phút.",
        ),
        RecoverySuggestion(
            code="CHECK_DASHBOARD",
            message_vi="Kiểm tra bảng điều khiển để xác minh trạng thái thiết bị.",
        ),
    ],
    "UNKNOWN": [
        RecoverySuggestion(
            code="REPHRASE_QUERY",
            message_vi="Thử diễn đạt lại câu hỏi hoặc yêu cầu kiểm tra trạng thái xe cụ thể.",
        ),
    ],
}


def get_catalog_template(outcome: str, reason_code: str | None = None) -> str:
    """Retrieve the most specific deterministic Vietnamese template for an outcome."""
    if reason_code:
        specific_key = f"{outcome}.{reason_code}"
        if specific_key in VIETNAMESE_RESPONSE_CATALOG:
            return VIETNAMESE_RESPONSE_CATALOG[specific_key]

    if outcome in VIETNAMESE_RESPONSE_CATALOG:
        return VIETNAMESE_RESPONSE_CATALOG[outcome]

    return VIETNAMESE_RESPONSE_CATALOG.get("EXECUTION_ERROR", "Đã xảy ra lỗi.")


def get_approved_recovery_suggestions(outcome: str, reason_code: str | None = None) -> list[RecoverySuggestion]:
    """Retrieve approved recovery suggestions for a given outcome or reason code."""
    suggestions: list[RecoverySuggestion] = []
    seen_codes: set[str] = set()

    if reason_code:
        specific_key = f"{outcome}.{reason_code}"
        if specific_key in APPROVED_RECOVERY_SUGGESTIONS:
            for item in APPROVED_RECOVERY_SUGGESTIONS[specific_key]:
                if item.code not in seen_codes:
                    suggestions.append(item)
                    seen_codes.add(item.code)

    if outcome in APPROVED_RECOVERY_SUGGESTIONS:
        for item in APPROVED_RECOVERY_SUGGESTIONS[outcome]:
            if item.code not in seen_codes:
                suggestions.append(item)
                seen_codes.add(item.code)

    return suggestions


def format_relevant_state(state: Mapping[str, Any] | None) -> str:
    """Format typed vehicle relevant state facts into clear Vietnamese sentences.

    Does not invent state properties or values. Only formats provided keys.
    """
    if not state:
        return ""

    formatted_parts: list[str] = []

    # Format battery percentage
    if "battery_pct" in state:
        formatted_parts.append(f"Dung lượng pin: {state['battery_pct']}%")
    elif "battery_level" in state:
        formatted_parts.append(f"Mức pin: {state['battery_level']}%")

    # Format speed
    if "speed_kmh" in state:
        formatted_parts.append(f"Tốc độ: {state['speed_kmh']} km/h")
    elif "speed" in state:
        formatted_parts.append(f"Tốc độ: {state['speed']} km/h")

    # Format gear
    if "gear" in state:
        formatted_parts.append(f"Vị trí số: {state['gear']}")

    # Format doors / trunk / hood
    if "door_status" in state:
        formatted_parts.append(f"Trạng thái cửa: {state['door_status']}")
    if "trunk_open" in state:
        status_str = "đang mở" if state["trunk_open"] else "đã đóng"
        formatted_parts.append(f"Cốp xe: {status_str}")

    # Format tire pressure
    if "tire_pressure" in state:
        pressures = state["tire_pressure"]
        if isinstance(pressures, Mapping):
            formatted_pressures = ", ".join(f"{k}: {v} PSI" for k, v in pressures.items())
            formatted_parts.append(f"Áp suất lốp ({formatted_pressures})")
        else:
            formatted_parts.append(f"Áp suất lốp: {pressures} PSI")

    # Format climate / temperature
    if "climate_temp" in state:
        formatted_parts.append(f"Nhiệt độ điều hòa: {state['climate_temp']}°C")
    elif "temperature" in state:
        formatted_parts.append(f"Nhiệt độ: {state['temperature']}°C")

    # Format general remaining state keys if not already handled
    handled_keys = {
        "battery_pct",
        "battery_level",
        "speed_kmh",
        "speed",
        "gear",
        "door_status",
        "trunk_open",
        "tire_pressure",
        "climate_temp",
        "temperature",
    }
    for k, v in state.items():
        if k not in handled_keys:
            formatted_parts.append(f"{k}: {v}")

    return ". ".join(formatted_parts) + ("." if formatted_parts else "")
