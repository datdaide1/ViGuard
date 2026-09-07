# Frozen test set — review (2026-09-07)

File: `vf_guardrails/evals/data/frozen_testset.jsonl` (530 dòng) +
`frozen_testset_generation_notes.md`. Gen bởi 1 agent khác từ
[`FROZEN_TESTSET_SPEC.md`](FROZEN_TESTSET_SPEC.md), không đọc repo.

## Verdict: **DÙNG ĐƯỢC — đã lưu vào repo.** 2 điểm cần bạn quyết (§3).

---

## 1. Kiểm định cấu trúc — ✅ PASS

`py -3 vf_guardrails/evals/validate_frozen.py` → **0 error**.

| Tiêu chí | Kết quả |
|---|---|
| Số dòng / JSON hợp lệ / schema đủ 10 trường | 530 / OK / OK |
| Phủ intent | **53/53**, mỗi intent đúng **8 positive + 2 hard-negative** |
| `id` FROZEN-0001…0530, duy nhất, liên tục | OK |
| `sounds_like` hợp lệ (≠ intent, ∈ catalog, chỉ khi hard-neg) | OK |
| Trùng utterance tuyệt đối | 0 |
| Near-dup (Jaccard ≥ 0.72) | **1 cặp**: FROZEN-0292 ~ 0294 (`shift_gear_park`) |
| dialect | bac 29% / trung 23% / nam 27% / trung_tinh 21% — trong ngưỡng |
| register | mỗi loại ≥ 15% (trung_tinh sát: 80 = 15.1%) |
| length_bucket | mỗi loại ≥ 20% |

## 2. Kiểm định nội dung

**Đọc tay ~80 dòng** (các intent khó: `OPEN_BONNET`, ghế, camp/pet, `deactivate_esc`,
`explain_feature`, các cặp hard-neg): **nhãn positive chính xác, câu tự nhiên, đa
dạng thật, `state_hint` nhắm đúng ngưỡng.** Chất lượng cao.

**Chạy thử T1 trên frozen** (`vf_guardrails/config/intent_keywords.json`, T1-only):

| | Frozen | (Golden pool, tham chiếu) |
|---|---|---|
| Intent acc tổng | **55.3%** (293/530) | 58.1% |
| — positive rows | 58.3% (247/424) | — |
| — hard-negative rows | 43.4% (46/106) | — |
| INTENT_UNKNOWN | 27.9% | 37% |

→ Frozen cho số **thấp hơn nhẹ** (đúng kỳ vọng của tập độc lập — khó hơn, không
có câu "đã thuộc"), **failure mode giống hệt** (UNKNOWN áp đảo; cùng các intent
tệ: `switch_drivemode_*`, `restore_driverseat_pos`, `get_door_lock_status→lock_doors`).
**Đây là bằng chứng frozen set đo đúng thứ cần đo, không bị thổi.** Sẵn sàng làm
oracle cho T2.

## 3. Quyết định (2026-09-07)

- **3a → phương án A (regen).** Brief: [`FROZEN_TESTSET_REGEN_HARDNEG.md`](FROZEN_TESTSET_REGEN_HARDNEG.md).
  Đạt đưa cho agent gen; kết quả `frozen_hardneg_v2.jsonl` (106 + 1 dòng thay
  positive FROZEN-0294) → Claude merge vào `frozen_testset.jsonl` + re-validate.
- **3b → sửa bằng script.** `vf_guardrails/evals/fix_frozen_metadata.py` đã chạy:
  94 dòng `length_bucket` được tính lại từ số từ thực. Phân bổ sau khi sửa:
  `dai 241 / vua 210 / ngan 79` — `ngan` tụt còn 15% (utterance vòng 1 thiên
  dài); brief regen yêu cầu ≥30 hard-neg ≤6 từ để kéo lại. 1 near-dup xử lý
  trong brief §7. Tỷ lệ viết tắt ~27%: chấp nhận ("k"="không" phổ biến), brief
  siết ≤15% cho phần hard-neg mới.

---

## 3-cũ. (giữ để đối chiếu) Hai điểm đã nêu

### 3a. Hard negatives bị đóng khuôn (84–98%)

104/106 hard-negative theo đúng 1 mẫu: **"[intent] chớ/chứ k phải [sounds_like]
đâu/mô/nghen"** — tự tuyên bố phủ định intent dễ nhầm.

Vấn đề: câu nói thật hiếm khi "khai" rằng nó KHÔNG phải intent Y. Mẫu này test
"xử lý câu có disclaimer" chứ không phải "phân giải mơ hồ thật sự". Làm
hard-negative dễ hơn thực tế theo một hướng cụ thể.

Spec §7 có gợi ý nhiều dạng (câu hỏi trạng thái "cửa khóa chưa", va chạm gần
nghĩa, câu một phần) — agent chỉ dùng 1 dạng.

**Chọn:**
- **(A)** Regen 106 hard-negative với ràng buộc: ≤ 40% dùng "k phải Y"; còn lại
  phải là câu-hỏi-trạng-thái / va-chạm-gần-nghĩa / ngữ-cảnh-bẫy không tuyên bố
  phủ định. Re-gen nhỏ, rẻ. → *khuyến nghị*
- **(B)** Giữ nguyên, nhưng khi báo cáo **tách riêng** hard-neg accuracy + caveat
  "explicit-disclaimer negatives, dễ hơn confusable thật".

### 3b. Metadata sai nhẹ (không ảnh hưởng metric lõi — utterance+intent)

- **Tỷ lệ viết tắt thật ~27%** (141/530 có `k`/`ko`/`dc`/`j`), spec đặt ≤15%,
  notes tự báo 10.2% (đếm sót). "k" = "không" quá phổ biến trong nhắn tin VN nên
  có thể chấp nhận, nhưng lệch spec + lệch self-report.
- **~20 dòng `length_bucket = ngan` thực chất 8–13 từ** (vd FROZEN-0280: 13 từ).
  Nên là `vua`. Sửa được bằng script.
- 1 cặp near-dup (§1).

→ Đề xuất: sửa metadata bằng script (tôi làm), không cần regen.

---

## 4. Nếu bạn chọn 3a-(A)

Đưa lại cho agent gen: `FROZEN_TESTSET_SPEC.md` §7 + đoạn này:

> Chỉ regen **106 hard-negative** (giữ nguyên 424 positive, giữ id FROZEN-xxxx
> của các dòng hard-neg cũ). Ràng buộc thêm: **tối đa 40% được dùng cấu trúc
> "… chớ/không phải …"**. 60% còn lại chia đều 3 dạng:
> (i) câu hỏi trạng thái bị nhầm thành lệnh ("cửa khoá chưa rứa" → `get_door_lock_status`);
> (ii) va chạm gần nghĩa không phủ định ("bật ga tự động bám đuôi xe trước" mơ hồ AAC/HDA → chọn nhãn đúng theo ngữ cảnh còn lại);
> (iii) ngữ cảnh bẫy ("để con chó trong xe, bật máy lạnh giùm" → `activate_petmode`, dễ nhầm `open_window`).

---

## 5. Bước tiếp (sau khi 3a/3b chốt)

1. (Claude) Sửa metadata + adapter `run_classifier.py --dataset frozen`
   (parse `state_hint` → `vehicle_state` → engine → `expected_outcome`).
2. (Claude) Đo T1 chính thức trên frozen → `METRICS_PHASE1_FROZEN.md`.
3. (Claude+PM) Quyết T2: TF-IDF (train golden pool, **eval frozen**) vs PhoBERT venv.
4. Sau đó **đóng băng** frozen set — không sửa nữa.
