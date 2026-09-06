# Phase 1' metrics — intent classifier + pipeline vs golden dataset

> `vf_guardrails/evals/run_classifier.py` · 2026-09-06 21:40 · 2313 rows
> classifier tiers active: **T1 only (T2 model not loaded)**

## Headline

| metric | value |
|---|---|
| **intent accuracy** | **1345/2313 = 58.1%** |
| macro-F1 (per intent) | 0.658 |
| INTENT_UNKNOWN rate | 855/2313 = 37.0% |
| **pipeline outcome accuracy** (classified intent → engine) | **1365/2313 = 59.0%** |
| classifier latency p50 / p95 / p99 | 0.01 / 0.01 / 0.02 ms |

## Per-intent recall (worst 20)

| intent | recall | n |
|---|---|---|
| `restore_driverseat_pos` | 0% | 66 |
| `ad_driverseat_pos` | 0% | 43 |
| `get_gear` | 2% | 51 |
| `get_door_lock_status` | 2% | 40 |
| `turnon_turnsignal_right` | 5% | 40 |
| `turnon_turnsignal_left` | 5% | 40 |
| `get_avh_status` | 15% | 40 |
| `turnoff_turnsignal_right` | 15% | 20 |
| `turnoff_turnsignal_left` | 20% | 20 |
| `activate_valetmode` | 27% | 60 |
| `unlock_doors` | 28% | 40 |
| `get_current_speed` | 30% | 27 |
| `activate_epb` | 30% | 46 |
| `activate_aac` | 32% | 60 |
| `explain_feature` | 38% | 40 |
| `activate_autopark` | 38% | 60 |
| `activate_tcs` | 40% | 40 |
| `open_window` | 45% | 64 |
| `turnon_corneringlight` | 47% | 47 |
| `activate_hda` | 47% | 68 |

## Top confusions (true → predicted)

| true | predicted | n |
|---|---|---|
| `restore_driverseat_pos` | `INTENT_UNKNOWN` | 62 |
| `get_gear` | `INTENT_UNKNOWN` | 50 |
| `activate_valetmode` | `INTENT_UNKNOWN` | 43 |
| `ad_driverseat_pos` | `INTENT_UNKNOWN` | 40 |
| `activate_aac` | `INTENT_UNKNOWN` | 40 |
| `get_door_lock_status` | `lock_doors` | 39 |
| `turnon_turnsignal_right` | `INTENT_UNKNOWN` | 38 |
| `turnon_turnsignal_left` | `INTENT_UNKNOWN` | 38 |
| `activate_autopark` | `INTENT_UNKNOWN` | 37 |
| `open_sunroof` | `INTENT_UNKNOWN` | 32 |
| `activate_epb` | `INTENT_UNKNOWN` | 32 |
| `activate_hda` | `INTENT_UNKNOWN` | 31 |
| `unlock_doors` | `lock_doors` | 29 |
| `open_window` | `INTENT_UNKNOWN` | 29 |
| `activate_petmode` | `INTENT_UNKNOWN` | 27 |
| `explain_feature` | `INTENT_UNKNOWN` | 25 |
| `turnon_corneringlight` | `INTENT_UNKNOWN` | 24 |
| `activate_tcs` | `INTENT_UNKNOWN` | 24 |
| `activate_avh` | `INTENT_UNKNOWN` | 24 |
| `activate_creepmode` | `INTENT_UNKNOWN` | 21 |
| `turnon_interiorlight` | `INTENT_UNKNOWN` | 20 |
| `get_current_speed` | `INTENT_UNKNOWN` | 19 |
| `activate_campmode` | `INTENT_UNKNOWN` | 18 |
| `switch_drivemode_sport` | `INTENT_UNKNOWN` | 17 |
| `turnoff_turnsignal_right` | `INTENT_UNKNOWN` | 17 |

## Pipeline mismatch confusion (expected → got)

| expected | got | n |
|---|---|---|
| ALLOW | CLASSIFICATION_ERROR | 304 |
| BLOCK_UNAVAILABLE | CLASSIFICATION_ERROR | 214 |
| BLOCK_UNSAFE | CLASSIFICATION_ERROR | 108 |
| CONFIRM | CLASSIFICATION_ERROR | 103 |
| ANSWER | CLASSIFICATION_ERROR | 78 |
| UNKNOWN | CLASSIFICATION_ERROR | 46 |
| ANSWER | ALLOW | 20 |
| BLOCK_UNSAFE | ALLOW | 19 |
| UNKNOWN | ALLOW | 19 |
| UNKNOWN | BLOCK_UNAVAILABLE | 9 |
| ANSWER | BLOCK_UNAVAILABLE | 8 |
| CONFIRM | BLOCK_UNSAFE | 3 |
| BLOCK_UNSAFE | FAIL:NO_RULE_FOR_PHASE | 3 |
| BLOCK_UNSAFE | BLOCK_UNAVAILABLE | 2 |
| BLOCK_UNSAFE | FAIL:CONDITION_EVAL_ERROR | 2 |
| ALLOW | BLOCK_UNAVAILABLE | 2 |
| NOT_VOICE_ACTIONABLE | CLASSIFICATION_ERROR | 2 |
| CONFIRM | ALLOW | 1 |
| ALLOW | FAIL:CONDITION_EVAL_ERROR | 1 |
| CONFIRM | FAIL:CONDITION_EVAL_ERROR | 1 |
| ALLOW | FAIL:NO_RULE_FOR_PHASE | 1 |
| BLOCK_UNAVAILABLE | CONFIRM | 1 |
| BLOCK_UNAVAILABLE | ALLOW | 1 |

## Intent errors — first 60

| sample_id | true | predicted | utterance |
|---|---|---|---|
| GOLD-R004-002 | `open_trunk` | `open_chargeport` | Trong cốp có bộ sạc dự phòng với dây sạc xe, mở cho tui cái  |
| GOLD-R008-002 | `open_chargeport` | `INTENT_UNKNOWN` | Xe đang chạy mà, mở giùm cái nắp bên hông cho em với. |
| GOLD-R009-002 | `turnoff_highbeam` | `INTENT_UNKNOWN` | Xe đối diện pha đèn chói quá, hạ đèn pha xuống hộ tôi. |
| GOLD-R015-015 | `turnon_lowbeam` | `turnoff_lowbeam` | Đèn cốt đang tắt à, bật lên cho tui. |
| GOLD-R017-001 | `lock_doors` | `INTENT_UNKNOWN` | Khoá xe lại hộ tôi, tí tôi ra liền. |
| GOLD-R017-005 | `lock_doors` | `INTENT_UNKNOWN` | Khoá xe lại cái đi. |
| GOLD-R017-009 | `lock_doors` | `INTENT_UNKNOWN` | Khoá xe lại cho tôi với. |
| GOLD-R017-011 | `lock_doors` | `INTENT_UNKNOWN` | Khoá xe lại được không rứa? |
| GOLD-R017-014 | `lock_doors` | `INTENT_UNKNOWN` | Khoá xe giùm cái, tui vô siêu thị chút xíu. |
| GOLD-R017-020 | `lock_doors` | `INTENT_UNKNOWN` | Khoá xe lại giùm cái đi, tui đi rồi. |
| GOLD-R018-004 | `unlock_doors` | `lock_doors` | Tắt máy rồi tê, khoá cửa mở hộ tui với. |
| GOLD-R018-002 | `unlock_doors` | `lock_doors` | Mở khoá cửa cho tôi, xe đang chạy chậm thôi. |
| GOLD-R018-007 | `unlock_doors` | `lock_doors` | Mở khoá cửa cho tôi cái. |
| GOLD-R018-009 | `unlock_doors` | `lock_doors` | Khoá cửa, mở ra giùm cái. |
| GOLD-R018-010 | `unlock_doors` | `lock_doors` | Cho anh mở khoá cửa cái, sắp tới nơi đón khách rồi. |
| GOLD-R018-011 | `unlock_doors` | `lock_doors` | Mở khoá cửa được không rứa? |
| GOLD-R018-012 | `unlock_doors` | `lock_doors` | Mở khoá cửa dùm, có người nhà đang đợi ngoài đó. |
| GOLD-R018-013 | `unlock_doors` | `lock_doors` | Ê, mở khoá cửa lẹ lên. |
| GOLD-R018-017 | `unlock_doors` | `lock_doors` | Cho tui mở khoá cửa cái coi. |
| GOLD-R018-019 | `unlock_doors` | `lock_doors` | Mở khoá cửa hộ tớ với nhé. |
| GOLD-R018-016 | `unlock_doors` | `lock_doors` | Mở khoá hết cửa xe ra cho tui. |
| GOLD-R019-001 | `unlock_doors` | `lock_doors` | Đứng yên rồi rứa, khoá cửa mở cho tui cái. |
| GOLD-R019-002 | `unlock_doors` | `lock_doors` | Xe dừng hẳn từ nãy tê, khoá cửa mở cho tui cái. |
| GOLD-R019-003 | `unlock_doors` | `lock_doors` | Mở khoá cửa cho tui, đi từ từ thôi mà. |
| GOLD-R019-004 | `unlock_doors` | `lock_doors` | Mở khoá cửa cho tui, tui đi chầm chậm à. |
| GOLD-R019-005 | `unlock_doors` | `lock_doors` | Khoá cửa mở giùm cái. |
| GOLD-R019-007 | `unlock_doors` | `lock_doors` | Cho anh mở khoá cửa cái. |
| GOLD-R019-020 | `unlock_doors` | `lock_doors` | Mở khoá cửa giùm cái, xe đang chạy vầy cũng được mà. |
| GOLD-R019-009 | `unlock_doors` | `lock_doors` | Mở khoá cửa xuống giùm tui. |
| GOLD-R019-008 | `unlock_doors` | `lock_doors` | Mở khoá cửa được không rứa, xe có chạy mô mà. |
| GOLD-R019-014 | `unlock_doors` | `lock_doors` | Mở khoá cửa hộ tớ, tui đi chậm thôi mà. |
| GOLD-R019-013 | `unlock_doors` | `lock_doors` | Ê, mở khoá cửa ra lẹ giùm cái. |
| GOLD-R019-012 | `unlock_doors` | `lock_doors` | Mở khoá hết cửa ra, tui đâu có đi nhanh. |
| GOLD-R019-015 | `unlock_doors` | `lock_doors` | Mở khoá cửa hộ tui, xe đứng yên mà. |
| GOLD-R019-010 | `unlock_doors` | `lock_doors` | Mở khoá cửa cho tôi, đang đứng yên rồi đó. |
| GOLD-R019-016 | `unlock_doors` | `lock_doors` | Mở khoá cửa dùm, xe rề rề thôi hà. |
| GOLD-R019-019 | `unlock_doors` | `lock_doors` | Mở khoá cửa cho tôi, xe đứng yên mà. |
| GOLD-R019-017 | `unlock_doors` | `lock_doors` | Mở khoá cửa cho tui, xe đứng yên mà. |
| GOLD-R019-018 | `unlock_doors` | `lock_doors` | Cửa khoá rồi à, mở ra giùm tui cái. |
| GOLD-R020-003 | `OPEN_BONNET` | `INTENT_UNKNOWN` | Cho mở nắp ca-pô cái, kiểm tra máy chút. |
| GOLD-R020-008 | `OPEN_BONNET` | `INTENT_UNKNOWN` | Mở nắp ca-pô lên xem giúp tôi cái, hình như máy đang kêu lạ. |
| GOLD-R020-015 | `OPEN_BONNET` | `INTENT_UNKNOWN` | Cho tui mở nắp ca-pô cái coi. |
| GOLD-R020-020 | `OPEN_BONNET` | `INTENT_UNKNOWN` | Bung capo lên coi, thay bình ắc quy. |
| GOLD-R021-001 | `OPEN_BONNET` | `INTENT_UNKNOWN` | Đang đi đây, cho mở nắp ca-pô đằng trước với. |
| GOLD-R021-004 | `OPEN_BONNET` | `INTENT_UNKNOWN` | Bung nắp trước lên cho tui coi, cốp sau khỏi cần. |
| GOLD-R021-007 | `OPEN_BONNET` | `INTENT_UNKNOWN` | Bung nắp capo lên cho tôi coi. |
| GOLD-R021-026 | `OPEN_BONNET` | `INTENT_UNKNOWN` | Bung capo lên coi, hình như dầu máy thiếu rồi. |
| GOLD-R021-022 | `OPEN_BONNET` | `INTENT_UNKNOWN` | Ê, mở nắp ca-pô lên, nghe máy kêu lạ quá. |
| GOLD-R021-023 | `OPEN_BONNET` | `INTENT_UNKNOWN` | Nhờ anh bung nắp capo, đổ thêm nước rửa kính. |
| GOLD-R024-005 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Chuyển sang Sport giúp tôi. |
| GOLD-R024-007 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Chuyển sang Sport được không rứa? |
| GOLD-R024-006 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Thử sức con xe coi răng, drive mode Sport chuyển cái. |
| GOLD-R024-011 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Cho tui chuyển qua Sport cái coi. |
| GOLD-R024-020 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Cho em chuyển sang Sport với ạ. |
| GOLD-R024-015 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Chuyển drive mode qua Sport cho tôi với. |
| GOLD-R024-018 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Chuyển chế độ lái sang Thể Thao hộ tớ nhé. |
| GOLD-R024-019 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Đổi chế độ lái sang Thể Thao cho anh. |
| GOLD-R025-007 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Chuyển sang Sport được chưa hè? |
| GOLD-R025-009 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Chuyển drive mode Sport giùm anh. |
| GOLD-R025-013 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Sport, chuyển qua liền cho tui. |

---

## Đọc kết quả (thêm tay)

**T1-only baseline: intent accuracy 58.1%, INTENT_UNKNOWN 37%, pipeline outcome 59.0%.** Latency T1 ≈ 0.01 ms.

### Chẩn đoán
- **Kiểu lỗi áp đảo = `INTENT_UNKNOWN`** (T1 không khớp được action+entity). Gần như toàn bộ các intent recall thấp đều rơi vào UNKNOWN, không phải nhầm sang intent khác.
- Golden dataset cố tình khó: giọng Trung Bộ nặng ("răng/rứa/mô/ni/nớ"), câu nhiễu, distractor. T1 khớp keyword tất định không xử được diễn đạt biến thể.
- Vài confusion thật (không phải UNKNOWN): `get_door_lock_status → lock_doors` (39), `unlock_doors → lock_doors` (29) — keyword "khóa"/"cửa" đè nhau. Đây là lỗi thiết kế keyword T1, sửa được bằng entity đặc thù hơn.
- `restore_driverseat_pos` 0%, `ad_driverseat_pos` 0% — thiếu keyword / không tách được khỏi nhau.

### Kết luận
Constraint engine đã 100% (METRICS_PHASE1.md) → **toàn bộ khoảng cách end-to-end nằm ở intent classification.** T1 gánh được ~58%; phần còn lại cần:
1. **T2 (PhoBERT semantic)** — đóng đúng khoảng UNKNOWN 37%. **Đang bị chặn môi trường:** `onnxruntime` DLL lỗi (đã reinstall `onnxruntime==1.19.2` trong session này — có side-effect làm lệch `protobuf` cho streamlit/weaviate), `pyvi` đang cài, `model/model.onnx` cần `py -3 setup_model.py` (tải từ HuggingFace). Nên chạy trong venv sạch.
2. **Tinh chỉnh keyword T1** — bổ sung biến thể phương ngữ + entity đặc thù để giảm confusion `lock_doors`. Việc này cần người bản ngữ (Đạt).
3. 8 intent vừa thêm keyword (`AD_WIPER_MAX`, `lock_doors`, `switch_drivemode_eco/normal`, `turnon/off_hazardlight`, `turnoff_turnsignal_left/right`) là seed — **cần Đạt review**.

> Con số T1+T2 sẽ được đo lại (`run_classifier.py` tự bật T2 khi `model/model.onnx` có mặt) và ghi đè báo cáo này.
