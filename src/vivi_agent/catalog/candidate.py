"""Agent capability candidates sourced from ``Intents_Candidate.xlsx``.

This is an Agent-side capability inventory only.  It deliberately contains no
Guardrail conditions, decisions, or safety policy.  Parameterized capabilities
use the common ``value`` tool argument until vehicle-specific adapters expose a
more specialized typed contract.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateCapability:
    intent: str
    description: str
    operation: str = "execute"
    requires_value: bool = False
    kind: str = "action"


_ROWS = (
    ("shift_gear_drive", "Chuyển cần số sang chế độ D."),
    ("shift_gear_neutral", "Chuyển cần số sang chế độ N."),
    ("set_regenlevel", "Thiết lập mức tái tạo năng lượng khi giảm tốc.", "set", True),
    ("poweroff_vehicle", "Tắt nguồn xe."),
    ("turnon_ac", "Bật hệ thống điều hòa."),
    ("turnoff_ac", "Tắt hệ thống điều hòa."),
    ("set_temperature", "Điều chỉnh nhiệt độ điều hòa.", "set", True),
    ("turnon_defrost_front", "Bật sấy kính trước."),
    ("turnon_defrost_rear", "Bật sấy kính sau."),
    ("turnoff_defrost_front", "Tắt sấy kính trước."),
    ("turnoff_defrost_rear", "Tắt sấy kính sau."),
    ("turnon_seatheating", "Bật sưởi ghế."),
    ("turnoff_seatheating", "Tắt sưởi ghế."),
    ("turnon_seatventilation", "Bật thông gió ghế."),
    ("turnoff_seatventilation", "Tắt thông gió ghế."),
    ("turnon_steeringwheelheating", "Bật sưởi vô lăng."),
    ("turnoff_steeringwheelheating", "Tắt sưởi vô lăng."),
    ("set_fanspeed", "Điều chỉnh tốc độ quạt điều hòa.", "set", True),
    ("turnon_recirculation", "Bật chế độ tuần hoàn gió trong xe."),
    ("turnoff_recirculation", "Tắt chế độ tuần hoàn gió trong xe."),
    ("set_wiperspeed", "Điều chỉnh tốc độ gạt mưa.", "set", True),
    ("close_chargeport", "Đóng nắp cổng sạc."),
    ("start_charging", "Bắt đầu quá trình sạc pin."),
    ("stop_charging", "Dừng quá trình sạc pin."),
    ("set_chargelimit", "Thiết lập giới hạn mức sạc pin.", "set", True),
    ("schedule_charging", "Thiết lập lịch sạc.", "set", True),
    ("activate_cc", "Bật Cruise Control."),
    ("deactivate_cc", "Tắt Cruise Control."),
    ("deactivate_aac", "Tắt Adaptive Cruise Control."),
    ("deactivate_hda", "Tắt Highway Driving Assist."),
    ("turnon_LKA", "Bật Lane Keeping Assist."),
    ("activate_tja", "Bật Traffic Jam Assist."),
    ("deactivate_tja", "Tắt Traffic Jam Assist."),
    ("set_cruise_speed", "Thiết lập tốc độ Cruise Control.", "set", True),
    ("set_following_distance", "Thiết lập khoảng cách bám xe phía trước.", "set", True),
    ("turnon_rearcamera", "Mở camera lùi."),
    ("turnoff_rearcamera", "Tắt camera lùi."),
    ("turnon_360camera", "Mở camera 360."),
    ("turnoff_360camera", "Tắt camera 360."),
    ("close_window", "Đóng cửa sổ xe."),
    ("close_sunroof", "Đóng cửa sổ trời."),
    ("close_trunk", "Đóng cốp sau."),
    ("pair_bluetooth", "Ghép nối thiết bị Bluetooth.", "set", True),
    ("unpair_bluetooth", "Hủy ghép nối Bluetooth.", "set", True),
    ("play_music", "Phát nhạc."),
    ("pause_music", "Tạm dừng phát nhạc."),
    ("resume_music", "Tiếp tục phát nhạc."),
    ("next_track", "Chuyển sang bài hát tiếp theo."),
    ("previous_track", "Quay lại bài hát trước."),
    ("set_volume", "Điều chỉnh âm lượng.", "set", True),
    ("mute_media", "Tắt tiếng hệ thống giải trí."),
    ("unmute_media", "Bật lại âm thanh hệ thống giải trí."),
    ("set_navigation_destination", "Thiết lập điểm đến dẫn đường.", "set", True),
    ("add_navigation_stop", "Thêm điểm dừng trên lộ trình.", "set", True),
    ("cancel_navigation", "Hủy dẫn đường."),
    ("get_eta", "Xem thời gian dự kiến đến nơi.", "query", False, "query"),
    ("make_phonecall", "Thực hiện cuộc gọi.", "set", True),
    ("accept_call", "Nhận cuộc gọi đến."),
    ("decline_call", "Từ chối cuộc gọi."),
    ("end_call", "Kết thúc cuộc gọi."),
    ("read_message", "Đọc tin nhắn đến."),
    ("turnon_foglight", "Bật đèn sương mù."),
    ("turnoff_foglight", "Tắt đèn sương mù."),
    ("set_ambientlight_color", "Thay đổi màu đèn nội thất.", "set", True),
    ("turnon_alarm", "Bật hệ thống báo động."),
    ("turnoff_alarm", "Tắt hệ thống báo động."),
    ("find_my_car", "Xác định vị trí xe."),
    ("get_range_remaining", "Xem quãng đường còn có thể di chuyển.", "query", False, "query"),
    ("get_chargestatus", "Xem trạng thái sạc hiện tại.", "query", False, "query"),
    ("get_chargelimit", "Xem giới hạn mức sạc hiện tại.", "query", False, "query"),
)

CANDIDATE_CAPABILITIES = tuple(CandidateCapability(*row) for row in _ROWS)
CANDIDATE_INTENTS = frozenset(item.intent for item in CANDIDATE_CAPABILITIES)
CANDIDATE_QUERY_INTENTS = frozenset(
    item.intent for item in CANDIDATE_CAPABILITIES if item.kind == "query"
)
CANDIDATE_ACTION_INTENTS = CANDIDATE_INTENTS - CANDIDATE_QUERY_INTENTS
CANDIDATE_SOURCE_CHECKSUM = "sha256:d8eec859dcf735fd2a240136ff73259da7a7ca8ab0fc7e78275d8c9042681640"

if len(CANDIDATE_CAPABILITIES) != 70 or len(CANDIDATE_INTENTS) != 70:
    raise RuntimeError("Intents_Candidate.xlsx capability inventory must contain 70 unique intents")
_actual_checksum = "sha256:" + hashlib.sha256(
    json.dumps(_ROWS, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
).hexdigest()
if _actual_checksum != CANDIDATE_SOURCE_CHECKSUM:
    raise RuntimeError("Agent candidate capability inventory checksum mismatch")
