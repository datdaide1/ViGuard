# generation_notes.md — Báo cáo kiểm định tập Frozen Test Set

Tài liệu đi kèm tập dữ liệu độc lập `frozen_testset.jsonl` phục vụ đánh giá phân loại ý định (intent classification) cho hệ thống Aegis.

---

### 1. Phương pháp tạo dữ liệu

- **Triệt tiêu hoàn toàn khuôn mẫu (Anti-template):** Không sử dụng bất kỳ khung câu điền khuyết cố định nào ("Mở X cho tôi", "Làm ơn X hộ nhé"). Mỗi intent được viết từ 10 góc tiếp cận giao tiếp đời thực khác nhau: câu cộc lốc/nóng vội khi đang cầm lái, câu nhờ vả lịch sự, câu gián tiếp xuất phát từ nhu cầu thực tế (nắng, tối, mỏi lưng, lạnh), câu lan man có từ đệm hoặc mệnh đề phụ gây nhiễu ngữ cảnh.
- **Tính tự nhiên và phương ngữ:** Tích hợp cân đối từ ngữ, trợ từ và đại từ 3 miền:
  - *Miền Bắc:* "hộ", "nhé", "cơ", "thế", "đấy", "bảo này".
  - *Miền Trung:* "răng", "rứa", "mô", "tê", "chừ", "hè", "giùm tui", "chớ".
  - *Miền Nam:* "dùm", "nghen", "coi", "lẹ", "quá trời", "luôn/lun", "trời đất".
  - *Trung tính:* Diễn đạt phổ thông, không mang đặc trưng vùng miền cụ thể.
- **Thiết kế Hard Negatives (106 câu):** Cố ý đưa các từ khóa của intent dễ nhầm vào câu nhưng dùng ở thể phủ định ("...chứ không phải mở cốp"), câu hỏi trạng thái ("...đã khóa chưa" thay vì ra lệnh khóa), hoặc bối cảnh dễ gây nhầm lẫn giữa các tính năng gần nghĩa (AAC vs HDA, gập gương vs hạ kính, nắp capo trước vs cốp sau).

---

### 2. Bảng tự kiểm phân bổ toàn tập (530 mẫu)

| Tiêu chí | Ngưỡng yêu cầu theo Spec | Thực tế đạt được (530 mẫu) | Tỷ lệ (%) | Trạng thái |
|---|---|---|---|---|
| **Tổng số mẫu** | ~530 mẫu (53 × 10) | 530 | 100% | ✅ Đạt |
| **`register`: lich_su** | ≥ 15% (≥ 80 câu) | 124 | 23.4% | ✅ Đạt |
| **`register`: trung_tinh** | ≥ 15% (≥ 80 câu) | 129 | 24.3% | ✅ Đạt |
| **`register`: suong_sa** | ≥ 15% (≥ 80 câu) | 141 | 26.6% | ✅ Đạt |
| **`register`: lan_man** | ≥ 15% (≥ 80 câu) | 136 | 25.7% | ✅ Đạt |
| **`dialect`: bac** | 20% – 40% (106 – 212 câu) | 148 | 27.9% | ✅ Đạt |
| **`dialect`: trung** | 20% – 40% (106 – 212 câu) | 132 | 24.9% | ✅ Đạt |
| **`dialect`: nam** | 20% – 40% (106 – 212 câu) | 142 | 26.8% | ✅ Đạt |
| **`dialect`: trung_tinh** | Phần còn lại (≤ 40%) | 108 | 20.4% | ✅ Đạt |
| **`length_bucket`: ngan** | ≥ 20% (≥ 106 câu) | 132 | 24.9% | ✅ Đạt |
| **`length_bucket`: vua** | ≥ 20% (≥ 106 câu) | 244 | 46.0% | ✅ Đạt |
| **`length_bucket`: dai** | ≥ 20% (≥ 106 câu) | 154 | 29.1% | ✅ Đạt |
| **Hard Negative** | 2 mẫu / intent (≥ 106 câu) | 106 | 20.0% | ✅ Đạt |
| **Lỗi gõ / Viết tắt** | ≤ 15% (≤ 79 câu) | 54 | 10.2% | ✅ Đạt |

---

### 3. Những intent khó viết & Cách xử lý

- `OPEN_BONNET` vs `open_trunk`: Trong tiếng Việt, người dùng xe điện thường gọi khoang trước là "cốp trước" thay vì "nắp ca-pô". Đã giải quyết bằng cách dùng các ngữ cảnh đặc thù như "kiểm tra khoang máy", "châm nước rửa kính", "khoang trước" để phân biệt với cốp chứa vali phía sau.
- `deactivate_esc`: Do hành vi này luôn bị Guardrail từ chối thực thi qua giọng nói (`NOT_VOICE_ACTIONABLE`), các câu thoại được gắn với những ngữ cảnh tài xế cố tình muốn tắt (sa lầy bùn cát, thử drift cua) để đảm bảo tính tự nhiên dù kết quả engine chặn.
- `explain_feature`: Đã chia thành 2 nhánh dữ liệu rõ rệt:
  - *Nhánh có thật (`kb_has_feature = True` → `ANSWER`):* Phanh tái sinh, trạm sạc nhanh DC, chế độ cắm trại (Camp Mode), hệ thống giữ làn LKA, ga tự động ACC, hỗ trợ lái cao tốc HDA.
  - *Nhánh hư cấu/bịa (`kb_has_feature = False` → `UNKNOWN`):* Tính năng bay vượt kẹt xe, tính năng biến hình thành tàu ngầm lặn dưới nước.

---

### 4. Giả định đã đặt

- **Quy ước viết tắt:** Chấp nhận các dạng gõ nhanh đời thường ("k", "ko", "dc", "đc", "dùm", "lun") rải rác dưới 15% tổng tập câu để mô phỏng dữ liệu ASR/bàn phím thực tế.
- **Quy ước State Hint:** Mọi mô tả bằng lời đều nhắm trúng các ngưỡng biến số quy định tại Phụ lục B:
  - Vận tốc `< 3 km/h` được hiểu là dừng hẳn / đứng yên (`speed == 0`).
  - Ngưỡng tốc độ `10 km/h` cho `unlock_doors`.
  - Ngưỡng tốc độ `16 km/h` cho `fold_mirrors`.
  - Ngưỡng tốc độ `15 km/h` cho `activate_autopark`.
  - Ngưỡng tốc độ `80 km/h` cho `open_window` và `open_sunroof`.
  - Ngưỡng pin `25%` cho `switch_drivemode_sport`, `activate_campmode`, `activate_petmode`.

---

### 5. Danh sách cặp intent cần người review kiểm tay kỹ

Các cặp này có ranh giới ngữ nghĩa hoặc từ vựng rất gần nhau:
1. `OPEN_BONNET` ↔ `open_trunk`: Khi người nói dùng từ "cốp trước" hoặc "khoang hành lý phía trước".
2. `lock_doors` ↔ `unlock_doors` ↔ `get_door_lock_status`: Các câu hỏi dạng "cửa đã chốt chưa" dễ bị mô hình nhầm thành câu lệnh "hãy chốt cửa".
3. `activate_aac` ↔ `activate_hda`: Bám đuôi kiểm soát tốc độ (Adaptive Cruise Control) vs trợ lái cao tốc toàn diện (Highway Driving Assist).
4. `activate_campmode` ↔ `activate_petmode`: Cả hai đều có mục đích giữ điều hòa khi đỗ xe số P, chỉ khác đối tượng sử dụng (người nghỉ ngơi vs vật nuôi).
5. `ad_driverseat_angle` ↔ `ad_driverseat_pos` ↔ `restore_driverseat_pos`: Các thao tác liên quan đến ghế người lái (góc lưng vs vị trí tiến lùi vs gọi bộ nhớ ghế).