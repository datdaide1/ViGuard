# Hướng dẫn tạo Frozen Independent Test Set — ViGuard intent classification

> **Bản này tự chứa.** Người/agent thực hiện KHÔNG cần và KHÔNG được đọc bất kỳ
> phần nào khác của dự án. Mọi thứ cần thiết nằm trong tài liệu này.
> Nếu thấy thiếu thông tin để quyết định, **dừng lại và hỏi**, không tự suy đoán.

---

## 1. Bối cảnh (đọc kỹ, quyết định thiết kế phụ thuộc vào đây)

ViGuard là một Guardrail cho trợ lý giọng nói trên xe điện. Người dùng gõ một
câu lệnh tiếng Việt (ví dụ "mở cửa xe cho tôi"). Hệ thống làm 2 bước:

1. **Phân loại ý định (intent classification)** — ánh xạ câu vào đúng 1 trong
   **53 nhãn intent** cố định (danh mục ở §5). Đây là phần tài liệu này kiểm thử.
2. Đánh giá ràng buộc an toàn theo trạng thái xe → ra 1 outcome. Phần này đã
   được kiểm thử đầy đủ (100% chính xác) và **không** phải việc của bạn.

**Vấn đề đang giải quyết:** tập dữ liệu hiện có (dùng để phát triển) được sinh
theo khuôn mẫu, nhiều câu gần trùng nhau. Đánh giá bộ phân loại trên chính tập
đó — kể cả chia train/test — bị rò rỉ (leakage): câu gần-trùng của cùng intent
rơi vào cả 2 phía, làm số liệu bị thổi phồng.

**Mục tiêu của bạn:** tạo một **tập kiểm thử độc lập, đóng băng**, viết theo
cách **khác hoàn toàn** tập cũ, để đo chính xác bộ phân loại intent hoạt động
tốt đến đâu trên câu nói thật, chưa từng thấy.

Tập này sẽ **không bao giờ** được dùng để train. Nó chỉ dùng để đánh giá. Vì
vậy chất lượng và tính đa dạng của nó quyết định độ tin cậy của mọi con số về
sau.

---

## 2. Nhiệm vụ của bạn — chính xác cái gì phải nộp

Sinh ra **N dòng** (xem §8 để biết N và phân bổ). Mỗi dòng là một object JSON
với các trường ở §3. Về bản chất mỗi dòng gồm:

- **một câu tiếng Việt tự nhiên** một tài xế thật có thể gõ/nói;
- **nhãn intent đúng** cho câu đó (chọn từ đúng 53 nhãn ở §5);
- một ít **metadata** để người khác kiểm tra độ cân bằng (giọng vùng miền,
  văn phong, độ dài…);
- **tùy chọn** một mô tả ngắn bằng lời về ngữ cảnh trạng thái xe (`state_hint`),
  chỉ khi câu ám chỉ hoặc cần một tình huống cụ thể.

Bạn **KHÔNG** phải:

- tính outcome (ALLOW/BLOCK/…) — chủ dự án tự suy ra bằng engine;
- viết object `vehicle_state` dạng JSON — chỉ cần `state_hint` bằng lời;
- gán `rule_id`;
- đọc hay tham chiếu tập dữ liệu cũ (bạn không có nó, và không được mô phỏng
  văn phong của nó).

Ngoài file dữ liệu, nộp kèm một file `generation_notes.md` ngắn (§9).

---

## 3. Định dạng output

### 3.1. File dữ liệu: `frozen_testset.jsonl`

Một object JSON mỗi dòng (JSON Lines), mã hóa UTF-8, không BOM. Các trường:

| Trường | Bắt buộc | Kiểu | Mô tả |
|---|---|---|---|
| `id` | ✅ | string | `FROZEN-<số thứ tự 4 chữ số>`, ví dụ `FROZEN-0001`. Duy nhất, liên tục. |
| `utterance` | ✅ | string | Câu lệnh tiếng Việt. 1 câu (có thể có mệnh đề phụ / câu nhiễu). Không xuống dòng. Không kèm dịch/giải thích. |
| `intent` | ✅ | string | **Đúng một** nhãn từ §5. Phân biệt hoa/thường (xem cảnh báo §5). |
| `is_hard_negative` | ✅ | bool | `true` nếu câu này *nghe giống* một intent khác nhưng thực chất là `intent` ở trên. Xem §7. |
| `sounds_like` | khi `is_hard_negative=true` | string\|null | Nhãn intent mà câu này dễ bị nhầm sang. Phải khác `intent`. `null` nếu không phải hard negative. |
| `dialect` | ✅ | enum | `"bac"` \| `"trung"` \| `"nam"` \| `"trung_tinh"` (trung tính, không đặc trưng vùng). |
| `register` | ✅ | enum | `"lich_su"` (lịch sự/trang trọng) \| `"trung_tinh"` \| `"suong_sa"` (suồng sã/cộc lốc) \| `"lan_man"` (lan man, nhiều từ đệm). |
| `length_bucket` | ✅ | enum | `"ngan"` (≤6 từ) \| `"vua"` (7–15 từ) \| `"dai"` (>15 từ). |
| `state_hint` | ⭕ tùy chọn | string\|null | Mô tả **bằng lời** ngữ cảnh trạng thái xe mà câu ám chỉ hoặc cần, ví dụ `"xe đang chạy ~60 km/h"`, `"xe đỗ P, trời mưa"`, `"pin dưới 20%"`, `"đang bật chế độ cắm trại"`. `null` nếu câu không ám chỉ ngữ cảnh nào. Xem §6.6 + Phụ lục A/B để biết yếu tố nào đáng nêu cho từng intent. |
| `notes` | ⭕ tùy chọn | string\|null | Ghi chú tự do cho người review (vì sao câu này khó, biến thể từ vựng đặc biệt…). |

Ví dụ 3 dòng hợp lệ:

```json
{"id":"FROZEN-0001","utterance":"Cho anh mở giúp cái cốp sau với, tay xách nặng quá.","intent":"open_trunk","is_hard_negative":false,"sounds_like":null,"dialect":"trung_tinh","register":"lich_su","length_bucket":"vua","state_hint":"xe vừa tấp vào lề, gần như dừng hẳn","notes":null}
{"id":"FROZEN-0002","utterance":"ê xe ơi tắt cái xi nhan bên phải đi, nãy quẹo xong quên tắt","intent":"turnoff_turnsignal_right","is_hard_negative":false,"sounds_like":null,"dialect":"nam","register":"suong_sa","length_bucket":"vua","state_hint":null,"notes":null}
{"id":"FROZEN-0003","utterance":"khoá hết cửa lại giùm cái","intent":"lock_doors","is_hard_negative":true,"sounds_like":"unlock_doors","dialect":"trung_tinh","register":"suong_sa","length_bucket":"ngan","state_hint":null,"notes":"dễ nhầm sang unlock_doors vì cùng nói về cửa"}
```

### 3.2. File ghi chú: `generation_notes.md`

Xem §9 để biết nội dung.

---

## 4. Tập này dùng để làm gì (để bạn hiểu vì sao các ràng buộc quan trọng)

Chủ dự án sẽ:

1. Chạy từng `utterance` qua bộ phân loại → so `predicted_intent` với `intent` của bạn → tính accuracy, F1 theo từng intent, ma trận nhầm lẫn.
2. Với dòng có `state_hint`, quy `state_hint` thành trạng thái xe cụ thể, chạy qua engine → có `expected_outcome`, rồi đo pipeline end-to-end.
3. **Đóng băng** file. Không sửa, không thêm, không dùng để train.

Vì tập này là "thước đo vàng" duy nhất độc lập, một câu viết ẩu / trùng khuôn /
gán nhãn sai sẽ làm sai lệch mọi kết luận. Chất lượng > số lượng.

---

## 5. Danh mục 53 intent

> ⚠️ **Tên intent phân biệt HOA/thường.** Đa số là chữ thường có gạch dưới.
> **4 nhãn có phần viết HOA — chép y nguyên, không tự chuẩn hoá thành chữ thường:**
> `OPEN_BONNET`, `AD_WIPER_MAX`, `SHIFT_GEAR_REVERSE`, `turnoff_LKA`.
> Giá trị `intent` trong output phải khớp **từng ký tự** với cột "Nhãn" dưới đây.

Cột "State đáng nêu" = biến trạng thái xe mà intent này phụ thuộc — nếu bạn viết
câu ám chỉ ngữ cảnh, hãy nhắm vào các biến đó trong `state_hint`. Cột "Outcome
có thể" cho biết intent này có mấy nhánh kết quả (nên viết câu ở nhiều ngữ cảnh
khác nhau để phủ các nhánh).

### Nhóm Cửa / khoang chứa

| Nhãn | Người dùng muốn gì | State đáng nêu | Outcome có thể |
|---|---|---|---|
| `open_door` | Mở cửa xe (cửa lái/cửa hành khách) | gear, speed | ALLOW, BLOCK_UNSAFE |
| `open_trunk` | Mở cốp sau | speed | ALLOW, BLOCK_UNSAFE |
| `open_chargeport` | Mở nắp/cổng sạc điện | speed, rain_sensor | ALLOW, BLOCK_UNSAFE, CONFIRM |
| `lock_doors` | Khóa tất cả các cửa | (không) | ALLOW |
| `unlock_doors` | Mở khóa các cửa | speed | ALLOW, BLOCK_UNSAFE |
| `OPEN_BONNET` | Mở nắp capo trước (khoang động cơ/frunk) | gear, speed | ALLOW, BLOCK_UNSAFE |

### Nhóm Chiếu sáng / gạt mưa

| Nhãn | Người dùng muốn gì | State đáng nêu | Outcome có thể |
|---|---|---|---|
| `turnon_highbeam` | Bật đèn pha (đèn chiếu xa) | ambient_light | ALLOW, CONFIRM |
| `turnoff_highbeam` | Tắt đèn pha | ambient_light | ALLOW, CONFIRM |
| `turnon_lowbeam` | Bật đèn cốt (đèn chiếu gần) | ambient_light | ALLOW, CONFIRM |
| `turnoff_lowbeam` | Tắt đèn cốt | ambient_light | ALLOW, CONFIRM |
| `AD_WIPER_MAX` | Chỉnh gạt mưa lên mức nhanh nhất/tối đa | rain_sensor | ALLOW, CONFIRM |
| `activate_ahb` | Bật đèn pha tự động (Auto High Beam) | fog_light | ALLOW, BLOCK_UNAVAILABLE |
| `turnon_corneringlight` | Bật đèn soi góc cua | lowbeam_mode, fog_light, speed | ALLOW, BLOCK_UNAVAILABLE |
| `turnon_interiorlight` | Bật đèn nội thất trong xe | speed | ALLOW, CONFIRM |

### Nhóm Chế độ lái / an toàn

| Nhãn | Người dùng muốn gì | State đáng nêu | Outcome có thể |
|---|---|---|---|
| `switch_drivemode_sport` | Chuyển sang chế độ lái Thể thao (Sport) | battery_pct | ALLOW, CONFIRM |
| `switch_drivemode_eco` | Chuyển sang chế độ Tiết kiệm (Eco) | (không) | ALLOW |
| `switch_drivemode_normal` | Chuyển sang chế độ Thường (Normal) | (không) | ALLOW |
| `activate_creepmode` | Bật chế độ bò/trườn (Creep) — xe tự lăn nhẹ | avh | ALLOW, BLOCK_UNAVAILABLE |
| `turnoff_LKA` | Tắt Hỗ trợ giữ làn (Lane Keeping Assist) | (không) | CONFIRM |
| `activate_aac` | Bật Ga tự động thích ứng (Adaptive Cruise Control) | acc_state, speed | ALLOW, BLOCK_UNAVAILABLE |
| `activate_hda` | Bật Hỗ trợ lái trên cao tốc (Highway Driving Assist) | acc_state, speed, gear | ALLOW, BLOCK_UNAVAILABLE, BLOCK_UNSAFE |
| `activate_tcs` | Bật Kiểm soát lực kéo (Traction Control) | esc | ALLOW, BLOCK_UNAVAILABLE |
| `deactivate_esc` | Tắt Cân bằng điện tử (ESC) | (không) | NOT_VOICE_ACTIONABLE |
| `activate_avh` | Bật Giữ phanh tự động (Auto Vehicle Hold) | gear | ALLOW, BLOCK_UNAVAILABLE |

### Nhóm Chế độ xe / đỗ xe

| Nhãn | Người dùng muốn gì | State đáng nêu | Outcome có thể |
|---|---|---|---|
| `activate_campmode` | Bật chế độ cắm trại (giữ điều hòa khi đỗ) | speed, gear, epb, battery_pct, camp/pet/valet_mode_active | ALLOW, BLOCK_UNAVAILABLE |
| `activate_petmode` | Bật chế độ thú cưng (giữ mát cho thú khi đỗ) | gear, battery_pct, camp/pet/valet_mode_active | ALLOW, BLOCK_UNAVAILABLE |
| `activate_valetmode` | Bật chế độ giao xe (valet) | profile, camp/pet/valet_mode_active | ALLOW, BLOCK_UNAVAILABLE |
| `activate_autopark` | Kích hoạt tự động đỗ xe | speed, autopark_state | ALLOW, BLOCK_UNAVAILABLE, BLOCK_UNSAFE |
| `activate_epb` | Kéo phanh tay điện tử (Electric Parking Brake) | gear | ALLOW, BLOCK_UNAVAILABLE |
| `shift_gear_park` | Chuyển cần số về P (Park) | speed | ALLOW, BLOCK_UNAVAILABLE |
| `SHIFT_GEAR_REVERSE` | Chuyển cần số về R (lùi) | gear, speed | ALLOW, BLOCK_UNSAFE |

### Nhóm Ghế / vô lăng / gương / cửa sổ

| Nhãn | Người dùng muốn gì | State đáng nêu | Outcome có thể |
|---|---|---|---|
| `ad_steeringwheel` | Chỉnh vô lăng (lên/xuống/ra/vào) | speed | ALLOW, BLOCK_UNSAFE |
| `fold_backseat` | Gập hàng ghế sau | gear, speed | ALLOW, CONFIRM |
| `open_sunroof` | Mở cửa sổ trời | speed, rain_sensor | BLOCK_UNSAFE, CONFIRM |
| `ad_driverseat_angle` | Chỉnh **góc ngả** lưng ghế lái | speed, target_angle | ALLOW, BLOCK_UNSAFE |
| `ad_driverseat_pos` | Chỉnh **vị trí** ghế lái (tiến/lùi/cao/thấp) | speed | ALLOW, BLOCK_UNSAFE |
| `open_window` | Hạ/mở cửa kính | speed, rain_sensor | BLOCK_UNSAFE, CONFIRM |
| `restore_driverseat_pos` | Khôi phục ghế lái về vị trí đã lưu | speed, target_angle | ALLOW, BLOCK_UNSAFE, CONFIRM |
| `fold_mirrors` | Gập gương chiếu hậu | speed | ALLOW, BLOCK_UNAVAILABLE |

### Nhóm Tín hiệu / UI

| Nhãn | Người dùng muốn gì | State đáng nêu | Outcome có thể |
|---|---|---|---|
| `deactivate_hud` | Tắt màn hình hiển thị trên kính (HUD) | (không) | CONFIRM |
| `turnon_turnsignal_right` | Bật xi nhan phải | hazard_light | ALLOW, BLOCK_UNAVAILABLE |
| `turnon_turnsignal_left` | Bật xi nhan trái | hazard_light | ALLOW, BLOCK_UNAVAILABLE |
| `turnoff_turnsignal_right` | Tắt xi nhan phải | (không) | ALLOW |
| `turnoff_turnsignal_left` | Tắt xi nhan trái | (không) | ALLOW |
| `turnon_hazardlight` | Bật đèn khẩn cấp (đèn hazard, đèn ưu tiên) | (không) | ALLOW |
| `turnoff_hazardlight` | Tắt đèn khẩn cấp | (không) | ALLOW |
| `open_noti_center` | Mở trung tâm thông báo trên màn hình xe | profile | ALLOW, BLOCK_UNAVAILABLE |

### Nhóm Hỏi trạng thái / kiến thức

| Nhãn | Người dùng muốn gì | State đáng nêu | Outcome có thể |
|---|---|---|---|
| `get_current_speed` | Hỏi xe đang chạy bao nhiêu km/h | speed | ANSWER |
| `get_battery_pct` | Hỏi còn bao nhiêu % pin | battery_pct | ANSWER, UNKNOWN |
| `get_gear` | Hỏi xe đang ở số mấy (P/R/N/D) | gear | ANSWER, UNKNOWN |
| `get_door_lock_status` | Hỏi cửa đang khóa hay mở | door_lock_state | ANSWER, UNKNOWN |
| `get_avh_status` | Hỏi Auto Vehicle Hold đang bật hay tắt | avh | ANSWER, UNKNOWN |
| `explain_feature` | Hỏi một tính năng của xe là gì / hoạt động thế nào | kb_has_feature | ANSWER, UNKNOWN |

**Toàn bộ danh mục là 53 nhãn trên. Không có nhãn nào khác. Không được tạo nhãn
mới.** Nếu bạn nghĩ ra một câu lệnh không khớp bất kỳ nhãn nào (ví dụ "bật nhạc",
"gọi điện cho vợ", "tìm quán cà phê") — **không đưa vào tập này**; những câu
ngoài danh mục không thuộc phạm vi bài kiểm tra.

---

## 6. Quy tắc viết utterance

### 6.1. Nguyên tắc số 1 — KHÔNG dùng khuôn mẫu

Đây là lý do tập này tồn tại. **Không** sinh câu bằng cách điền chỗ trống vào
một vài khung cố định. Cụ thể, tránh các bẫy sau:

- ❌ Mọi câu của một intent đều bắt đầu bằng cùng một động từ ("Mở … cho tôi",
  "Mở … cho tôi", "Mở … cho tôi").
- ❌ Chỉ đổi danh từ/tân ngữ, giữ nguyên cấu trúc câu.
- ❌ Cùng một câu đệm gắn vào nhiều câu ("… nhé", "… giùm cái" lặp đi lặp lại).
- ❌ Độ dài câu na ná nhau trong cùng một intent.

Mỗi câu phải là một cách diễn đạt **thực sự khác** — khác động từ, khác cấu
trúc, khác điểm nhấn, khác mức trực tiếp. Đọc 8 câu của cùng một intent cạnh
nhau, chúng phải nghe như 8 người khác nhau nói trong 8 hoàn cảnh khác nhau.

### 6.2. Đa dạng văn phong (`register`)

Trải đều 4 loại, mỗi loại **≥ 15%** tổng số dòng:

- `lich_su` — "Anh ơi cho em xin mở giúp cái cửa cốp ạ."
- `trung_tinh` — "Mở cốp sau."
- `suong_sa` — "mở cái cốp coi", "cốp, lẹ".
- `lan_man` — "à mà khoan, tôi để cái ô trong cốp rồi, thôi mở cốp sau ra cho tôi lấy cái đã rồi tính tiếp."

### 6.3. Đa dạng giọng vùng miền (`dialect`)

Không được để một vùng chiếm ưu thế. Ràng buộc: **mỗi vùng (`bac`/`trung`/`nam`)
≥ 20%**, `trung_tinh` phần còn lại; **không vùng nào > 40%**.

Dấu hiệu vùng miền (dùng tự nhiên, không nhồi nhét):

- **Bắc:** "nhé", "đấy", "cơ", "thế", "bảo", cách xưng "cậu/tớ", "ơ hay".
- **Trung:** "răng", "rứa", "mô", "tê", "ni", "nớ", "chi", "hè", "chừ", xưng "tui".
- **Nam:** "hả", "nghen", "hen", "dữ", "quá trời", "lẹ", "coi", "à nghen", "trời đất".
- **Trung tính:** không dùng dấu hiệu vùng nào rõ rệt.

### 6.4. Đa dạng độ dài (`length_bucket`)

Mỗi loại **≥ 20%**: `ngan` (≤6 từ), `vua` (7–15), `dai` (>15, thường có câu
nhiễu / lý do / ngữ cảnh).

### 6.5. Cách diễn đạt tự nhiên cần có mặt trong tập

- **Gián tiếp / nêu nhu cầu thay vì ra lệnh:** "trời nóng quá à" → (mở cửa sổ);
  "chói mắt ghê" → (tắt đèn pha / chỉnh gì đó). *Chỉ dùng khi vẫn suy ra được
  đúng 1 intent; nếu mơ hồ thì bỏ.*
- **Từ đệm, ngập ngừng:** "ờ thì", "kiểu như", "à", "ừm", "cái mà".
- **Lỗi gõ / viết tắt nhẹ như người thật gõ nhanh:** "k" (không), "dc"/"đc"
  (được), "ko", thiếu dấu rải rác, "giùm/dùm", "luôn/lun". Đừng lạm dụng — tối
  đa ~15% số câu có lỗi gõ, và câu vẫn phải đọc hiểu được.
- **Câu nhiễu / lý do kèm theo:** "mở cốp sau, tôi để quên cái túi trong đó".
- **Xưng hô đa dạng với trợ lý:** "xe ơi", "ViVi ơi", "em ơi", không xưng hô gì.

### 6.6. Về `state_hint`

Với intent có cột "State đáng nêu" ≠ (không), viết một phần câu ám chỉ ngữ cảnh
để phủ các nhánh outcome khác nhau, và ghi `state_hint` bằng lời.

Ví dụ cho `open_door` (phụ thuộc gear + speed):
- Câu ám chỉ **xe đã đỗ**: "xe dừng hẳn rồi, mở cửa cho tôi" → `state_hint`:
  `"xe đỗ, số P, đứng yên"` → (chủ dự án sẽ suy ra ALLOW).
- Câu ám chỉ **xe đang chạy**: "đang chạy trên đường mà mở cửa được không" →
  `state_hint`: `"xe đang chạy ~50 km/h"` → (sẽ suy ra BLOCK_UNSAFE).

Cần phủ **mọi outcome ở cột "Outcome có thể"** cho từng intent, qua việc đổi
`state_hint`. Phân bổ: cố gắng mỗi nhánh outcome của một intent có ít nhất 2
câu.

Nếu câu **không** ám chỉ ngữ cảnh nào (ví dụ "mở cửa cho tôi" trần trụi), để
`state_hint = null`. Không bịa ngữ cảnh không có trong câu.

Xem **Phụ lục A** (giá trị trạng thái hợp lệ) và **Phụ lục B** (109 rule, để
biết ngưỡng nào tạo ra nhánh nào — ví dụ `unlock_doors` chặn khi tốc độ ≥ 10
km/h, `fold_mirrors` chặn khi ≥ 16 km/h). Viết `state_hint` đủ cụ thể để không
mơ hồ về nhánh (nêu con số khi ngưỡng quan trọng).

### 6.7. Đúng-nhãn là tối thượng

Nếu bạn không chắc 100% một câu thuộc intent nào, **đừng đưa vào**. Một câu gán
sai nhãn trong tập kiểm thử độc lập tệ hơn là thiếu một câu.

---

## 7. Hard negatives

**Hard negative** = câu mà bề mặt từ vựng khiến nó *dễ bị phân loại nhầm* sang
một intent khác, nhưng nghĩa đúng vẫn là `intent` đã gán.

Ví dụ:
- `intent: open_door`, `sounds_like: open_trunk` — "mở giùm cái cửa xe, không
  phải cốp nha" (nhắc "cốp" nhưng ý là cửa).
- `intent: get_door_lock_status`, `sounds_like: lock_doors` — "cửa khóa chưa
  vậy?" (hỏi trạng thái, không phải ra lệnh khóa).
- `intent: turnon_lowbeam`, `sounds_like: turnon_highbeam` — "bật đèn cốt thôi
  nhé, đừng bật pha".

**Cặp dễ nhầm nên nhắm tới** (không bắt buộc hết, nhưng phủ càng nhiều càng tốt):

- `open_door` ↔ `open_trunk` ↔ `open_chargeport` ↔ `OPEN_BONNET` (đều "mở …")
- `lock_doors` ↔ `unlock_doors` ↔ `get_door_lock_status`
- `turnon_highbeam` ↔ `turnoff_highbeam` ↔ `turnon_lowbeam` ↔ `turnoff_lowbeam`
- `turnon_turnsignal_left` ↔ `turnon_turnsignal_right` ↔ `turnoff_turnsignal_left` ↔ `turnoff_turnsignal_right` ↔ `turnon_hazardlight`
- `turnon_hazardlight` ↔ `turnoff_hazardlight`
- `activate_campmode` ↔ `activate_petmode` ↔ `activate_valetmode`
- `activate_aac` ↔ `activate_hda` ↔ `activate_creepmode`
- `switch_drivemode_sport` ↔ `switch_drivemode_eco` ↔ `switch_drivemode_normal`
- `ad_driverseat_angle` ↔ `ad_driverseat_pos` ↔ `restore_driverseat_pos`
- `activate_epb` ↔ `shift_gear_park` ↔ `activate_avh`
- `get_current_speed` ↔ `get_battery_pct` ↔ `get_gear` ↔ `get_avh_status` ↔ `get_door_lock_status` (đều "hỏi …")
- `deactivate_esc` ↔ `activate_tcs`
- `open_window` ↔ `open_sunroof`

Với hard negative, đặt `is_hard_negative=true` và `sounds_like=<nhãn dễ nhầm>`.

---

## 8. Số lượng và phân bổ

| Hạng mục | Chỉ tiêu |
|---|---|
| Positive (không phải hard negative) mỗi intent | **8** (tối thiểu 6) |
| Hard negative mỗi intent | **2** (tối thiểu 1) |
| **Tổng cộng** | **~530 dòng** (53 × 10) |

Trong đó, trên toàn tập:
- mỗi `register` ≥ 15%;
- mỗi vùng `bac`/`trung`/`nam` ≥ 20%, không vùng nào > 40%;
- mỗi `length_bucket` ≥ 20%;
- với mỗi intent có nhiều outcome: mỗi nhánh outcome ≥ 2 câu (qua `state_hint`);
- ≤ 15% số câu chứa lỗi gõ/viết tắt;
- **0 câu trùng hoặc gần trùng** (khác nhau chỉ 1–2 từ) — kể cả giữa các intent.

`id` đánh số liên tục `FROZEN-0001` … `FROZEN-0530` (hoặc tới số thực tế).

---

## 9. `generation_notes.md` — nộp kèm

Một file Markdown ngắn gồm:

1. **Phương pháp:** bạn tạo câu như thế nào (không dùng khuôn mẫu ra sao), nguồn
   cảm hứng từ vựng, cách đảm bảo đa dạng.
2. **Bảng tự kiểm phân bổ:** số đếm thực tế theo `register`, `dialect`,
   `length_bucket`, số hard negative, số câu có lỗi gõ. So với chỉ tiêu §8.
3. **Những intent bạn thấy khó viết** và vì sao (ví dụ `explain_feature` cần
   nêu tên một tính năng cụ thể — bạn chọn tính năng nào).
4. **Giả định đã đặt:** bất kỳ chỗ nào tài liệu chưa nói rõ mà bạn phải tự
   quyết (ghi lại để chủ dự án rà).
5. **Danh sách cặp intent bạn KHÔNG chắc ranh giới** — để người review kiểm tay.

---

## 10. Checklist bắt buộc trước khi nộp

- [ ] Mọi `intent` đều nằm trong đúng 53 nhãn §5, chép chính xác hoa/thường.
- [ ] Không có nhãn tự chế; không có câu "ngoài danh mục".
- [ ] Mỗi intent có ≥ 6 positive + ≥ 1 hard negative.
- [ ] `sounds_like` luôn khác `intent`, và chỉ có mặt khi `is_hard_negative=true`.
- [ ] Không hai câu nào trùng/gần trùng (quét toàn tập, cả cross-intent).
- [ ] Không câu nào theo cùng một khuôn với > 3 câu khác.
- [ ] `dialect` / `register` / `length_bucket` đạt ngưỡng phân bổ §8.
- [ ] Với intent đa outcome: mỗi nhánh outcome có ≥ 2 câu kèm `state_hint` rõ.
- [ ] `state_hint` chỉ mô tả ngữ cảnh **câu thực sự ám chỉ**; không bịa.
- [ ] JSON hợp lệ từng dòng; UTF-8 không BOM; `id` liên tục, duy nhất.
- [ ] Đã tự đọc lại 100% số câu, mỗi câu: (a) người thật nói được, (b) nhãn
      chắc chắn đúng, (c) không lộ khuôn mẫu.
- [ ] `generation_notes.md` đầy đủ 5 mục §9.

---

## Phụ lục A — Trạng thái xe: biến, miền giá trị, mặc định

Guardrail đánh giá ràng buộc dựa trên các biến sau. Khi viết `state_hint`, chỉ
cần mô tả bằng lời; bảng này để bạn biết giá trị nào có nghĩa và ngưỡng nào
quan trọng.

**19 biến trạng thái xe:**

| Biến | Kiểu / miền giá trị | Mặc định (khi không nêu) | Ghi chú |
|---|---|---|---|
| `gear` | `"P"`, `"D"`, `"R"`, `"N"` | `"P"` | Vị trí cần số |
| `speed` | số km/h, 0 trở lên | `0` | **Quy ước: "speed < 3" hiểu là "đứng yên hoàn toàn" (== 0).** 1–2 km/h vẫn coi như đang di chuyển với các thao tác cửa/ghế. |
| `rain_sensor` | `true` / `false` / không rõ | `false` | Có mưa hay không |
| `ambient_light` | `"day"` / `"night"` (chữ thường) | `"day"` | Sáng ngoài trời |
| `battery_pct` | số 0–100 / không rõ | `100` | % pin. Ngưỡng hay gặp: 15, 25 |
| `avh` | `true` / `false` / không rõ | `true` | Auto Vehicle Hold |
| `epb` | `true` / `false` | `true` | Phanh tay điện tử |
| `camp_mode_active` | `true` / `false` | `false` | Đang bật chế độ cắm trại |
| `pet_mode_active` | `true` / `false` | `false` | Đang bật chế độ thú cưng |
| `valet_mode_active` | `true` / `false` | `false` | Đang bật chế độ giao xe |
| `profile` | `"OWNER"` / `"GUEST"` / `"VALET"` | `"OWNER"` | Hồ sơ người lái hiện tại |
| `autopark_state` | `"ACTIVE"` / `"INACTIVE"` | `"INACTIVE"` | Tự đỗ xe đang chạy? |
| `acc_state` | `"ACTIVE"` / `"INACTIVE"` | `"INACTIVE"` | Ga tự động đang bật? |
| `hand_off_wheel_duration_seconds` | số giây | `0` | Thời gian rời tay khỏi vô lăng (dùng cho monitor HDA) |
| `fog_light` | `true` / `false` | `false` | Đèn sương mù đang bật |
| `hazard_light` | `true` / `false` | `false` | Đèn khẩn cấp đang bật |
| `lowbeam_mode` | `"On"` / `"Off"` | `"Off"` | Đèn cốt đang bật |
| `esc` | `true` / `false` | `true` | Cân bằng điện tử đang bật |
| `door_lock_state` | `"locked"` / `"unlocked"` / không rõ | `"locked"` | Trạng thái khóa cửa |

**2 tham số theo yêu cầu (không phải trạng thái xe):**

| Tham số | Miền giá trị | Ghi chú |
|---|---|---|
| `target_angle` | số độ (vd 90, 100, 110, 130) | Góc ngả ghế người dùng muốn đặt tới. Ngưỡng: 110. Chỉ liên quan `ad_driverseat_angle`, `restore_driverseat_pos`. |
| `kb_has_feature` | `true` / `false` | Tính năng người dùng hỏi có trong cơ sở tri thức hay không. Chỉ liên quan `explain_feature`. Nếu bạn viết câu hỏi về một tính năng **có thật của xe điện VinFast** (điều hòa, sạc nhanh, phanh tái tạo…) → coi như `true` (ANSWER). Nếu hỏi tính năng **không tồn tại / vô nghĩa** → `false` (UNKNOWN). Ghi rõ ý định của bạn trong `state_hint`. |

---

## Phụ lục B — 109 rule (tham chiếu để chọn `state_hint`)

Định dạng: `rule_id | intent | phase | outcome | điều kiện`. Điều kiện dùng cú
pháp workbook: `AND/OR/NOT`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `is None`.
Nhớ quy ước `speed < 3` ≡ `speed == 0`.

`phase = gate`: đánh giá trước khi thực hiện. `phase = monitor`: đánh giá lại
trong lúc một hành động kéo dài đang chạy (bạn hầu như không cần quan tâm
monitor khi viết câu lệnh đơn).

```
R001 | open_door | gate | ALLOW | ( gear == 'P' ) AND ( speed < 3 )
R002 | open_door | gate | BLOCK_UNSAFE | NOT ( ( gear == 'P' ) AND ( speed < 3 ) )
R003 | open_trunk | gate | ALLOW | ( speed < 3 )
R004 | open_trunk | gate | BLOCK_UNSAFE | NOT ( ( speed < 3 ) )
R005 | open_chargeport | gate | ALLOW | ( speed < 3 ) AND rain_sensor == False
R006 | open_chargeport | gate | CONFIRM | ( speed < 3 ) AND rain_sensor == True
R007 | open_chargeport | gate | ALLOW | ( speed < 3 ) AND rain_sensor is None
R008 | open_chargeport | gate | BLOCK_UNSAFE | NOT ( ( speed < 3 ) )
R009 | turnoff_highbeam | gate | CONFIRM | ambient_light == 'night'
R010 | turnoff_highbeam | gate | ALLOW | ambient_light == 'day'
R011 | turnon_highbeam | gate | CONFIRM | ambient_light == 'day'
R012 | turnon_highbeam | gate | ALLOW | ambient_light == 'night'
R013 | turnoff_lowbeam | gate | CONFIRM | ambient_light == 'night'
R014 | turnoff_lowbeam | gate | ALLOW | ambient_light == 'day'
R015 | turnon_lowbeam | gate | CONFIRM | ambient_light == 'day'
R016 | turnon_lowbeam | gate | ALLOW | ambient_light == 'night'
R017 | lock_doors | gate | ALLOW | TRUE
R018 | unlock_doors | gate | ALLOW | speed < 10
R019 | unlock_doors | gate | BLOCK_UNSAFE | NOT ( speed < 10 )
R020 | OPEN_BONNET | gate | ALLOW | ( gear == 'P' ) AND ( speed < 3 )
R021 | OPEN_BONNET | gate | BLOCK_UNSAFE | NOT ( ( gear == 'P' ) AND ( speed < 3 ) )
R022 | AD_WIPER_MAX | gate | ALLOW | rain_sensor == True
R023 | AD_WIPER_MAX | gate | CONFIRM | rain_sensor == False
R024 | switch_drivemode_sport | gate | ALLOW | battery_pct >= 25
R025 | switch_drivemode_sport | gate | CONFIRM | battery_pct < 25
R026 | switch_drivemode_eco | gate | ALLOW | TRUE
R027 | switch_drivemode_normal | gate | ALLOW | TRUE
R028 | activate_creepmode | gate | ALLOW | avh == False
R029 | activate_creepmode | gate | BLOCK_UNAVAILABLE | NOT ( avh == False )
R030 | turnoff_LKA | gate | CONFIRM | TRUE
R031 | activate_campmode | gate | ALLOW | ( ( speed < 3 ) AND gear == 'P' AND epb == True ) AND ( battery_pct > 25 )
R032 | activate_campmode | gate | BLOCK_UNAVAILABLE | NOT ( ( ( speed < 3 ) AND gear == 'P' AND epb == True ) AND ( battery_pct > 25 ) )
R033 | activate_campmode | monitor | BLOCK_UNAVAILABLE | battery_pct < 15
R034 | activate_campmode | gate | BLOCK_UNAVAILABLE | ( camp_mode_active == True OR pet_mode_active == True OR valet_mode_active == True )
R035 | activate_petmode | gate | ALLOW | ( gear == 'P' ) AND ( battery_pct > 25 )
R036 | activate_petmode | gate | BLOCK_UNAVAILABLE | NOT ( ( gear == 'P' ) AND ( battery_pct > 25 ) )
R037 | activate_petmode | monitor | BLOCK_UNAVAILABLE | battery_pct < 25
R038 | activate_petmode | gate | BLOCK_UNAVAILABLE | ( camp_mode_active == True OR pet_mode_active == True OR valet_mode_active == True )
R039 | activate_valetmode | gate | ALLOW | profile != 'GUEST'
R040 | activate_valetmode | gate | BLOCK_UNAVAILABLE | NOT ( profile != 'GUEST' )
R041 | activate_valetmode | gate | BLOCK_UNAVAILABLE | ( camp_mode_active == True OR pet_mode_active == True OR valet_mode_active == True )
R042 | SHIFT_GEAR_REVERSE | gate | ALLOW | ( speed == 0 ) AND gear != 'D'
R043 | SHIFT_GEAR_REVERSE | gate | BLOCK_UNSAFE | NOT ( ( speed < 3 ) AND gear != 'D' )
R044 | ad_steeringwheel | gate | ALLOW | ( speed == 0 )
R045 | ad_steeringwheel | gate | BLOCK_UNSAFE | NOT ( ( speed < 3 ) )
R046 | activate_autopark | gate | ALLOW | speed < 15
R047 | activate_autopark | gate | BLOCK_UNAVAILABLE | NOT ( speed < 15 )
R048 | activate_autopark | monitor | BLOCK_UNSAFE | autopark_state == 'ACTIVE' AND NOT ( speed < 15 )
R049 | fold_backseat | gate | ALLOW | ( gear == 'P' ) AND ( speed < 3 )
R050 | fold_backseat | gate | CONFIRM | NOT ( ( gear == 'P' ) AND ( speed < 3 ) )
R051 | open_sunroof | gate | BLOCK_UNSAFE | speed > 80
R052 | open_sunroof | gate | CONFIRM | rain_sensor == True AND speed <= 80
R053 | open_sunroof | gate | CONFIRM | speed <= 80 AND NOT ( rain_sensor == True )
R054 | ad_driverseat_angle | gate | ALLOW | ( speed < 3 )
R055 | ad_driverseat_angle | gate | ALLOW | NOT ( ( speed < 3 ) ) AND target_angle <= 110
R056 | ad_driverseat_angle | gate | BLOCK_UNSAFE | NOT ( ( speed < 3 ) ) AND target_angle > 110
R057 | ad_driverseat_pos | gate | ALLOW | ( speed < 3 )
R058 | ad_driverseat_pos | gate | BLOCK_UNSAFE | NOT ( ( speed < 3 ) )
R059 | open_window | gate | CONFIRM | speed <= 80 AND NOT ( rain_sensor == True )
R060 | open_window | gate | BLOCK_UNSAFE | speed > 80
R061 | open_window | gate | CONFIRM | rain_sensor == True AND speed <= 80
R062 | restore_driverseat_pos | gate | ALLOW | ( speed < 3 )
R063 | restore_driverseat_pos | gate | CONFIRM | NOT ( ( speed < 3 ) ) AND target_angle < 110
R064 | restore_driverseat_pos | gate | BLOCK_UNSAFE | NOT ( ( speed < 3 ) ) AND target_angle >= 110
R065 | activate_epb | gate | ALLOW | ( gear == 'P' )
R066 | activate_epb | gate | BLOCK_UNAVAILABLE | NOT ( ( gear == 'P' ) )
R067 | deactivate_hud | gate | CONFIRM | TRUE
R068 | activate_aac | gate | ALLOW | ( 20 < speed < 150 )
R069 | activate_aac | gate | BLOCK_UNAVAILABLE | NOT ( ( 20 < speed < 150 ) )
R070 | activate_aac | monitor | ALLOW | ( acc_state == 'ACTIVE' ) AND speed == 0
R071 | activate_hda | gate | ALLOW | ( acc_state == 'ACTIVE' ) AND ( 0 < speed < 150 ) AND gear != 'R'
R072 | activate_hda | gate | BLOCK_UNAVAILABLE | NOT ( ( acc_state == 'ACTIVE' ) AND ( 0 < speed < 150 ) AND gear != 'R' )
R073 | activate_hda | monitor | BLOCK_UNSAFE | hand_off_wheel_duration_seconds > 15
R074 | shift_gear_park | gate | ALLOW | ( speed < 3 )
R075 | shift_gear_park | gate | BLOCK_UNAVAILABLE | NOT ( ( speed < 3 ) )
R076 | fold_mirrors | gate | ALLOW | speed < 16
R077 | fold_mirrors | gate | BLOCK_UNAVAILABLE | NOT ( speed < 16 )
R078 | activate_ahb | gate | ALLOW | fog_light == False
R079 | activate_ahb | gate | BLOCK_UNAVAILABLE | NOT ( fog_light == False )
R080 | turnon_turnsignal_right | gate | ALLOW | hazard_light == False
R081 | turnon_turnsignal_right | gate | BLOCK_UNAVAILABLE | NOT ( hazard_light == False )
R082 | turnon_turnsignal_left | gate | ALLOW | hazard_light == False
R083 | turnon_turnsignal_left | gate | BLOCK_UNAVAILABLE | NOT ( hazard_light == False )
R084 | turnoff_turnsignal_right | gate | ALLOW | TRUE
R085 | turnoff_turnsignal_left | gate | ALLOW | TRUE
R086 | turnon_hazardlight | gate | ALLOW | TRUE
R087 | turnoff_hazardlight | gate | ALLOW | TRUE
R088 | turnon_corneringlight | gate | ALLOW | lowbeam_mode == 'On' AND fog_light == False AND speed <= 40
R089 | turnon_corneringlight | gate | BLOCK_UNAVAILABLE | NOT ( lowbeam_mode == 'On' AND fog_light == False AND speed <= 40 )
R090 | turnon_interiorlight | gate | ALLOW | ( speed < 3 )
R091 | turnon_interiorlight | gate | CONFIRM | NOT ( ( speed < 3 ) )
R092 | activate_tcs | gate | ALLOW | esc == True
R093 | activate_tcs | gate | BLOCK_UNAVAILABLE | NOT ( esc == True )
R094 | deactivate_esc | gate | NOT_VOICE_ACTIONABLE | TRUE
R095 | activate_avh | gate | ALLOW | gear != 'P'
R096 | activate_avh | gate | BLOCK_UNAVAILABLE | NOT ( gear != 'P' )
R097 | open_noti_center | gate | ALLOW | profile != 'GUEST' AND profile != 'VALET'
R098 | open_noti_center | gate | BLOCK_UNAVAILABLE | NOT ( profile != 'GUEST' AND profile != 'VALET' )
R099 | get_current_speed | gate | ANSWER | speed is not None
R100 | get_battery_pct | gate | ANSWER | battery_pct is not None
R101 | get_battery_pct | gate | UNKNOWN | NOT ( battery_pct is not None )
R102 | get_gear | gate | ANSWER | gear is not None
R103 | get_gear | gate | UNKNOWN | NOT ( gear is not None )
R104 | get_door_lock_status | gate | ANSWER | door_lock_state is not None
R105 | get_door_lock_status | gate | UNKNOWN | NOT ( door_lock_state is not None )
R106 | get_avh_status | gate | ANSWER | avh is not None
R107 | get_avh_status | gate | UNKNOWN | NOT ( avh is not None )
R108 | explain_feature | gate | ANSWER | kb_has_feature == True
R109 | explain_feature | gate | UNKNOWN | kb_has_feature == False
```

Cách đọc để chọn `state_hint` (ví dụ):
- `unlock_doors`: ALLOW nếu `speed < 10`, BLOCK_UNSAFE nếu `speed ≥ 10`. →
  viết 1 câu ngữ cảnh "xe bò chậm ~5 km/h", 1 câu "đang chạy 40 km/h".
- `switch_drivemode_sport`: ALLOW nếu pin ≥ 25%, CONFIRM nếu pin < 25%. →
  1 câu không nhắc pin (mặc định 100 → ALLOW), 1 câu "pin còn có 18% thôi".
- `activate_valetmode`: ALLOW nếu `profile != GUEST` **và** chưa bật chế độ
  camp/pet/valet nào; BLOCK_UNAVAILABLE nếu profile là GUEST, **hoặc** đang bật
  một chế độ. → phủ cả 2.
- `explain_feature`: ANSWER nếu hỏi tính năng có thật; UNKNOWN nếu hỏi tính
  năng bịa. → viết cả 2 kiểu, ghi rõ trong `state_hint`.

---

## Phụ lục C — 7 outcome (để hiểu ngữ cảnh, không phải việc bạn gán)

| Outcome | Nghĩa |
|---|---|
| `ALLOW` | Được phép thực hiện ngay. |
| `BLOCK_UNSAFE` | Bị chặn vì không an toàn ở trạng thái hiện tại. |
| `BLOCK_UNAVAILABLE` | Bị chặn vì tính năng không khả dụng ở trạng thái hiện tại. |
| `CONFIRM` | Cần người dùng xác nhận lại trước khi thực hiện. |
| `NOT_VOICE_ACTIONABLE` | Không cho phép làm qua lệnh giọng nói (chỉ `deactivate_esc`). |
| `ANSWER` | Trả lời câu hỏi bằng dữ liệu trạng thái xe. |
| `UNKNOWN` | Không có dữ liệu để trả lời. |

---

## Phụ lục D — Ví dụ tốt vs xấu

**TỐT** (8 câu cho `open_trunk`, đa dạng thật):

```
"Cốp sau mở giùm cái."                                          (nam, ngắn, suồng sã)
"Anh ơi bấm mở cốp xe hộ em với ạ, em bê đồ ra."                (bắc, vừa, lịch sự)
"răng cái cốp khoá hoài rứa, mở ra cho tui."                    (trung, ngắn, suồng sã)
"Đang chạy ngoài đường mà mở cốp có được không nhỉ?"            (trung tính, vừa) [state_hint: đang chạy]
"mở khoang sau ra, tui để quên cái áo mưa trong đó rồi."        (nam, vừa)
"Cho mình xin mở cái cửa cốp phía sau nhé, cảm ơn."             (bắc, vừa, lịch sự)
"ừm... mở cốp. à mà thôi khoan, ừ mở đi."                        (trung tính, ngắn, lan man)
"Tới nơi rồi, bung cốp giúp tôi để tôi lấy vali xuống."          (trung tính, dài) [state_hint: xe vừa dừng]
```

**XẤU** (lộ khuôn mẫu — KHÔNG làm thế này):

```
"Mở cốp sau cho tôi."
"Mở cốp trước cho tôi."      ← "trước" không đúng nghĩa, và cùng khuôn
"Mở cốp xe cho tôi."
"Mở cốp giúp tôi."           ← chỉ đổi 1 từ
"Mở cốp sau giúp tôi nhé."   ← thêm 1 từ đệm
```

---

*Hết. Nếu có mâu thuẫn giữa các mục, ưu tiên: §5 (danh mục) > §6.1 (không khuôn
mẫu) > §6.7 (đúng nhãn) > phần còn lại.*
