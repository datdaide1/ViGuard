import os
import sys

# Bổ sung thư mục chứa file này vào sys.path để import src
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.models import VehicleState
from src.guardrail import VinFastGuardrail
from src.agent import VinFastAgent

def print_header():
    print("=" * 80)
    print("      VINFAST CONTEXT-AWARE AI GUARDRAIL ENGINE - LOCAL CLI SIMULATION")
    print("=" * 80)
    print(" Hướng dẫn sử dụng:")
    print("   1. Gõ câu thoại của tài xế để thử nghiệm Guardrail (VD: 'mở cốp sau giúp tôi')")
    print("   2. Gõ 'state' để hiển thị trạng thái xe hiện tại")
    print("   3. Gõ 'set <thuộc tính> <giá trị>' để thay đổi trạng thái xe")
    print("      Ví dụ: 'set speed_kmh 45.0', 'set gear D', 'set ambient_light NIGHT'")
    print("   4. Gõ 'exit' hoặc 'quit' để thoát chương trình")
    print("=" * 80)

def print_vehicle_state(state: VehicleState):
    print("\n[TRẠNG THÁI XE HIỆN TẠI]")
    print("-" * 50)
    state_dict = state.model_dump()
    for key, value in state_dict.items():
        print(f"  {key:<28}: {value}")
    print("-" * 50)

def main():
    # Khởi tạo Guardrail
    try:
        guardrail = VinFastGuardrail()
    except Exception as e:
        print(f"Lỗi khi nạp cấu hình Guardrail: {e}")
        sys.exit(1)

    # Khởi tạo trạng thái xe mặc định
    current_state = VehicleState(
        speed_kmh=60.0,
        gear="D",
        doors_locked=True,
        trunk_open=False,
        driver_seat_angle_deg=95.0,
        passenger_seat_angle_deg=95.0,
        has_passenger=False,
        ambient_light="NIGHT",
        rain_sensor=False,
        battery_level=85.0,
        tire_pressure_psi=32.0
    )

    print_header()
    print_vehicle_state(current_state)

    while True:
        try:
            user_input = input("\nDriver/Command >>> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nĐang thoát...")
            break

        if not user_input:
            continue

        lower_input = user_input.lower()

        if lower_input in ["exit", "quit"]:
            print("Cảm ơn bạn đã sử dụng trình giả lập. Tạm biệt!")
            break

        if lower_input == "state":
            print_vehicle_state(current_state)
            continue

        if lower_input.startswith("set "):
            parts = user_input.split(maxsplit=2)
            if len(parts) < 3:
                print("Cú pháp sai. Vui lòng gõ: set <tên_thuộc_tính> <giá_trị>")
                continue
            
            field = parts[1]
            val_str = parts[2]
            
            # Kiểm tra xem thuộc tính có tồn tại trong VehicleState không
            state_dict = current_state.model_dump()
            if field not in state_dict:
                print(f"Lỗi: Thuộc tính '{field}' không tồn tại trong VehicleState.")
                print("Các thuộc tính hợp lệ: " + ", ".join(state_dict.keys()))
                continue

            # Đổi kiểu dữ liệu phù hợp
            try:
                current_val = state_dict[field]
                if isinstance(current_val, bool):
                    if val_str.lower() in ["true", "1", "yes", "on", "có"]:
                        new_val = True
                    elif val_str.lower() in ["false", "0", "no", "off", "không"]:
                        new_val = False
                    else:
                        raise ValueError("Giá trị boolean phải là: true, false, 1, 0")
                elif isinstance(current_val, int):
                    new_val = int(val_str)
                elif isinstance(current_val, float):
                    new_val = float(val_str)
                else:  # str
                    new_val = val_str
                
                # Cập nhật trạng thái xe bằng cách tạo đối tượng mới để trigger Pydantic validation
                temp_dict = current_state.model_dump()
                temp_dict[field] = new_val
                current_state = VehicleState(**temp_dict)
                print(f"Đã cập nhật: {field} = {new_val}")
                
            except Exception as e:
                print(f"Lỗi khi cập nhật thuộc tính '{field}': {e}")
            continue

import re

def map_local_intent_to_command(intent: str, query: str = "") -> dict | None:
    """
    Ánh xạ từ ý định cứng cục bộ (Local Intent) sang cấu trúc gói lệnh thống nhất
    dạng {"command": str, "args": dict} để mô phỏng/điều khiển phần cứng.
    """
    clean_query = query.strip().lower()
    
    if intent == "open_trunk":
        return {"command": "control_trunk", "args": {"open_status": True}}
    elif intent == "close_trunk":
        return {"command": "control_trunk", "args": {"open_status": False}}
    elif intent == "open_door" or intent == "unlock_doors":
        return {"command": "control_doors_lock", "args": {"lock_status": False}}
    elif intent == "lock_doors":
        return {"command": "control_doors_lock", "args": {"lock_status": True}}
    elif intent == "open_chargeport":
        return {"command": "control_chargeport", "args": {"open_status": True}}
    elif intent == "close_chargeport":
        return {"command": "control_chargeport", "args": {"open_status": False}}
    elif intent == "open_sunroof":
        return {"command": "control_sunroof", "args": {"open_status": True}}
    elif intent == "close_sunroof":
        return {"command": "control_sunroof", "args": {"open_status": False}}
    elif intent == "open_window":
        return {"command": "adjust_window", "args": {"position": "all", "open_percentage": 100.0}}
    elif intent == "close_window":
        return {"command": "adjust_window", "args": {"position": "all", "open_percentage": 0.0}}
    elif intent == "turnoff_highbeam":
        return {"command": "control_headlights_mode", "args": {"mode": "OFF"}}
    elif intent == "turnon_highbeam":
        return {"command": "control_headlights_mode", "args": {"mode": "HIGH"}}
    elif intent == "turnoff_lowbeam":
        return {"command": "control_headlights_mode", "args": {"mode": "OFF"}}
    elif intent == "turnon_lowbeam":
        return {"command": "control_headlights_mode", "args": {"mode": "LOW"}}
    elif intent == "switch_drivemode_sport":
        return {"command": "set_drive_mode", "args": {"mode": "SPORT"}}
    elif intent == "switch_drivemode_eco":
        return {"command": "set_drive_mode", "args": {"mode": "ECO"}}
    elif intent == "switch_drivemode_normal":
        return {"command": "set_drive_mode", "args": {"mode": "NORMAL"}}
    elif intent == "turnoff_LKA":
        return {"command": "set_lka", "args": {"active": False}}
    elif intent == "turnon_LKA":
        return {"command": "set_lka", "args": {"active": True}}
    elif intent == "activate_campmode":
        return {"command": "activate_campmode", "args": {"active": True}}
    elif intent == "activate_petmode":
        return {"command": "activate_petmode", "args": {"active": True}}
    elif intent == "activate_valetmode":
        return {"command": "activate_valetmode", "args": {"active": True}}
    elif intent == "SHIFT_GEAR_REVERSE":
        return {"command": "shift_gear", "args": {"gear": "R"}}
    elif intent == "shift_gear_park":
        return {"command": "shift_gear", "args": {"gear": "P"}}
    elif intent == "activate_autopark":
        return {"command": "activate_autopark", "args": {"active": True}}
    elif intent == "fold_backseat":
        return {"command": "fold_backseat", "args": {"folded": True}}
    elif intent == "fold_mirrors":
        return {"command": "fold_mirrors", "args": {"folded": True}}
    elif intent == "activate_epb":
        return {"command": "set_epb", "args": {"active": True}}
    elif intent == "deactivate_hud":
        return {"command": "control_hud", "args": {"active": False}}
    elif intent == "activate_aac":
        return {"command": "control_cruise_control", "args": {"active": True}}
    elif intent == "ad_driverseat_angle":
        angle_match = re.search(r"(\d+)\s*(độ|deg)", clean_query)
        target_angle = float(angle_match.group(1)) if angle_match else 115.0
        return {"command": "adjust_driverseat_angle", "args": {"angle_deg": target_angle}}
    elif intent == "OPEN_BONNET":
        return {"command": "control_bonnet", "args": {"open_status": True}}
    elif intent == "activate_creepmode":
        return {"command": "control_creep_mode", "args": {"active": True}}
    elif intent == "ad_steeringwheel":
        action = "DOWN"
        if "lên" in clean_query: action = "UP"
        elif "ra" in clean_query or "tiến" in clean_query: action = "FORWARD"
        elif "vào" in clean_query or "lùi" in clean_query: action = "BACKWARD"
        return {"command": "adjust_steering_wheel", "args": {"action": action}}
    elif intent == "ad_driverseat_pos":
        action = "BACKWARD"
        if "lên" in clean_query or "tiến" in clean_query: action = "FORWARD"
        return {"command": "adjust_driverseat_position", "args": {"action": action}}
    elif intent == "restore_driverseat_pos":
        return {"command": "restore_driverseat_position", "args": {}}
    elif intent == "activate_ahb":
        return {"command": "control_ahb", "args": {"active": True}}
    elif intent == "turnon_turnsignal_right":
        return {"command": "control_turn_signal", "args": {"direction": "right", "active": True}}
    elif intent == "turnon_turnsignal_left":
        return {"command": "control_turn_signal", "args": {"direction": "left", "active": True}}
    elif intent == "turnoff_turnsignal_right":
        return {"command": "control_turn_signal", "args": {"direction": "right", "active": False}}
    elif intent == "turnoff_turnsignal_left":
        return {"command": "control_turn_signal", "args": {"direction": "left", "active": False}}
    elif intent == "turnon_interiorlight":
        return {"command": "control_interior_light", "args": {"active": True}}
    elif intent == "activate_tcs":
        return {"command": "control_traction_control", "args": {"active": True}}
    elif intent == "deactivate_esc":
        return {"command": "control_stability_control", "args": {"active": False}}
    elif intent == "open_noti_center":
        return {"command": "control_notification_center", "args": {"open_status": True}}
    elif intent == "get_current_speed":
        return {"command": "get_vehicle_status_field", "args": {"field_name": "speed"}}
    elif intent == "get_battery_pct":
        return {"command": "get_vehicle_status_field", "args": {"field_name": "battery"}}
    elif intent == "get_gear":
        return {"command": "get_vehicle_status_field", "args": {"field_name": "gear"}}
    elif intent == "get_door_lock_status":
        return {"command": "get_vehicle_status_field", "args": {"field_name": "doors_locked"}}
    elif intent == "get_avh_status":
        return {"command": "get_vehicle_status_field", "args": {"field_name": "avh"}}
        
    return None

def get_proposed_state(query: str, current_state: VehicleState, classifier, intent: str = None) -> tuple[VehicleState, str]:
    if intent is None:
        intent = classifier.classify(query)
    cmd = map_local_intent_to_command(intent, query)
    if cmd:
        return apply_tool_call_to_state(current_state, cmd["command"], cmd["args"]), intent
    return current_state, intent

def apply_tool_call_to_state(state: VehicleState, tool_name: str, args: dict) -> VehicleState:
    """Áp dụng các thay đổi từ lệnh gọi Tool của Agent lên VehicleState"""
    temp_dict = state.model_dump()
    
    if tool_name == "set_cabin_temperature":
        print(f"  [THỰC THI] Điều chỉnh nhiệt độ điều hòa sang {args.get('temp_celsius')} độ C.")
    elif tool_name == "control_media":
        print(f"  [THỰC THI] Thực hiện hành động phát nhạc: {args.get('action')}" + (f" cho bài '{args.get('song_name')}'" if args.get('song_name') else ""))
    elif tool_name == "adjust_window":
        temp_dict["window_open"] = args.get("open_percentage", 0.0) > 0.0
        print(f"  [THỰC THI] Điều chỉnh kính cửa sổ vị trí {args.get('position')} sang mức mở {args.get('open_percentage')}%")
    elif tool_name == "set_wiper_speed":
        temp_dict["wiper_speed"] = args.get("speed", "OFF")
        print(f"  [THỰC THI] Chỉnh tốc độ gạt mưa sang mức {args.get('speed')}.")
    elif tool_name == "set_drive_mode":
        temp_dict["drive_mode"] = args.get("mode", "NORMAL")
        print(f"  [THỰC THI] Đã chuyển sang chế độ lái: {args.get('mode')}.")
    elif tool_name == "control_sunroof":
        temp_dict["sunroof_open"] = args.get("open_status", False)
        print(f"  [THỰC THI] Đã {'mở' if args.get('open_status') else 'đóng'} cửa sổ trời.")
    elif tool_name == "control_doors_lock":
        temp_dict["doors_locked"] = args.get("lock_status", True)
        print(f"  [THỰC THI] Đã {'khóa' if args.get('lock_status') else 'mở khóa'} toàn bộ cửa xe.")
    elif tool_name == "control_chargeport":
        temp_dict["chargeport_open"] = args.get("open_status", False)
        print(f"  [THỰC THI] Đã {'mở' if args.get('open_status') else 'đóng'} nắp cổng sạc pin.")
    elif tool_name == "adjust_driverseat_angle":
        temp_dict["driver_seat_angle_deg"] = float(args.get("angle_deg", 95.0))
        print(f"  [THỰC THI] Đã ngả ghế lái sang góc {args.get('angle_deg')} độ.")
    elif tool_name == "adjust_passenger_seat_angle":
        temp_dict["passenger_seat_angle_deg"] = float(args.get("angle_deg", 95.0))
        print(f"  [THỰC THI] Đã ngả ghế phụ sang góc {args.get('angle_deg')} độ.")
    elif tool_name == "control_hud":
        temp_dict["hud_active"] = args.get("active", True)
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} hiển thị kính lái HUD.")
    elif tool_name == "control_headlights_mode":
        temp_dict["headlights_mode"] = args.get("mode", "AUTO")
        if args.get("mode") in ["HIGH", "LOW"]:
            temp_dict["lowbeam_mode"] = "On"
        else:
            temp_dict["lowbeam_mode"] = "Off"
        print(f"  [THỰC THI] Đã chuyển chế độ đèn pha chiếu sáng sang {args.get('mode')}.")
    elif tool_name == "control_fog_lights":
        temp_dict["fog_light"] = args.get("active", False)
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} đèn sương mù.")
    elif tool_name == "control_hazard_lights":
        temp_dict["hazard_light"] = args.get("active", False)
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} đèn khẩn cấp hazard.")
    elif tool_name == "set_avh":
        temp_dict["avh"] = args.get("active", True)
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} giữ xe tự động AVH.")
    elif tool_name == "set_epb":
        temp_dict["epb"] = args.get("active", True)
        print(f"  [THỰC THI] Đã {'kích hoạt' if args.get('active') else 'giải phóng'} phanh tay điện tử EPB.")
    elif tool_name == "set_lka":
        temp_dict["lka_active"] = args.get("active", True)
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} hỗ trợ giữ làn đường LKA.")
    elif tool_name == "activate_campmode":
        temp_dict["camp_mode_active"] = args.get("active", False)
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} chế độ cắm trại Camp Mode.")
    elif tool_name == "activate_petmode":
        temp_dict["pet_mode_active"] = args.get("active", False)
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} chế độ thú cưng Pet Mode.")
    elif tool_name == "activate_valetmode":
        temp_dict["valet_mode_active"] = args.get("active", False)
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} chế độ đỗ xe Valet Mode.")
    elif tool_name == "shift_gear":
        temp_dict["gear"] = args.get("gear", "P")
        print(f"  [THỰC THI] Đã chuyển cần số sang vị trí {args.get('gear')}.")
    elif tool_name == "activate_autopark":
        temp_dict["autopark_state"] = "ACTIVE" if args.get("active") else "INACTIVE"
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} tự động đỗ xe Autopark.")
    elif tool_name == "fold_backseat":
        temp_dict["backseat_folded"] = args.get("folded", False)
        print(f"  [THỰC THI] Đã {'gập' if args.get('folded') else 'dựng đứng'} hàng ghế hành khách phía sau.")
    elif tool_name == "fold_mirrors":
        temp_dict["folded_mirrors"] = args.get("folded", False)
        print(f"  [THỰC THI] Đã {'gập' if args.get('folded') else 'mở'} gương chiếu hậu hai bên.")
    elif tool_name == "control_trunk":
        temp_dict["trunk_open"] = args.get("open_status", False)
        print(f"  [THỰC THI] Đã {'mở' if args.get('open_status') else 'đóng'} cốp sau.")
        
    # --- XỬ LÝ CÁC CÔNG CỤ MỚI BỔ SUNG (30) ---
    elif tool_name == "set_regen_level":
        print(f"  [THỰC THI] Thiết lập mức độ phanh tái sinh về mức {args.get('level')}")
    elif tool_name == "poweroff_vehicle":
        if args.get("confirm"):
            temp_dict["speed_kmh"] = 0.0
            temp_dict["gear"] = "P"
            temp_dict["headlights_mode"] = "OFF"
            temp_dict["lowbeam_mode"] = "Off"
            temp_dict["hud_active"] = False
            print(f"  [THỰC THI] Đã tắt nguồn hệ thống xe điện hoàn toàn.")
    elif tool_name == "control_ac":
        print(f"  [THỰC THI] {'Bật' if args.get('active') else 'Tắt'} hệ thống điều hòa nhiệt độ cabin A/C.")
    elif tool_name == "control_defrost":
        print(f"  [THỰC THI] {'Bật' if args.get('active') else 'Tắt'} hệ thống sấy kính sấy phía {args.get('position')}.")
    elif tool_name == "control_seat_heating":
        print(f"  [THỰC THI] {'Bật' if args.get('active') else 'Tắt'} sưởi ấm của ghế {args.get('position')}.")
    elif tool_name == "control_seat_ventilation":
        print(f"  [THỰC THI] {'Bật' if args.get('active') else 'Tắt'} thông gió làm mát ghế {args.get('position')}.")
    elif tool_name == "control_steering_wheel_heating":
        print(f"  [THỰC THI] {'Bật' if args.get('active') else 'Tắt'} sưởi ấm vô lăng lái xe.")
    elif tool_name == "set_fan_speed":
        print(f"  [THỰC THI] Đã điều chỉnh tốc độ quạt gió sang mức {args.get('speed')}.")
    elif tool_name == "control_air_recirculation":
        print(f"  [THỰC THI] Đã chuyển sang lấy gió {'trong cabin (tuần hoàn)' if args.get('active') else 'ngoài xe'}.")
    elif tool_name == "control_charging":
        print(f"  [THỰC THI] Đã gửi lệnh {'bắt đầu sạc pin' if args.get('active') else 'ngắt/dừng sạc pin'}.")
    elif tool_name == "set_charge_limit":
        print(f"  [THỰC THI] Đã thiết lập giới hạn mức sạc pin tối đa là {args.get('limit_pct')}%")
    elif tool_name == "schedule_charging":
        print(f"  [THỰC THI] Thiết lập lịch sạc tự động bắt đầu vào lúc {args.get('start_time')}.")
    elif tool_name == "control_cruise_control":
        active = args.get('active', False)
        temp_dict["acc_state"] = "ACTIVE" if active else "INACTIVE"
        print(f"  [THỰC THI] Đã {'bật' if active else 'tắt'} ga tự động Cruise Control (CC).")
    elif tool_name == "control_hda":
        print(f"  [THỰC THI] {'Kích hoạt' if args.get('active') else 'Vô hiệu hóa'} hệ thống hỗ trợ lái cao tốc HDA.")
    elif tool_name == "control_tja":
        print(f"  [THỰC THI] {'Bật' if args.get('active') else 'Tắt'} tính năng hỗ trợ lái khi kẹt xe TJA.")
    elif tool_name == "set_cruise_speed":
        print(f"  [THỰC THI] Đã thiết lập tốc độ hành trình Cruise Control sang mức {args.get('speed_kmh')} km/h.")
    elif tool_name == "set_following_distance":
        print(f"  [THỰC THI] Thiết lập khoảng cách an toàn bám xe phía trước sang mức {args.get('distance_level')}.")
    elif tool_name == "control_camera":
        print(f"  [THỰC THI] {'Mở hiển thị' if args.get('active') else 'Đóng'} camera {args.get('camera_type')}.")
    elif tool_name == "control_bluetooth":
        print(f"  [THỰC THI] Đang thực hiện {args.get('action')} với thiết bị Bluetooth '{args.get('device_name')}'...")
    elif tool_name == "set_volume":
        print(f"  [THỰC THI] Đã điều chỉnh âm lượng loa sang mức {args.get('level')}.")
    elif tool_name == "control_media_mute":
        print(f"  [THỰC THI] Đã {'tắt tiếng' if args.get('mute') else 'bật tiếng trở lại'} loa giải trí.")
    elif tool_name == "control_navigation":
        print(f"  [THỰC THI] Định vị hành trình: thực hiện {args.get('action')}" + (f" cho địa điểm '{args.get('destination')}'" if args.get('destination') else ""))
    elif tool_name == "control_phone_call":
        print(f"  [THỰC THI] Cuộc gọi: thực hiện {args.get('action')}" + (f" tới liên hệ '{args.get('contact_name')}'" if args.get('contact_name') else ""))
    elif tool_name == "read_latest_message":
        print(f"  [THỰC THI] Trợ lý ảo đang đọc tin nhắn mới nhất đến điện thoại của bạn.")
    elif tool_name == "set_ambient_light_color":
        print(f"  [THỰC THI] Thay đổi màu đèn viền nội thất xe sang màu: {args.get('color')}.")
    elif tool_name == "control_alarm":
        print(f"  [THỰC THI] Đã {'kích hoạt' if args.get('active') else 'vô hiệu hóa'} còi và đèn cảnh báo báo động chống trộm.")
    elif tool_name == "find_my_car":
        print(f"  [THỰC THI] Đã kích hoạt nháy đèn pha và còi xe cảnh báo để giúp tìm vị trí xe.")
    elif tool_name == "get_vehicle_info":
        q_type = args.get('query_type')
        if q_type == "range":
            range_km = state.battery_level * 5.0
            print(f"  [TRUY VẤN THÔNG TIN] Quãng đường xe còn có thể di chuyển: {range_km:.1f} km.")
        elif q_type == "charge_status":
            print(f"  [TRUY VẤN THÔNG TIN] Mức pin hiện tại: {state.battery_level}%, cổng sạc sạc đang {'MỞ' if state.chargeport_open else 'ĐÓNG'}.")
        elif q_type == "charge_limit":
            print(f"  [TRUY VẤN THÔNG TIN] Giới hạn dung lượng sạc pin được đặt là: 80%.")
        elif q_type == "tire_pressure":
            print(f"  [TRUY VẤN THÔNG TIN] Áp suất lốp trung bình: {state.tire_pressure_psi} PSI (Trạng thái: An toàn).")
        elif q_type == "outside_temp":
            print(f"  [TRUY VẤN THÔNG TIN] Nhiệt độ cảm biến môi trường bên ngoài: 29 độ C.")
        elif q_type == "energy_consumption":
            print(f"  [TRUY VẤN THÔNG TIN] Mức tiêu hao năng lượng tức thời: 14.8 kWh/100 km.")
    elif tool_name == "reset_tripmeter":
        print(f"  [THỰC THI] Thiết lập lại đồng hồ hành trình Trip Odometer về 0 km.")
    elif tool_name == "call_emergency":
        print(f"  [THỰC THI] ĐANG THỰC HIỆN KẾT NỐI CUỘC GỌI KHẨN CẤP: {args.get('assistance_type')}...")
        
    # --- XỬ LÝ CÁC CÔNG CỤ BỔ SUNG ĐỂ ĐẠT 100% CONSTRAINTS COVERAGE ---
    elif tool_name == "control_bonnet":
        temp_dict["bonnet_open"] = args.get("open_status", False)
        print(f"  [THỰC THI] Đã {'mở' if args.get('open_status') else 'đóng'} nắp capo phía trước.")
    elif tool_name == "control_creep_mode":
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} chế độ bò xe (Creep Mode).")
    elif tool_name == "adjust_steering_wheel":
        print(f"  [THỰC THI] Điều chỉnh vô lăng theo hướng: {args.get('action')}.")
    elif tool_name == "adjust_driverseat_position":
        print(f"  [THỰC THI] Di chuyển vị trí ghế lái theo hướng: {args.get('action')}.")
    elif tool_name == "restore_driverseat_position":
        print(f"  [THỰC THI] Khôi phục vị trí ghế lái đã lưu.")
    elif tool_name == "control_ahb":
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} hệ thống đèn pha tự động AHB.")
    elif tool_name == "control_turn_signal":
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} đèn xi-nhan bên {args.get('direction')}.")
    elif tool_name == "control_interior_light":
        temp_dict["interior_light_on"] = args.get("active", False)
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} đèn trần nội thất cabin.")
    elif tool_name == "control_traction_control":
        temp_dict["tcs_active"] = args.get("active", False)
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} hệ thống kiểm soát lực bám đường TCS.")
    elif tool_name == "control_stability_control":
        temp_dict["esc"] = args.get("active", True)
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} hệ thống cân bằng điện tử ESC.")
    elif tool_name == "control_notification_center":
        temp_dict["noti_center_open"] = args.get("open_status", False)
        print(f"  [THỰC THI] Đã {'mở' if args.get('open_status') else 'đóng'} trung tâm thông báo.")
    elif tool_name == "get_vehicle_status_field":
        field = args.get("field_name")
        if field == "speed":
            print(f"  [TRUY VẤN THÔNG TIN] Tốc độ hiện tại: {state.speed_kmh} km/h.")
        elif field == "battery":
            print(f"  [TRUY VẤN THÔNG TIN] Dung lượng pin: {state.battery_level}%.")
        elif field == "gear":
            print(f"  [TRUY VẤN THÔNG TIN] Cần số đang ở vị trí: {state.gear}.")
        elif field == "doors_locked":
            print(f"  [TRUY VẤN THÔNG TIN] Trạng thái khóa cửa: {'Đang khóa' if state.doors_locked else 'Mở khóa'}.")
        elif field == "avh":
            print(f"  [TRUY VẤN THÔNG TIN] Kích hoạt giữ xe tự động AVH: {state.avh}.")
            
    # --- CÁC CÔNG CỤ MÔ PHỎNG 3D MỚI BỔ SUNG ---
    elif tool_name == "control_door":
        print(f"  [THỰC THI] Đã {'mở' if args.get('open_status') else 'đóng'} cánh cửa vị trí {args.get('position')}.")
    elif tool_name == "control_sunroof_tilt":
        print(f"  [THỰC THI] Đã {'hé nghiêng' if args.get('tilt_status') else 'đóng'} kính nóc.")
    elif tool_name == "adjust_seat_slide":
        print(f"  [THỰC THI] Điều chỉnh trượt ghế {args.get('position')} theo hướng {args.get('direction')}.")
    elif tool_name == "adjust_seat_height":
        print(f"  [THỰC THI] Điều chỉnh độ cao ghế {args.get('position')} theo hướng {args.get('direction')}.")
    elif tool_name == "adjust_seat_cushion_tilt":
        print(f"  [THỰC THI] Điều chỉnh độ nghiêng đệm ghế {args.get('position')} theo hướng {args.get('direction')}.")
    elif tool_name == "control_climate_auto":
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} chế độ điều hòa AUTO.")
    elif tool_name == "control_drl":
        print(f"  [THỰC THI] Đã {'bật' if args.get('active') else 'tắt'} đèn định vị ban ngày DRL.")
    elif tool_name == "set_rear_wiper_mode":
        print(f"  [THỰC THI] Đã chỉnh chế độ gạt mưa sau sang: {args.get('mode')}.")
        
    return VehicleState(**temp_dict)

def check_state_redundancy(intent: str, current_state: VehicleState, args: dict = None) -> str | None:
    """
    Kiểm tra xem yêu cầu hành động có bị trùng lặp với trạng thái hiện tại của xe không.
    Trả về câu thông báo tiếng Việt nếu đã ở trạng thái đó, ngược lại trả về None.
    """
    # 1. Đèn pha/đèn chiếu sáng
    if intent == "turnon_highbeam" or (intent == "control_headlights_mode" and args and args.get("mode") == "HIGH"):
        if current_state.headlights_mode == "HIGH":
            return "Đèn pha hiện tại đã đang bật ở chế độ chiếu xa (HIGH) rồi."
    elif intent == "turnoff_highbeam" or (intent == "control_headlights_mode" and args and args.get("mode") == "OFF"):
        if current_state.headlights_mode == "OFF":
            return "Đèn chiếu sáng hiện tại đã đang tắt (OFF) rồi."
    elif intent == "turnon_lowbeam" or (intent == "control_headlights_mode" and args and args.get("mode") == "LOW"):
        if current_state.lowbeam_mode == "On" or current_state.headlights_mode == "LOW":
            return "Đèn cốt (lowbeam) hiện tại đã đang bật rồi."
    elif intent == "turnoff_lowbeam":
        if current_state.lowbeam_mode == "Off":
            return "Đèn cốt (lowbeam) hiện tại đã đang tắt rồi."
    elif intent == "control_headlights_mode" and args:
        target_mode = args.get("mode")
        if current_state.headlights_mode == target_mode:
            return f"Đèn chiếu sáng hiện tại đã đang ở chế độ {target_mode} rồi."
    elif intent == "control_fog_lights" or intent == "turnon_foglight":
        active = args.get("active", True) if args else (intent == "turnon_foglight")
        if current_state.fog_light == active:
            return f"Đèn sương mù hiện tại đã đang {'bật' if active else 'tắt'} rồi."
    elif intent == "control_hazard_lights":
        active = args.get("active", True) if args else True
        if current_state.hazard_light == active:
            return f"Đèn cảnh báo khẩn cấp hazard hiện tại đã đang {'bật' if active else 'tắt'} rồi."

    # 2. Cửa và Cốp xe
    elif intent == "open_trunk" or (intent == "control_trunk" and args and args.get("open_status") is True):
        if current_state.trunk_open:
            return "Cốp sau hiện tại đã đang mở rồi."
    elif intent == "close_trunk" or (intent == "control_trunk" and args and args.get("open_status") is False):
        if not current_state.trunk_open:
            return "Cốp sau hiện tại đã đang đóng rồi."
    elif intent == "lock_doors" or (intent == "control_doors_lock" and args and args.get("lock_status") is True):
        if current_state.doors_locked:
            return "Cửa xe hiện tại đã đang được khóa rồi."
    elif intent == "unlock_doors" or (intent == "control_doors_lock" and args and args.get("lock_status") is False):
        if not current_state.doors_locked:
            return "Cửa xe hiện tại đã đang được mở khóa rồi."

    # 3. Cổng sạc
    elif intent == "open_chargeport" or (intent == "control_chargeport" and args and args.get("open_status") is True):
        if current_state.chargeport_open:
            return "Nắp cổng sạc hiện tại đã đang mở rồi."
    elif intent == "close_chargeport" or (intent == "control_chargeport" and args and args.get("open_status") is False):
        if not current_state.chargeport_open:
            return "Nắp cổng sạc hiện tại đã đang đóng rồi."

    # 4. Cửa sổ trời và Cửa sổ kính
    elif intent == "open_sunroof" or (intent == "control_sunroof" and args and args.get("open_status") is True):
        if current_state.sunroof_open:
            return "Cửa sổ trời hiện tại đã đang mở rồi."
    elif intent == "close_sunroof" or (intent == "control_sunroof" and args and args.get("open_status") is False):
        if not current_state.sunroof_open:
            return "Cửa sổ trời hiện tại đã đang đóng rồi."
    elif intent == "open_window":
        if current_state.window_open:
            return "Cửa sổ kính hiện tại đã đang mở rồi."
    elif intent == "close_window" or (intent == "adjust_window" and args and args.get("open_percentage", 0.0) == 0.0):
        if not current_state.window_open:
            return "Cửa sổ kính hiện tại đã đang đóng rồi."

    # 5. Phanh tay và giữ xe tự động
    elif intent == "activate_epb" or (intent == "set_epb" and args and args.get("active") is True):
        if current_state.epb:
            return "Phanh tay điện tử EPB hiện tại đã đang được kích hoạt rồi."
    elif intent == "activate_avh" or (intent == "set_avh" and args and args.get("active") is True):
        if current_state.avh:
            return "Tính năng giữ xe tự động AVH hiện tại đã đang bật rồi."

    # 6. Chế độ đặc biệt
    elif intent == "activate_campmode" or (intent == "activate_campmode" and args and args.get("active") is True):
        if current_state.camp_mode_active:
            return "Chế độ cắm trại Camp Mode hiện tại đã đang hoạt động rồi."
    elif intent == "activate_petmode" or (intent == "activate_petmode" and args and args.get("active") is True):
        if current_state.pet_mode_active:
            return "Chế độ thú cưng Pet Mode hiện tại đã đang hoạt động rồi."
    elif intent == "activate_valetmode" or (intent == "activate_valetmode" and args and args.get("active") is True):
        if current_state.valet_mode_active:
            return "Chế độ đỗ xe Valet Mode hiện tại đã đang hoạt động rồi."

    # 7. ADAS
    elif intent == "turnon_LKA" or (intent == "set_lka" and args and args.get("active") is True):
        if current_state.lka_active:
            return "Hệ thống hỗ trợ giữ làn đường LKA hiện tại đã đang bật rồi."
    elif intent == "turnoff_LKA" or (intent == "set_lka" and args and args.get("active") is False):
        if not current_state.lka_active:
            return "Hệ thống hỗ trợ giữ làn đường LKA hiện tại đã tắt rồi."
    elif intent == "control_cruise_control":
        active = args.get("active", True)
        is_active = current_state.acc_state == "ACTIVE"
        if is_active == active:
            return f"Hệ thống ga tự động Cruise Control hiện tại đã đang {'bật' if active else 'tắt'} rồi."

    # 8. Cần số
    elif intent == "shift_gear" and args:
        target_gear = args.get("gear")
        if current_state.gear == target_gear:
            return f"Cần số hiện tại đã đang ở vị trí {target_gear} rồi."
    elif intent == "SHIFT_GEAR_REVERSE":
        if current_state.gear == "R":
            return "Cần số hiện tại đã đang ở vị trí số lùi R rồi."
    elif intent == "shift_gear_park":
        if current_state.gear == "P":
            return "Cần số hiện tại đã đang ở vị trí đỗ P rồi."

    return None

# Thay đổi vòng lặp chính của main
def run_cli_loop(guardrail, agent, current_state):
    while True:
        try:
            user_input = input("\nDriver/Command >>> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nĐang thoát...")
            break

        if not user_input:
            continue

        lower_input = user_input.lower()

        if lower_input in ["exit", "quit"]:
            print("Cảm ơn bạn đã sử dụng trình giả lập. Tạm biệt!")
            break

        if lower_input == "state":
            print_vehicle_state(current_state)
            continue

        if lower_input.startswith("set "):
            parts = user_input.split(maxsplit=2)
            if len(parts) < 3:
                print("Cú pháp sai. Vui lòng gõ: set <tên_thuộc_tính> <giá_trị>")
                continue
            
            field = parts[1]
            val_str = parts[2]
            
            # Kiểm tra xem thuộc tính có tồn tại trong VehicleState không
            state_dict = current_state.model_dump()
            if field not in state_dict:
                print(f"Lỗi: Thuộc tính '{field}' không tồn tại trong VehicleState.")
                print("Các thuộc tính hợp lệ: " + ", ".join(state_dict.keys()))
                continue

            # Đổi kiểu dữ liệu phù hợp
            try:
                current_val = state_dict[field]
                if isinstance(current_val, bool):
                    if val_str.lower() in ["true", "1", "yes", "on", "có"]:
                        new_val = True
                    elif val_str.lower() in ["false", "0", "no", "off", "không"]:
                        new_val = False
                    else:
                        raise ValueError("Giá trị boolean phải là: true, false, 1, 0")
                elif isinstance(current_val, int):
                    new_val = int(val_str)
                elif isinstance(current_val, float):
                    new_val = float(val_str)
                else:  # str
                    new_val = val_str
                
                # Cập nhật trạng thái xe bằng cách tạo đối tượng mới để trigger Pydantic validation
                temp_dict = current_state.model_dump()
                temp_dict[field] = new_val
                current_state = VehicleState(**temp_dict)
                print(f"Đã cập nhật: {field} = {new_val}")
                
            except Exception as e:
                print(f"Lỗi khi cập nhật thuộc tính '{field}': {e}")
            continue

        # Nếu không phải lệnh hệ thống, xử lý như một câu thoại của tài xế
        print("-" * 60)
        print(f"Đang xử lý câu lệnh: '{user_input}'")
        
        # --- TẦNG 1: AI GUARDRAIL ENGINE (Người gác cổng đầu vào) ---
        import time
        start_time = time.perf_counter()
        
        # Phân loại intent để sinh proposed state thích hợp cho bộ lọc an toàn đầu vào
        pre_intent = guardrail.classifier.classify(user_input)
        detected_intent = pre_intent
        
        # Bỏ qua phân loại cứng nếu câu lệnh chứa các từ chỉ mức độ/tỷ lệ để chuyển tiếp tới LLM Agent
        if pre_intent in ["open_window", "close_window", "open_sunroof", "close_sunroof", "ad_driverseat_angle"]:
            import re
            if re.search(r'\d+', user_input) or any(w in lower_input for w in ["nửa", "chút", "tí", "khoảng", "tầm", "phần trăm", "%", "mức"]):
                pre_intent = "INTENT_UNKNOWN"
                detected_intent = "INTENT_UNKNOWN"
        
        # Đánh giá tính an toàn thô của câu lệnh dựa trên trạng thái xe hiện tại
        if pre_intent != "INTENT_UNKNOWN":
            proposed_state, detected_intent = get_proposed_state(user_input, current_state, guardrail.classifier, pre_intent)
            result = guardrail.process(user_input, proposed_state, pre_intent)
        else:
            result = guardrail.process(user_input, current_state, pre_intent)
            
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        
        # In kết quả của bộ lọc an toàn Guardrail
        print(f"  [AI GUARDRAIL ENGINE] Phân loại Ý định (Intent): {result.intent}")
        print(f"  [AI GUARDRAIL ENGINE] Thời gian xử lý (Latency): {latency_ms:.3f} ms")
        
        # Xử lý các quyết định an toàn của Guardrail
        if result.action.startswith("BLOCK") or result.action == "NOT_VOICE_ACTIONABLE":
            print(f"  [AI GUARDRAIL ENGINE] QUYẾT ĐỊNH           : \033[91m[{result.action}]\033[0m")
            print(f"  [AI GUARDRAIL ENGINE] Lý do (Reason)       : {result.reason}")
            print(f"  [AI GUARDRAIL ENGINE] Phản hồi an toàn     : \033[93m{result.response}\033[0m")
            print("-" * 60)
            continue
            
        elif result.action == "CONFIRM":
            print(f"  [AI GUARDRAIL ENGINE] QUYẾT ĐỊNH           : \033[93m[CONFIRM]\033[0m")
            print(f"  [AI GUARDRAIL ENGINE] Lý do (Reason)       : {result.reason}")
            print(f"  [AI GUARDRAIL ENGINE] Phản hồi an toàn     : \033[93m{result.response}\033[0m")
            
            confirm_input = input("  Xác nhận thực hiện yêu cầu này? (y/n): ").strip().lower()
            if confirm_input not in ["y", "yes", "co", "có"]:
                print(f"  \033[91m[CANCEL]\033[0m Đã hủy bỏ yêu cầu theo ý muốn của tài xế.")
                print("-" * 60)
                continue
            # Nếu tài xế xác nhận CONFIRM -> Tiếp tục đi xuống tầng Agent thực thi
            print(f"  \033[92m[CONFIRMED]\033[0m Tài xế đã đồng ý. Chuyển tiếp câu lệnh cho Agent thực thi.")
            
        else: # ALLOW / ANSWER
            print(f"  [AI GUARDRAIL ENGINE] QUYẾT ĐỊNH           : \033[92m[ALLOW]\033[0m")

        # --- TẦNG 2: MAIN AGENT / CORE LLM (Bộ điều phối & thực thi khi đã được ALLOW) ---
        if pre_intent != "INTENT_UNKNOWN":
            # Luồng cục bộ: Chuyển tiếp sang Local Control Agent (Bộ phân giải cứng)
            # 1. Kiểm tra trùng lặp trạng thái trước
            redundancy_msg = check_state_redundancy(detected_intent, current_state)
            if redundancy_msg:
                print(f"  [LOCAL CONTROL AGENT] QUYẾT ĐỊNH           : \033[93m[REDUNDANT]\033[0m")
                print(f"  [LOCAL CONTROL AGENT] Phản hồi hệ thống    : \033[93m{redundancy_msg}\033[0m")
                print("-" * 60)
                continue
                
            # 2. Thực thi cập nhật trạng thái
            proposed_state, detected_intent = get_proposed_state(user_input, current_state, guardrail.classifier, pre_intent)
            current_state = proposed_state
            print("  [LOCAL CONTROL AGENT] Đã gửi lệnh CAN-Bus thực thi tác vụ cục bộ.")
            print("  \033[92m[Cập nhật trạng thái xe thành công!]\033[0m")
            
        else:
            # Luồng đám mây: Chuyển tiếp tác vụ phức tạp sang LLM Agent xử lý
            print("  [MAIN AGENT] Đang phân tích kịch bản và lập kế hoạch cuộc gọi hàm (Function Calling)...")
            agent_res = agent.execute(user_input, current_state)
            
            if agent_res["action"] == "REPLY_CONVERSATIONAL":
                print(f"  [MAIN AGENT] Phản hồi Trợ lý ảo            : \033[96m{agent_res['response']}\033[0m")
                
            elif agent_res["action"] == "CALL_TOOLS":
                declared_tool_names = {t["function"]["name"] for t in agent.tools}
                for tc in agent_res["tool_calls"]:
                    tool_name = tc["name"]
                    tool_args = tc["args"]
                    
                    if tool_name not in declared_tool_names:
                        print(f"  \033[91m[LỖI HỆ THỐNG] Agent đề xuất gọi Tool '{tool_name}' - hành động này không nằm trong danh sách khai báo hệ thống!\033[0m")
                        continue
                        
                    # --- KIỂM TRA TRÙNG LẶP TRẠNG THÁI (Agent Tool) ---
                    redundancy_msg = check_state_redundancy(tool_name, current_state, tool_args)
                    if redundancy_msg:
                        print(f"  [MAIN AGENT] Yêu cầu gọi Tool              : \033[93m{tool_name}({tool_args})\033[0m")
                        print(f"  [MAIN AGENT] QUYẾT ĐỊNH                    : \033[93m[REDUNDANT]\033[0m")
                        print(f"  [MAIN AGENT] Phản hồi hệ thống             : \033[93m{redundancy_msg}\033[0m")
                        continue
                        
                    print(f"  [MAIN AGENT] Yêu cầu gọi Tool              : \033[93m{tool_name}({tool_args})\033[0m")
                    
                    # --- BỘ LỌC CHÉO: Double-Check Guard (Thẩm định chéo tại Vehicle Gateway) ---
                    mapped_intent = agent.map_tool_to_safety_intent(tool_name, tool_args)
                    
                    if mapped_intent:
                        # 1. Sinh đề xuất trạng thái
                        proposed_state = apply_tool_call_to_state(current_state, tool_name, tool_args)
                        # 2. Thẩm định chéo lại qua SafetyEngine trước khi bắn tín hiệu CAN Bus
                        eval_res = guardrail.safety_engine.evaluate(mapped_intent, proposed_state)
                        
                        if eval_res:
                            action = eval_res["action"]
                            reason = eval_res["reason"]
                            response = eval_res["response"]
                            
                            if action.startswith("BLOCK") or action == "NOT_VOICE_ACTIONABLE":
                                print(f"  \033[91m[DOUBLE-CHECK GUARD CHẶN AN TOÀN TẠI VEHICLE GATEWAY]\033[0m")
                                print(f"  QUYẾT ĐỊNH                                 : \033[91m[{action}]\033[0m")
                                print(f"  Lý do (Reason)                             : {reason}")
                                print(f"  Phản hồi an toàn                           : \033[93m{response}\033[0m")
                                
                            elif action == "CONFIRM":
                                print(f"  \033[93m[DOUBLE-CHECK GUARD CẢNH BÁO TẠI VEHICLE GATEWAY]\033[0m")
                                print(f"  QUYẾT ĐỊNH                                 : \033[93m[CONFIRM]\033[0m")
                                print(f"  Lý do (Reason)                             : {reason}")
                                print(f"  Phản hồi an toàn                           : \033[93m{response}\033[0m")
                                
                                confirm_input = input("  Xác nhận thực hiện yêu cầu này? (y/n): ").strip().lower()
                                if confirm_input in ["y", "yes", "co", "có"]:
                                    current_state = proposed_state
                                    print(f"  \033[92m[ALLOW]\033[0m Đã xác nhận. Đã gửi lệnh CAN-Bus thực thi thành công!")
                                else:
                                    print(f"  \033[91m[CANCEL]\033[0m Đã hủy bỏ yêu cầu theo ý muốn của tài xế.")
                        else:
                            current_state = proposed_state
                            print("  \033[92m[DOUBLE-CHECK PASS - Đã gửi lệnh CAN-Bus thực thi thành công!]\033[0m")
                    else:
                        current_state = apply_tool_call_to_state(current_state, tool_name, tool_args)
                        print("  \033[92m[Đã gửi lệnh CAN-Bus thực thi thành công!]\033[0m")
        print("-" * 60)

def main():
    # Khởi tạo Guardrail và Agent
    try:
        guardrail = VinFastGuardrail()
        agent = VinFastAgent()
    except Exception as e:
        print(f"Lỗi khi nạp cấu hình hệ thống: {e}")
        sys.exit(1)

    # Khởi tạo trạng thái xe mặc định
    current_state = VehicleState(
        speed_kmh=60.0,
        gear="D",
        doors_locked=True,
        trunk_open=False,
        driver_seat_angle_deg=95.0,
        passenger_seat_angle_deg=95.0,
        has_passenger=False,
        ambient_light="NIGHT",
        rain_sensor=False,
        battery_level=85.0,
        tire_pressure_psi=32.0
    )

    print_header()
    print_vehicle_state(current_state)
    run_cli_loop(guardrail, agent, current_state)

if __name__ == "__main__":
    main()
