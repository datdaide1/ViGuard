# Regen 106 hard-negative — Frozen Test Set (vòng 2)

> Kèm theo: `FROZEN_TESTSET_SPEC.md` (tra danh mục 53 intent ở §5, schema ở §3,
> quy tắc viết tiếng Việt ở §6). Bản này **thay thế §7 + §8 của SPEC cho riêng
> phần hard-negative**. Bạn KHÔNG đọc gì khác trong dự án.

---

## 1. Vì sao regen

Vòng 1: 104/106 hard-negative dùng đúng **một khuôn**: *"[việc muốn làm] **chớ /
chứ / k phải** [việc dễ nhầm] **đâu / mô / nghen**"* — tự tuyên bố phủ định
intent dễ nhầm.

Câu nói thật hiếm khi "khai" rằng nó KHÔNG phải việc Y. Khuôn này chỉ test
"xử lý câu có disclaimer", không test "phân giải mơ hồ thật sự", và bị đóng
khuôn — vi phạm nguyên tắc chống-khuôn-mẫu.

## 2. Nhiệm vụ

Viết lại **`utterance`** cho **106 dòng** ở bảng §6. Với mỗi dòng:

- **GIỮ NGUYÊN:** `id`, `intent`, `sounds_like`, `is_hard_negative` (= `true`).
- **VIẾT LẠI:** `utterance` + đặt lại `dialect`, `register`, `length_bucket`,
  `state_hint` (nếu cần), `notes`.
- Nhãn đúng vẫn là cột `intent`. Câu vẫn phải khiến **một người Việt đọc là
  hiểu ngay đó là `intent`**, dù bề mặt từ vựng dễ khiến máy nhầm sang
  `sounds_like`.

Cộng thêm **1 dòng** ở §7 (thay một positive bị near-duplicate).

Nộp: `frozen_hardneg_v2.jsonl` (107 dòng) + `regen_notes.md` ngắn (§8).

## 3. Ràng buộc phân bổ (BẮT BUỘC — regen_notes phải có bảng tự kiểm)

Trên 106 hard-negative mới:

| Tiêu chí | Ngưỡng |
|---|---|
| Dùng cấu trúc phủ định tường minh ("… chớ/chứ/không phải … đâu/mô") | **≤ 42 câu (40%)** |
| Dạng (i) câu-hỏi-trạng-thái | ≥ 20 câu |
| Dạng (ii) va-chạm-gần-nghĩa (không phủ định) | ≥ 22 câu |
| Dạng (iii) ngữ-cảnh-bẫy (không phủ định) | ≥ 22 câu |
| Câu ngắn ≤ 6 từ | **≥ 30 câu** |
| dialect: mỗi vùng bac/trung/nam | ≥ 20 câu, không vùng nào > 45 |
| register: mỗi loại (lich_su / trung_tinh / suong_sa / lan_man) | ≥ 15 câu |
| Lỗi gõ/viết tắt ("k", "ko", "dc") | ≤ 16 câu (≤ 15%) |
| Không hai câu trùng/gần trùng nhau, và không trùng bản vòng 1 | 0 |

## 4. Ba dạng hard-negative KHÔNG phủ định (ưu tiên dùng)

### Dạng (i) — Câu hỏi trạng thái bị nhầm thành câu lệnh
Chỉ hợp với các cặp mà một bên là `get_*` (hỏi) và bên kia là lệnh.
Người dùng **hỏi** trạng thái, không **ra lệnh**.

- `get_door_lock_status` (dễ nhầm `lock_doors`): *"cửa xe khoá hết chưa rứa"* /
  *"kiểm tra giùm coi mấy cái cửa chốt chưa"*
- `get_gear` (dễ nhầm `shift_gear_park` / `SHIFT_GEAR_REVERSE`): *"xe đang để
  số chi rứa hè"* / *"cần số đang ở P hay D vậy"*
- `get_avh_status` (dễ nhầm `activate_avh`): *"AVH đang bật hay tắt đó"*
- `get_current_speed` / `get_battery_pct`: *"chạy nhanh cỡ nào rồi"* / *"pin còn
  nhiêu phần trăm"* — dễ nhầm nhau, KHÔNG được thêm "chớ k phải hỏi …".

### Dạng (ii) — Va chạm gần nghĩa, không phủ định
Câu dùng từ vựng **của cả hai** intent, nhưng ngữ cảnh / chi tiết còn lại chỉ
đúng về `intent`. KHÔNG nhắc tên intent kia để loại trừ.

- `activate_hda` (dễ nhầm `activate_aac`): *"bật trợ lái cao tốc cho xe tự bám
  làn tự giữ ga luôn nha"* — "tự bám làn" ⇒ HDA, không phải chỉ AAC.
- `activate_aac` (dễ nhầm `activate_hda`): *"cho xe tự giữ khoảng cách với xe
  trước, đỡ phải rà ga phanh"* — chỉ nói giữ khoảng cách ⇒ AAC.
- `ad_driverseat_angle` (dễ nhầm `ad_driverseat_pos`): *"ngả lưng ghế lái ra sau
  cho dựa lưng đỡ mỏi"* — "ngả lưng / góc dựa" ⇒ angle.
- `ad_driverseat_pos` (dễ nhầm `ad_driverseat_angle`): *"đẩy nguyên cái ghế lái
  tới trước cho với tới vô lăng"* — "đẩy tới/lui" ⇒ pos.
- `open_sunroof` (dễ nhầm `open_window`): *"mở cái nóc kính trên đầu ra cho
  thoáng"* — "trên nóc / trên đầu" ⇒ sunroof.
- `turnon_hazardlight` (dễ nhầm `turnon_turnsignal_*`): *"bật đèn nhấp nháy cả
  hai bên lên, xe chết máy giữa đường rồi"* — "cả hai bên" + "chết máy" ⇒ hazard.

### Dạng (iii) — Ngữ cảnh bẫy
Tình huống gợi ý intent kia, nhưng yêu cầu thật là `intent`.

- `activate_petmode` (bẫy `open_window`): *"để con chó trong xe chạy vô mua đồ
  cái, bật máy giữ mát giùm"* — giữ mát khi đỗ ⇒ pet mode, không phải hạ kính.
- `activate_campmode` (bẫy `activate_petmode`): *"tối nay ngủ lại trong xe, giữ
  điều hoà chạy suốt đêm giùm"* — người ngủ ⇒ camp mode.
- `open_chargeport` (bẫy `open_trunk`): *"tới trụ sạc rồi, mở chỗ cắm điện ra"*
  — trụ sạc ⇒ chargeport.
- `fold_mirrors` (bẫy `fold_backseat`): *"vô hẻm nhỏ quá, thu gương lại giùm"* —
  hẻm nhỏ ⇒ gương, không phải ghế.
- `shift_gear_park` (bẫy `activate_epb`): *"đậu xong rồi, gạt số về đỗ đi"* —
  "gạt số" ⇒ shift P, không phải kéo phanh tay.

> Một số cặp (vd 2 chế độ đèn pha/cốt bật↔tắt) khó tránh phủ định — với các cặp
> đó vẫn được dùng dạng phủ định, miễn tổng ≤ 42 câu.

## 5. Nhắc lại quy tắc từ SPEC (vẫn áp dụng)

- Đa dạng giọng 3 miền (dấu hiệu: bac "nhé/đấy/thế"; trung "răng/rứa/mô/tê/hè";
  nam "nghen/coi/lẹ/dữ"). Không nhồi nhét.
- Không hai câu cùng khuôn với > 3 câu khác.
- Tên intent chép chính xác hoa/thường: `OPEN_BONNET`, `AD_WIPER_MAX`,
  `SHIFT_GEAR_REVERSE`, `turnoff_LKA` viết hoa như vậy.
- `state_hint`: để `null` trừ khi câu ám chỉ ngữ cảnh trạng thái xe cụ thể
  (đa số hard-negative không cần).

## 6. Bảng 106 hard-negative cần viết lại

Định dạng: `id | intent (nhãn ĐÚNG) | sounds_like (dễ nhầm sang)`

```
FROZEN-0009 | open_door | open_trunk
FROZEN-0010 | open_door | open_sunroof
FROZEN-0019 | open_trunk | open_door
FROZEN-0020 | open_trunk | OPEN_BONNET
FROZEN-0029 | open_chargeport | open_noti_center
FROZEN-0030 | open_chargeport | open_trunk
FROZEN-0039 | lock_doors | unlock_doors
FROZEN-0040 | lock_doors | get_door_lock_status
FROZEN-0049 | unlock_doors | lock_doors
FROZEN-0050 | unlock_doors | open_door
FROZEN-0059 | OPEN_BONNET | open_trunk
FROZEN-0060 | OPEN_BONNET | open_door
FROZEN-0069 | turnon_highbeam | turnon_lowbeam
FROZEN-0070 | turnon_highbeam | turnoff_highbeam
FROZEN-0079 | turnoff_highbeam | turnoff_lowbeam
FROZEN-0080 | turnoff_highbeam | turnon_highbeam
FROZEN-0089 | turnon_lowbeam | turnon_highbeam
FROZEN-0090 | turnon_lowbeam | turnoff_lowbeam
FROZEN-0099 | turnoff_lowbeam | turnoff_highbeam
FROZEN-0100 | turnoff_lowbeam | turnon_lowbeam
FROZEN-0109 | AD_WIPER_MAX | open_window
FROZEN-0110 | AD_WIPER_MAX | OPEN_BONNET
FROZEN-0119 | activate_ahb | turnon_highbeam
FROZEN-0120 | activate_ahb | turnon_corneringlight
FROZEN-0129 | turnon_corneringlight | turnon_turnsignal_right
FROZEN-0130 | turnon_corneringlight | activate_ahb
FROZEN-0139 | turnon_interiorlight | turnon_highbeam
FROZEN-0140 | turnon_interiorlight | open_sunroof
FROZEN-0149 | switch_drivemode_sport | switch_drivemode_eco
FROZEN-0150 | switch_drivemode_sport | switch_drivemode_normal
FROZEN-0159 | switch_drivemode_eco | switch_drivemode_sport
FROZEN-0160 | switch_drivemode_eco | switch_drivemode_normal
FROZEN-0169 | switch_drivemode_normal | switch_drivemode_sport
FROZEN-0170 | switch_drivemode_normal | switch_drivemode_eco
FROZEN-0179 | activate_creepmode | activate_avh
FROZEN-0180 | activate_creepmode | activate_aac
FROZEN-0189 | turnoff_LKA | deactivate_esc
FROZEN-0190 | turnoff_LKA | activate_aac
FROZEN-0199 | activate_aac | activate_hda
FROZEN-0200 | activate_aac | activate_creepmode
FROZEN-0209 | activate_hda | activate_aac
FROZEN-0210 | activate_hda | activate_autopark
FROZEN-0219 | activate_tcs | deactivate_esc
FROZEN-0220 | activate_tcs | activate_avh
FROZEN-0229 | deactivate_esc | activate_tcs
FROZEN-0230 | deactivate_esc | turnoff_LKA
FROZEN-0239 | activate_avh | activate_epb
FROZEN-0240 | activate_avh | get_avh_status
FROZEN-0249 | activate_campmode | activate_petmode
FROZEN-0250 | activate_campmode | activate_valetmode
FROZEN-0259 | activate_petmode | activate_campmode
FROZEN-0260 | activate_petmode | open_door
FROZEN-0269 | activate_valetmode | activate_campmode
FROZEN-0270 | activate_valetmode | open_noti_center
FROZEN-0279 | activate_autopark | SHIFT_GEAR_REVERSE
FROZEN-0280 | activate_autopark | shift_gear_park
FROZEN-0289 | activate_epb | activate_avh
FROZEN-0290 | activate_epb | shift_gear_park
FROZEN-0299 | shift_gear_park | SHIFT_GEAR_REVERSE
FROZEN-0300 | shift_gear_park | get_gear
FROZEN-0309 | SHIFT_GEAR_REVERSE | shift_gear_park
FROZEN-0310 | SHIFT_GEAR_REVERSE | activate_autopark
FROZEN-0319 | ad_steeringwheel | ad_driverseat_angle
FROZEN-0320 | ad_steeringwheel | ad_driverseat_pos
FROZEN-0329 | fold_backseat | open_trunk
FROZEN-0330 | fold_backseat | ad_driverseat_angle
FROZEN-0339 | open_sunroof | open_window
FROZEN-0340 | open_sunroof | turnon_interiorlight
FROZEN-0349 | ad_driverseat_angle | ad_driverseat_pos
FROZEN-0350 | ad_driverseat_angle | restore_driverseat_pos
FROZEN-0359 | ad_driverseat_pos | ad_driverseat_angle
FROZEN-0360 | ad_driverseat_pos | ad_steeringwheel
FROZEN-0369 | open_window | open_door
FROZEN-0370 | open_window | open_sunroof
FROZEN-0379 | restore_driverseat_pos | ad_driverseat_pos
FROZEN-0380 | restore_driverseat_pos | ad_driverseat_angle
FROZEN-0389 | fold_mirrors | fold_backseat
FROZEN-0390 | fold_mirrors | open_window
FROZEN-0399 | deactivate_hud | open_noti_center
FROZEN-0400 | deactivate_hud | turnon_interiorlight
FROZEN-0409 | turnon_turnsignal_right | turnon_turnsignal_left
FROZEN-0410 | turnon_turnsignal_right | turnoff_turnsignal_right
FROZEN-0419 | turnon_turnsignal_left | turnon_turnsignal_right
FROZEN-0420 | turnon_turnsignal_left | turnon_hazardlight
FROZEN-0429 | turnoff_turnsignal_right | turnoff_turnsignal_left
FROZEN-0430 | turnoff_turnsignal_right | turnon_turnsignal_right
FROZEN-0439 | turnoff_turnsignal_left | turnoff_turnsignal_right
FROZEN-0440 | turnoff_turnsignal_left | turnoff_hazardlight
FROZEN-0449 | turnon_hazardlight | turnon_turnsignal_right
FROZEN-0450 | turnon_hazardlight | turnoff_hazardlight
FROZEN-0459 | turnoff_hazardlight | turnon_highbeam
FROZEN-0460 | turnoff_hazardlight | turnon_hazardlight
FROZEN-0469 | open_noti_center | open_door
FROZEN-0470 | open_noti_center | open_chargeport
FROZEN-0479 | get_current_speed | get_battery_pct
FROZEN-0480 | get_current_speed | get_gear
FROZEN-0489 | get_battery_pct | get_current_speed
FROZEN-0490 | get_battery_pct | open_chargeport
FROZEN-0499 | get_gear | shift_gear_park
FROZEN-0500 | get_gear | SHIFT_GEAR_REVERSE
FROZEN-0509 | get_door_lock_status | lock_doors
FROZEN-0510 | get_door_lock_status | unlock_doors
FROZEN-0519 | get_avh_status | activate_avh
FROZEN-0520 | get_avh_status | get_door_lock_status
FROZEN-0529 | explain_feature | turnoff_LKA
FROZEN-0530 | explain_feature | activate_autopark
```

## 7. Một dòng positive cần thay (near-duplicate)

`FROZEN-0294` (intent `shift_gear_park`, **không** phải hard-negative) hiện là
*"Chuyển cần số về P."* — gần trùng `FROZEN-0292` *"chuyển cần số về P coi"*.

Viết 1 câu `shift_gear_park` mới cho `FROZEN-0294`: khác cấu trúc, khác 2 câu
trên, `is_hard_negative=false`, `sounds_like=null`, `state_hint` ám chỉ xe
đứng yên (vd `"xe đã dừng hẳn"`).

## 8. `regen_notes.md`

1. Bảng tự kiểm phân bổ (mọi ngưỡng §3), số thực tế / ngưỡng.
2. Với mỗi dạng (i)(ii)(iii): liệt kê id đã dùng dạng đó.
3. Các cặp bạn buộc phải dùng phủ định tường minh (và vì sao).
4. Cặp nào bạn thấy ranh giới nhãn mong manh → để người review kiểm tay.

## 9. Checklist trước khi nộp

- [ ] Đúng 106 dòng hard-negative + 1 dòng `FROZEN-0294`.
- [ ] `id` / `intent` / `sounds_like` khớp §6 từng dòng, không đổi.
- [ ] ≤ 42 câu dùng phủ định tường minh (đếm lại).
- [ ] ≥ 30 câu ≤ 6 từ.
- [ ] Không câu nào trùng/gần trùng nhau HOẶC trùng bản vòng 1.
- [ ] Mỗi câu: người Việt đọc ra đúng `intent`; máy có thể nhầm sang `sounds_like`.
- [ ] JSON hợp lệ từng dòng, UTF-8 không BOM.
