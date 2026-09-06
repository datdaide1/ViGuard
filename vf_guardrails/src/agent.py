import os
import sys
import json
from typing import Dict, Any, List, Tuple, Optional
from dotenv import load_dotenv

# Bổ sung thư mục gốc vào sys.path để hỗ trợ import car_status khi chạy trực tiếp file này
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from car_status import VehicleState

# Nạp cấu hình từ tệp .env
load_dotenv()

class VinFastAgent:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.is_mock = not self.api_key or self.api_key.strip() == ""
        self.client = None
        
        if not self.is_mock:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
                print("OpenAI LLM Agent initialized successfully.")
            except Exception as e:
                print(f"[Warning] Failed to initialize OpenAI client: {e}. Falling back to Mock Mode.")
                self.is_mock = True
        else:
            print("OPENAI_API_KEY is empty. LLM Agent is running in Mock Mode.")

        # Định nghĩa danh sách các công cụ điều khiển phương tiện mở rộng (Tổng cộng 67 công cụ)
        # Bao phủ hoàn toàn 100% intents từ Driver_constraints(Constraints).csv và Driver_constraints(candidate).csv
        self.tools = [
            # --- CÁC CÔNG CỤ CŨ (25) ---
            {
                "type": "function",
                "function": {
                    "name": "set_cabin_temperature",
                    "description": "Điều chỉnh nhiệt độ cabin/điều hòa nhiệt độ mong muốn trên xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "temp_celsius": {"type": "number", "description": "Nhiệt độ mong muốn bằng độ C (từ 16.0 đến 30.0)"}
                        },
                        "required": ["temp_celsius"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_media",
                    "description": "Điều khiển phát nhạc, dừng, tiếp tục hoặc chuyển bài hát trên xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["PLAY", "PAUSE", "RESUME", "NEXT", "PREVIOUS"], "description": "Hành động phát nhạc"},
                            "song_name": {"type": "string", "description": "Tên bài hát hoặc ca sĩ (nếu có)"}
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_window",
                    "description": "Điều khiển nâng hạ kính cửa sổ xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "position": {"type": "string", "enum": ["driver", "passenger", "rear_left", "rear_right", "all"], "description": "Vị trí cửa sổ"},
                            "open_percentage": {"type": "number", "description": "Phần trăm mở kính từ 0.0 (đóng kính hoàn toàn) đến 100.0 (mở hết cỡ)"}
                        },
                        "required": ["position", "open_percentage"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_wiper_speed",
                    "description": "Chỉnh tốc độ gạt mưa của kính lái trước.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "speed": {"type": "string", "enum": ["OFF", "ONCE", "LOW", "HIGH", "MAX"], "description": "Mức độ gạt nước"}
                        },
                        "required": ["speed"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_drive_mode",
                    "description": "Thay đổi chế độ lái xe (Sport, Eco, Normal).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mode": {"type": "string", "enum": ["NORMAL", "ECO", "SPORT"], "description": "Chế độ lái"}
                        },
                        "required": ["mode"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_sunroof",
                    "description": "Điều khiển mở hoặc đóng cửa sổ trời.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "open_status": {"type": "boolean", "description": "True để mở cửa sổ trời, False để đóng"}
                        },
                        "required": ["open_status"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_doors_lock",
                    "description": "Điều khiển khóa hoặc mở khóa tất cả các cửa xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lock_status": {"type": "boolean", "description": "True để khóa cửa xe, False để mở khóa"}
                        },
                        "required": ["lock_status"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_chargeport",
                    "description": "Điều khiển đóng hoặc mở cổng sạc pin của xe điện.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "open_status": {"type": "boolean", "description": "True để mở cổng sạc, False để đóng"}
                        },
                        "required": ["open_status"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_driverseat_angle",
                    "description": "Điều chỉnh góc ngả của tựa lưng ghế lái chính.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "angle_deg": {"type": "number", "description": "Góc ngả ghế lái mong muốn bằng độ (từ 90.0 đến 130.0)"}
                        },
                        "required": ["angle_deg"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_passenger_seat_angle",
                    "description": "Điều chỉnh góc ngả tựa lưng ghế phụ bên cạnh lái xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "angle_deg": {"type": "number", "description": "Góc ngả ghế phụ mong muốn bằng độ (từ 90.0 đến 130.0)"}
                        },
                        "required": ["angle_deg"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_hud",
                    "description": "Bật hoặc tắt màn hình hiển thị thông tin kính lái HUD.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật HUD, False để tắt HUD"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_headlights_mode",
                    "description": "Điều chỉnh chế độ hoạt động của cụm đèn pha chiếu sáng phía trước.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mode": {"type": "string", "enum": ["AUTO", "HIGH", "LOW", "OFF"], "description": "Chế độ đèn pha"}
                        },
                        "required": ["mode"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_fog_lights",
                    "description": "Bật hoặc tắt hệ thống đèn sương mù của xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật đèn sương mù, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_hazard_lights",
                    "description": "Bật hoặc tắt đèn cảnh báo nguy hiểm hazard (nhấp nháy khẩn cấp cả 2 bên).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật đèn khẩn cấp, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_avh",
                    "description": "Bật hoặc tắt hệ thống giữ xe tự động Auto Vehicle Hold (AVH).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để kích hoạt giữ xe tự động AVH, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_epb",
                    "description": "Kích hoạt hoặc giải phóng phanh tay điện tử EPB.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để kéo phanh tay EPB, False để giải phóng"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_lka",
                    "description": "Bật hoặc tắt hệ thống hỗ trợ giữ làn đường chủ động LKA.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để kích hoạt giữ làn LKA, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "activate_campmode",
                    "description": "Kích hoạt hoặc vô hiệu hóa chế độ cắm trại Camp Mode để giữ nguồn điện cabin ổn định.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật chế độ cắm trại, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "activate_petmode",
                    "description": "Bật hoặc tắt chế độ thú cưng Pet Mode nhằm giữ điều hòa cabin mát mẻ khi đỗ xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật chế độ thú cưng, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "activate_valetmode",
                    "description": "Kích hoạt hoặc thoát chế độ đỗ xe Valet Mode để khóa giao diện màn hình trung tâm và giới hạn hiệu năng.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật Valet Mode, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "shift_gear",
                    "description": "Chuyển số xe sang các vị trí số P, R, N, D.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "gear": {"type": "string", "enum": ["P", "R", "N", "D"], "description": "Số xe muốn chuyển sang"}
                        },
                        "required": ["gear"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "activate_autopark",
                    "description": "Kích hoạt hệ thống hỗ trợ tự động đỗ xe Autopark.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để kích hoạt Autopark, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fold_backseat",
                    "description": "Điều khiển gập hoặc dựng hàng ghế hành khách phía sau.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "folded": {"type": "boolean", "description": "True để gập hàng ghế sau xuống phẳng, False để dựng đứng dậy"}
                        },
                        "required": ["folded"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fold_mirrors",
                    "description": "Điều khiển gập hoặc mở gương chiếu hậu hai bên hông xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "folded": {"type": "boolean", "description": "True để gập gương lại, False để mở gương ra"}
                        },
                        "required": ["folded"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_trunk",
                    "description": "Điều khiển mở hoặc đóng cốp sau của xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "open_status": {"type": "boolean", "description": "True để mở cốp sau, False để đóng cốp sau"}
                        },
                        "required": ["open_status"]
                    }
                }
            },

            # --- CÁC CÔNG CỤ TỪ DANH SÁCH CANDIDATE (30) ---
            {
                "type": "function",
                "function": {
                    "name": "set_regen_level",
                    "description": "Thiết lập mức độ phanh tái sinh để thu hồi năng lượng khi giảm tốc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "level": {"type": "number", "enum": [1, 2, 3], "description": "Mức tái sinh năng lượng (1: Thấp, 2: Vừa, 3: Cao)"}
                        },
                        "required": ["level"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "poweroff_vehicle",
                    "description": "Tắt hoàn toàn nguồn điện hệ thống xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "confirm": {"type": "boolean", "description": "True để xác nhận tắt nguồn xe"}
                        },
                        "required": ["confirm"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_ac",
                    "description": "Bật hoặc tắt hệ thống điều hòa không khí (A/C) cabin xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật điều hòa, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_defrost",
                    "description": "Điều khiển bật hoặc tắt hệ thống sấy kính lái trước hoặc sấy kính sau.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "position": {"type": "string", "enum": ["front", "rear"], "description": "Vị trí kính sấy"},
                            "active": {"type": "boolean", "description": "True để bật sấy kính, False để tắt"}
                        },
                        "required": ["position", "active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_seat_heating",
                    "description": "Điều khiển chức năng sưởi ấm của ghế lái chính hoặc ghế hành khách phụ.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "position": {"type": "string", "enum": ["driver", "passenger"], "description": "Vị trí ghế"},
                            "active": {"type": "boolean", "description": "True để bật sưởi ghế, False để tắt"}
                        },
                        "required": ["position", "active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_seat_ventilation",
                    "description": "Điều khiển quạt làm mát thông gió của ghế lái chính hoặc ghế phụ.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "position": {"type": "string", "enum": ["driver", "passenger"], "description": "Vị trí ghế"},
                            "active": {"type": "boolean", "description": "True để bật thông gió làm mát ghế, False để tắt"}
                        },
                        "required": ["position", "active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_steering_wheel_heating",
                    "description": "Điều khiển sưởi ấm vô lăng lái xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật sưởi vô lăng, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_fan_speed",
                    "description": "Điều chỉnh tốc độ quạt gió của hệ thống điều hòa.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "speed": {"type": "number", "description": "Tốc độ quạt mong muốn từ 1 (nhẹ nhất) đến 8 (mạnh nhất)"}
                        },
                        "required": ["speed"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_air_recirculation",
                    "description": "Điều khiển bật/tắt chế độ tuần hoàn gió trong xe (lấy gió trong cabin).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để lấy gió trong cabin, False để lấy gió ngoài"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_charging",
                    "description": "Điều khiển bắt đầu hoặc dừng quá trình sạc điện pin cho xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bắt đầu sạc, False để dừng sạc pin"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_charge_limit",
                    "description": "Thiết lập giới hạn sạc tối đa của pin để bảo vệ tuổi thọ pin.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit_pct": {"type": "number", "description": "Phần trăm giới hạn sạc tối đa mong muốn (từ 50 đến 100)"}
                        },
                        "required": ["limit_pct"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "schedule_charging",
                    "description": "Đặt lịch sạc pin tự động cho xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_time": {"type": "string", "description": "Thời gian bắt đầu sạc (định dạng HH:MM, ví dụ '22:00')"}
                        },
                        "required": ["start_time"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_cruise_control",
                    "description": "Điều khiển kích hoạt hoặc tắt hệ thống giữ ga tự động Cruise Control (CC).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để kích hoạt Cruise Control, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_hda",
                    "description": "Điều khiển kích hoạt hoặc tắt hỗ trợ lái xe trên đường cao tốc HDA.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật HDA, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_tja",
                    "description": "Điều khiển bật hoặc tắt tính năng hỗ trợ di chuyển khi tắc đường Traffic Jam Assist (TJA).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật TJA, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_cruise_speed",
                    "description": "Thiết lập tốc độ mục tiêu mong muốn cho hệ thống Cruise Control.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "speed_kmh": {"type": "number", "description": "Tốc độ thiết lập bằng km/h (từ 30 đến 150)"}
                        },
                        "required": ["speed_kmh"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_following_distance",
                    "description": "Thiết lập khoảng cách an toàn bám theo xe phía trước của hệ thống Adaptive Cruise Control.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "distance_level": {"type": "number", "enum": [1, 2, 3, 4], "description": "Mức khoảng cách từ 1 (gần nhất) đến 4 (xa nhất)"}
                        },
                        "required": ["distance_level"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_camera",
                    "description": "Điều khiển hiển thị camera lùi xe hoặc camera 360 độ trên màn hình trung tâm.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "camera_type": {"type": "string", "enum": ["rear", "360"], "description": "Loại camera muốn điều khiển"},
                            "active": {"type": "boolean", "description": "True để mở camera hiển thị, False để ẩn/tắt"}
                        },
                        "required": ["camera_type", "active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_bluetooth",
                    "description": "Thực hiện ghép nối (Pair) hoặc hủy ghép nối (Unpair) thiết bị điện thoại qua kết nối Bluetooth.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["PAIR", "UNPAIR"], "description": "Hành động kết nối"},
                            "device_name": {"type": "string", "description": "Tên thiết bị điện thoại muốn ghép nối"}
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_volume",
                    "description": "Điều chỉnh mức âm lượng loa của hệ thống giải trí đa phương tiện.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "level": {"type": "number", "description": "Mức âm lượng mong muốn (từ 0 đến 100)"}
                        },
                        "required": ["level"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_media_mute",
                    "description": "Tắt tiếng (Mute) hoặc mở lại tiếng (Unmute) hệ thống âm thanh giải trí.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mute": {"type": "boolean", "description": "True để tắt tiếng, False để mở lại âm thanh"}
                        },
                        "required": ["mute"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_navigation",
                    "description": "Điều khiển hệ thống định vị dẫn đường: đặt điểm đến, thêm điểm dừng, hoặc hủy dẫn đường.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["SET_DESTINATION", "ADD_STOP", "CANCEL"], "description": "Hành động dẫn đường"},
                            "destination": {"type": "string", "description": "Địa chỉ hoặc tên địa điểm cần dẫn đường đến"}
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_phone_call",
                    "description": "Thực hiện cuộc gọi đi, nhận cuộc gọi đến, từ chối hoặc cúp máy.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["MAKE", "ACCEPT", "DECLINE", "END"], "description": "Hành động cuộc gọi"},
                            "contact_name": {"type": "string", "description": "Tên liên bạ hoặc số điện thoại muốn gọi"}
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_latest_message",
                    "description": "Đọc tin nhắn SMS hoặc tin nhắn ứng dụng mới nhận gần đây nhất bằng giọng nói.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_ambient_light_color",
                    "description": "Thay đổi màu sắc của hệ thống đèn viền nội thất (Ambient Light) trang trí cabin xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "color": {"type": "string", "enum": ["RED", "BLUE", "GREEN", "YELLOW", "WHITE", "PURPLE", "ORANGE", "CYAN", "PINK", "RAINBOW"], "description": "Tên màu sắc đèn viền LED nội thất"}
                        },
                        "required": ["color"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_alarm",
                    "description": "Kích hoạt hoặc tắt hệ thống báo động chống trộm của xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật hệ thống báo động, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "find_my_car",
                    "description": "Nháy đèn pha và bấm còi xe từ xa để giúp tài xế tìm vị trí xe trong bãi đỗ.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_vehicle_info",
                    "description": "Truy vấn các thông tin cơ bản về phương tiện như quãng đường còn lại, trạng thái sạc pin, áp suất lốp, nhiệt độ ngoài trời...",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query_type": {"type": "string", "enum": ["range", "charge_status", "charge_limit", "tire_pressure", "outside_temp", "energy_consumption"], "description": "Loại thông tin muốn xem"}
                        },
                        "required": ["query_type"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "reset_tripmeter",
                    "description": "Đặt lại (reset) đồng hồ đo quãng đường hành trình tạm thời (trip odometer) về 0 km.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "call_emergency",
                    "description": "Thực hiện cuộc gọi khẩn cấp SOS hoặc liên hệ cứu hộ kỹ thuật trên đường.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "assistance_type": {"type": "string", "enum": ["SOS", "ROADSIDE"], "description": "Loại hỗ trợ khẩn cấp cần kết nối"}
                        },
                        "required": ["assistance_type"]
                    }
                }
            },

            # --- CÁC CÔNG CỤ BỔ SUNG ĐỂ ĐẢM BẢO 100% COVERAGE CHO DRIVER CONSTRAINTS ---
            {
                "type": "function",
                "function": {
                    "name": "control_bonnet",
                    "description": "Điều khiển mở hoặc đóng nắp capo phía trước của xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "open_status": {"type": "boolean", "description": "True để mở nắp capo, False để đóng"}
                        },
                        "required": ["open_status"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_creep_mode",
                    "description": "Bật hoặc tắt chế độ bò xe Creep Mode.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật Creep Mode, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_steering_wheel",
                    "description": "Điều chỉnh vị trí vô lăng lái xe (lên, xuống, tiến, lùi).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["UP", "DOWN", "FORWARD", "BACKWARD"], "description": "Hướng điều chỉnh vô lăng"}
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_driverseat_position",
                    "description": "Điều chỉnh tịnh tiến vị trí ghế lái ra xa hoặc lại gần vô lăng.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["FORWARD", "BACKWARD"], "description": "Hướng di chuyển ghế"}
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "restore_driverseat_position",
                    "description": "Khôi phục vị trí ghế lái cũ đã ghi nhớ trong cấu hình cá nhân.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_ahb",
                    "description": "Bật hoặc tắt hệ thống đèn pha thích ứng tự động AHB.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật AHB, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_turn_signal",
                    "description": "Điều khiển bật hoặc tắt đèn xi-nhan báo rẽ trái hoặc phải.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "direction": {"type": "string", "enum": ["left", "right"], "description": "Hướng báo rẽ"},
                            "active": {"type": "boolean", "description": "True để bật đèn xi-nhan, False để tắt"}
                        },
                        "required": ["direction", "active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_interior_light",
                    "description": "Điều khiển bật hoặc tắt hệ thống đèn trần chiếu sáng nội thất cabin.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật đèn trần, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_traction_control",
                    "description": "Kích hoạt hoặc tắt hệ thống kiểm soát lực bám đường TCS.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật TCS, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_stability_control",
                    "description": "Kích hoạt hoặc tắt hệ thống cân bằng điện tử ESC.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật ESC, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_notification_center",
                    "description": "Mở hoặc đóng trung tâm thông báo hệ thống.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "open_status": {"type": "boolean", "description": "True để mở trung tâm thông báo, False để đóng"}
                        },
                        "required": ["open_status"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_vehicle_status_field",
                    "description": "Truy vấn cụ thể một trường trạng thái đơn lẻ của xe (tốc độ, cần số, khóa cửa...).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "field_name": {"type": "string", "enum": ["speed", "battery", "gear", "doors_locked", "avh"], "description": "Tên trường trạng thái muốn xem"}
                        },
                        "required": ["field_name"]
                    }
                }
            },
            # --- CÁC CÔNG CỤ ĐIỀU KHIỂN MÔ PHỎNG 3D MỚI BỔ SUNG ---
            {
                "type": "function",
                "function": {
                    "name": "control_door",
                    "description": "Điều khiển mở hoặc đóng vật lý từng cánh cửa xe hoặc cả 4 cửa.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "position": {"type": "string", "enum": ["driver", "passenger", "rear_left", "rear_right", "all"], "description": "Vị trí cánh cửa"},
                            "open_status": {"type": "boolean", "description": "True để mở cánh cửa, False để đóng"}
                        },
                        "required": ["position", "open_status"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_sunroof_tilt",
                    "description": "Điều khiển hé nghiêng (tilt) hoặc đóng kính nóc/cửa sổ trời.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tilt_status": {"type": "boolean", "description": "True để hé nghiêng kính nóc, False để đóng"}
                        },
                        "required": ["tilt_status"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_seat_slide",
                    "description": "Điều khiển tiến hoặc lùi vị trí ghế lái hoặc ghế phụ trên ray trượt.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "position": {"type": "string", "enum": ["driver", "passenger"], "description": "Vị trí ghế"},
                            "direction": {"type": "string", "enum": ["FORWARD", "BACKWARD"], "description": "Hướng di chuyển tiến hoặc lùi"}
                        },
                        "required": ["position", "direction"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_seat_height",
                    "description": "Điều khiển nâng hoặc hạ độ cao toàn bộ ghế lái hoặc ghế phụ.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "position": {"type": "string", "enum": ["driver", "passenger"], "description": "Vị trí ghế"},
                            "direction": {"type": "string", "enum": ["UP", "DOWN"], "description": "Hướng nâng hoặc hạ độ cao"}
                        },
                        "required": ["position", "direction"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_seat_cushion_tilt",
                    "description": "Điều khiển nâng hoặc hạ mép trước đệm ghế lái hoặc ghế phụ.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "position": {"type": "string", "enum": ["driver", "passenger"], "description": "Vị trí ghế"},
                            "direction": {"type": "string", "enum": ["UP", "DOWN"], "description": "Hướng nâng hoặc hạ đệm ghế"}
                        },
                        "required": ["position", "direction"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_climate_auto",
                    "description": "Bật hoặc tắt chế độ điều hòa tự động AUTO.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật điều hòa AUTO, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_drl",
                    "description": "Bật hoặc tắt hệ thống đèn định vị ban ngày DRL.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active": {"type": "boolean", "description": "True để bật đèn DRL, False để tắt"}
                        },
                        "required": ["active"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_rear_wiper_mode",
                    "description": "Điều khiển gạt mưa kính phía sau xe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mode": {"type": "string", "enum": ["OFF", "ONCE", "LOW", "HIGH", "INT"], "description": "Chế độ gạt mưa sau"}
                        },
                        "required": ["mode"]
                    }
                }
            }
        ]

    def map_tool_to_safety_intent(self, func_name: str, arguments: Dict[str, Any]) -> Optional[str]:
        """
        Ánh xạ ngược từ tên Tool và tham số của Agent về Intent nhạy cảm ban đầu 
        để phục vụ lớp Double-Check Guard.
        """
        if func_name == "control_trunk" and arguments.get("open_status") is True:
            return "open_trunk"
            
        elif func_name == "control_doors_lock" and arguments.get("lock_status") is False:
            return "unlock_doors"
            
        elif func_name == "control_chargeport" and arguments.get("open_status") is True:
            return "open_chargeport"
            
        elif func_name == "control_sunroof" and arguments.get("open_status") is True:
            return "open_sunroof"
            
        elif func_name == "adjust_driverseat_angle":
            return "ad_driverseat_angle"
            
        elif func_name == "adjust_window" and arguments.get("open_percentage", 0) > 0.0:
            return "open_window"
            
        elif func_name == "set_epb" and arguments.get("active") is True:
            return "activate_epb"
            
        elif func_name == "control_hud" and arguments.get("active") is False:
            return "deactivate_hud"
            
        elif func_name == "activate_campmode" and arguments.get("active") is True:
            return "activate_campmode"
            
        elif func_name == "activate_petmode" and arguments.get("active") is True:
            return "activate_petmode"
            
        elif func_name == "activate_valetmode" and arguments.get("active") is True:
            return "activate_valetmode"
            
        elif func_name == "shift_gear":
            target_gear = arguments.get("gear")
            if target_gear == "R":
                return "SHIFT_GEAR_REVERSE"
            elif target_gear == "P":
                return "shift_gear_park"
                
        elif func_name == "activate_autopark" and arguments.get("active") is True:
            return "activate_autopark"
            
        elif func_name == "fold_backseat" and arguments.get("folded") is True:
            return "fold_backseat"
            
        elif func_name == "fold_mirrors" and arguments.get("folded") is True:
            return "fold_mirrors"
            
        elif func_name == "set_avh" and arguments.get("active") is True:
            return "activate_avh"
            
        elif func_name == "control_headlights_mode" and arguments.get("mode") == "OFF":
            return "turnoff_highbeam"

        # --- Ánh xạ ngược của các tool nhạy cảm mới bổ sung ---
        elif func_name == "poweroff_vehicle":
            return "poweroff_vehicle"
            
        elif func_name == "control_charging" and arguments.get("active") is True:
            return "start_charging"
            
        elif func_name == "control_cruise_control" and arguments.get("active") is True:
            return "activate_cc"
            
        # --- Ánh xạ ngược bổ sung để đảm bảo 100% Constraints Coverage ---
        elif func_name == "control_door" and arguments.get("open_status") is True:
            return "open_door"
        elif func_name == "control_sunroof_tilt" and arguments.get("tilt_status") is True:
            return "open_sunroof"
        elif func_name == "adjust_seat_slide" and arguments.get("position") == "driver":
            return "ad_driverseat_pos"
        elif func_name == "control_bonnet" and arguments.get("open_status") is True:
            return "OPEN_BONNET"
        elif func_name == "control_creep_mode" and arguments.get("active") is True:
            return "activate_creepmode"
        elif func_name == "adjust_steering_wheel":
            return "ad_steeringwheel"
        elif func_name == "adjust_driverseat_position":
            return "ad_driverseat_pos"
        elif func_name == "restore_driverseat_position":
            return "restore_driverseat_pos"
        elif func_name == "control_ahb" and arguments.get("active") is True:
            return "activate_ahb"
        elif func_name == "control_turn_signal" and arguments.get("active") is True:
            direction = arguments.get("direction")
            if direction == "right":
                return "turnon_turnsignal_right"
            elif direction == "left":
                return "turnon_turnsignal_left"
        elif func_name == "control_interior_light" and arguments.get("active") is True:
            return "turnon_interiorlight"
        elif func_name == "control_traction_control" and arguments.get("active") is True:
            return "activate_tcs"
        elif func_name == "control_stability_control" and arguments.get("active") is False:
            return "deactivate_esc"
        elif func_name == "control_notification_center" and arguments.get("open_status") is True:
            return "open_noti_center"
        elif func_name == "get_vehicle_status_field":
            field = arguments.get("field_name")
            if field == "speed":
                return "get_current_speed"
            elif field == "battery":
                return "get_battery_pct"
            elif field == "gear":
                return "get_gear"
            elif field == "doors_locked":
                return "get_door_lock_status"
            elif field == "avh":
                return "get_avh_status"
            
        return None

    def execute(self, query: str, state: VehicleState) -> Dict[str, Any]:
        """
        Thực thi câu thoại qua LLM Agent (hoặc Mock Mode).
        """
        if self.is_mock:
            return self._execute_mock(query)
            
        try:
            system_prompt = (
                "Bạn là trợ lý ảo AI thông minh điều khiển xe ô tô điện VinFast.\n"
                "Nhiệm vụ của bạn là nhận câu lệnh giọng nói của tài xế và gọi các Tools (hàm) thích hợp "
                "để thay đổi trạng thái xe.\n"
                "Chỉ gọi các Tool có sẵn khi câu thoại thực sự yêu cầu hành động đó.\n"
                "Nếu câu nói là chào hỏi hoặc nằm ngoài khả năng của các Tools, hãy trả lời trò chuyện "
                "bằng tiếng Việt tự nhiên, lịch sự."
            )
            
            openai_tools = []
            for t in self.tools:
                openai_tools.append(t)
                
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Trạng thái xe hiện thời: {state.model_dump_json()}\nCâu thoại tài xế: {query}"}
            ]
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=openai_tools,
                tool_choice="auto",
                temperature=0.0
            )
            
            choice = response.choices[0]
            message = choice.message
            
            if message.tool_calls:
                tool_calls_result = []
                for tc in message.tool_calls:
                    tool_calls_result.append({
                        "name": tc.function.name,
                        "args": json.loads(tc.function.arguments)
                    })
                return {
                    "action": "CALL_TOOLS",
                    "tool_calls": tool_calls_result,
                    "response": "Đang gọi hàm thực thi..."
                }
            else:
                return {
                    "action": "REPLY_CONVERSATIONAL",
                    "tool_calls": [],
                    "response": message.content
                }
                
        except Exception as e:
            print(f"[Warning] OpenAI API call failed: {e}. Falling back to Mock logic.")
            return self._execute_mock(query)

    def _execute_mock(self, query: str) -> Dict[str, Any]:
        """Cơ chế giả lập (Mock) khi không có OpenAI API Key hoặc gặp sự cố mạng"""
        clean_query = query.strip().lower()
        
        # 1. Tắt nguồn xe (poweroff_vehicle)
        if any(w in clean_query for w in ["tắt nguồn", "tắt máy", "tắt xe"]):
            return {
                "action": "CALL_TOOLS",
                "tool_calls": [{"name": "poweroff_vehicle", "args": {"confirm": True}}],
                "response": "Đang gửi yêu cầu tắt nguồn xe."
            }

        # 2. Sạc pin (control_charging)
        elif any(w in clean_query for w in ["sạc pin", "cắm sạc"]):
            action = True
            if "dừng" in clean_query or "tắt" in clean_query or "ngắt" in clean_query:
                action = False
            return {
                "action": "CALL_TOOLS",
                "tool_calls": [{"name": "control_charging", "args": {"active": action}}],
                "response": f"Đang gửi yêu cầu {'bắt đầu' if action else 'dừng'} sạc pin."
            }

        # 3. Kích hoạt Cruise Control (control_cruise_control)
        elif any(w in clean_query for w in ["cruise control", "ga tự động"]):
            action = True
            if "tắt" in clean_query or "vô hiệu hóa" in clean_query:
                action = False
            return {
                "action": "CALL_TOOLS",
                "tool_calls": [{"name": "control_cruise_control", "args": {"active": action}}],
                "response": f"Đang gửi yêu cầu {'bật' if action else 'tắt'} Cruise Control."
            }
            
        # 4. Giả lập điều hòa nhiệt độ
        elif any(w in clean_query for w in ["điều hòa", "nhiệt độ", "lạnh quá", "nóng quá", "cabin"]):
            import re
            temp = 22.0
            match = re.search(r"(\d+(\.\d+)?)", clean_query)
            if match:
                temp = float(match.group(1))
            elif "nóng" in clean_query:
                temp = 20.0  # Giảm nhiệt độ cho mát
            elif "lạnh" in clean_query:
                temp = 26.0  # Tăng nhiệt độ cho ấm
                
            return {
                "action": "CALL_TOOLS",
                "tool_calls": [{"name": "set_cabin_temperature", "args": {"temp_celsius": temp}}],
                "response": f"Đang điều chỉnh nhiệt độ cabin sang {temp} độ C."
            }
            
        # 5. Giả lập âm thanh/nhạc
        elif any(w in clean_query for w in ["nhạc", "bài hát", "ca sĩ", "âm nhạc"]):
            song = "Nhạc Lofi thư giãn"
            action = "PLAY"
            if "tắt" in clean_query or "dừng" in clean_query:
                action = "PAUSE"
            else:
                for word in ["bài", "hát", "nhạc"]:
                    if word in clean_query:
                        parts = clean_query.split(word, 1)
                        if len(parts) > 1 and parts[1].strip():
                            song = parts[1].strip()
                            
            return {
                "action": "CALL_TOOLS",
                "tool_calls": [{"name": "control_media", "args": {"action": action, "song_name": song}}],
                "response": f"Đang thực hiện phát phương tiện: {song}."
            }

        # 6. Giả lập mở cửa sổ kính
        elif any(w in clean_query for w in ["cửa sổ", "hạ kính", "lên kính", "kính xe"]):
            pct = 50.0
            if "hạ" in clean_query or "mở" in clean_query:
                pct = 100.0
            elif "đóng" in clean_query or "lên" in clean_query:
                pct = 0.0
            return {
                "action": "CALL_TOOLS",
                "tool_calls": [{"name": "adjust_window", "args": {"position": "driver", "open_percentage": pct}}],
                "response": "Đang điều chỉnh cửa kính xe lái."
            }

        # 7. Giả lập gạt mưa
        elif "gạt mưa" in clean_query:
            speed = "LOW"
            if "tắt" in clean_query:
                speed = "OFF"
            elif "nhanh" in clean_query or "mạnh" in clean_query or "tối đa" in clean_query:
                speed = "MAX"
            return {
                "action": "CALL_TOOLS",
                "tool_calls": [{"name": "set_wiper_speed", "args": {"speed": speed}}],
                "response": f"Đang chỉnh gạt mưa sang mức {speed}."
            }

        # 8. Giả lập mở cốp (Bypass Testcase)
        elif "cốp" in clean_query:
            status = True
            if "đóng" in clean_query:
                status = False
            return {
                "action": "CALL_TOOLS",
                "tool_calls": [{"name": "control_trunk", "args": {"open_status": status}}],
                "response": "Đang gửi yêu cầu điều khiển cốp sau."
            }

        # 9. Giả lập ngả ghế lái
        elif "ghế lái" in clean_query:
            import re
            angle = 115.0
            match = re.search(r"(\d+)", clean_query)
            if match:
                angle = float(match.group(1))
            return {
                "action": "CALL_TOOLS",
                "tool_calls": [{"name": "adjust_driverseat_angle", "args": {"angle_deg": angle}}],
                "response": f"Đang gửi yêu cầu ngả ghế lái sang góc {angle} độ."
            }

        # 10. Giả lập vào số lùi (R)
        elif any(w in clean_query for w in ["số lùi", "lùi xe", "số r"]):
            return {
                "action": "CALL_TOOLS",
                "tool_calls": [{"name": "shift_gear", "args": {"gear": "R"}}],
                "response": "Đang gửi yêu cầu vào số lùi R."
            }

        # Trả lời trò chuyện thông thường
        return {
            "action": "REPLY_CONVERSATIONAL",
            "tool_calls": [],
            "response": f"Chào bạn, tôi là trợ lý ảo VinFast. Tôi chưa nhận diện được yêu cầu điều khiển xe từ câu thoại: '{query}'. Bạn cần tôi giúp gì?"
        }
