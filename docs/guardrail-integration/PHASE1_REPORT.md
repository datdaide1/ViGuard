# Pha 1′ — Báo cáo hoàn thành

**Kỳ:** 2026-09-06 → 2026-09-07 · **Nhánh:** `feat/guardrail-agent-integration`
· **Trạng thái: HOÀN THÀNH.** Sang Pha 2′.

> Báo cáo tổng hợp. Chi tiết: `AUDIT.md` (kế hoạch), `PHASE0_RULE_DIFF.md`,
> `FROZEN_TESTSET_REVIEW.md`, `T2_DECISION.md`, `METRICS_PHASE1*.md`.
> Điểm vào cho session mới: `STATUS.md`.

---

## 1. Mục tiêu Pha 1′

Xây **decision core của Guardrail** (phân loại intent + đánh giá 109 rule → 1
trong 7 outcome) và **đo được trên tập độc lập** — không phụ thuộc agent, HTTP,
UI. Đây là phần Sprint 3 (kế hoạch cũ) chưa từng làm xong.

## 2. Đã giao

| Hạng mục | File | Ghi chú |
|---|---|---|
| Import guardrail của Long | `vf_guardrails/` | từ repo sibling, commit `cbfea6f` |
| Audit tích hợp | `docs/guardrail-integration/AUDIT.md` | bảng giữ/sửa/xây từng thành phần vs contract v1 |
| **Constraint engine mới** | `vf_guardrails/policy/` | `conditions.py` (AST evaluator, no `eval()`) · `rules.py` (nạp 109 rule từ CSV, fail-closed, `policy_checksum`) · `state.py` (VehicleState canonical) · `engine.py` (`PolicyEngine`, 3 rule precedence, phase gate/monitor) |
| **Frozen independent test set** | `vf_guardrails/evals/data/frozen_testset.jsonl` | 530 dòng, gen bởi agent ngoài (không đọc repo), regen hard-neg v2, `validate_frozen.py` sạch |
| **T2 intent classifier** | `vf_guardrails/classifier/` | TF-IDF (char2-5 + word1-2) + LinearSVC; `model_tfidf.pkl` committed; `IntentResolver` (T2 primary) |
| **Guardrail facade** | `vf_guardrails/guardrail.py` | `Guardrail.process(text, state) → GuardrailResult` |
| Harness đo | `vf_guardrails/evals/` | `run_golden.py`, `run_frozen.py`, `run_t2.py`, `run_t2_phobert.py`, `run_benchmark.py` |
| Test | `vf_guardrails/tests/` | `test_policy_engine.py` (12, gồm oracle 2313 dòng) + `test_guardrail.py` (7 e2e) |
| Đã xoá | — | `src/safety_engine.py`, `config/safety_rules.yaml`, `src/guardrail.py`, `src/models.py`, `src/agent.py` (66 KB), `app_sim.py`, `car_status.py` |

## 3. Bằng chứng (số liệu)

| Thành phần | Kết quả | Mục tiêu / tham chiếu |
|---|---|---|
| **Constraint engine** — outcome accuracy trên golden dataset (2.313 dòng, đủ 7 outcome) | **100.0% (2313/2313)** | PRD: reproduce đúng workbook |
| Engine latency p50 / p95 / p99 | 0.04 / 0.10 / **0.13 ms** | PRD §15: gate ≤5 ms p99 ✅ |
| **T2 classifier** (TF-IDF) — intent accuracy trên frozen | **88.3%** (positive 91.0%, hard-neg 77.4%) | — |
| T1 (keyword, không train) — frozen | 53.4% | sàn tham chiếu |
| PhoBERT emb + LinearSVC — frozen | 79.2% | đối chứng (thua TF-IDF ~9 điểm) |
| T2 latency p99 | ~2–5 ms | PRD §15: T2 ≤20 ms p99 ✅ |
| **Guardrail e2e** `process()` latency p99 | **~2.4–5 ms** | PRD §15: fast-path ≤25 ms p99 ✅ |
| Test suite | **19 pass** | — |

Đo trên frozen = leakage-free (T1 không train; T2 train golden pool, eval CHỈ
trên frozen). Không đo trên split của golden pool.

## 4. Quyết định đã chốt (D1–D6 + T2)

| # | Chốt |
|---|---|
| D1 | 2 service tách (`vf_guardrails/` + `vivi-agent/`) qua HTTP contract v1 |
| D2 | Guardrail trả `answer={grounded, facts}`; agent verbalize |
| D3 | Source of truth 109 rule = `rules.json` (== `Driver_constraints.xlsx`); parse `condition` trực tiếp; **bỏ `safety_rules.yaml`** (chỉ phủ 47/109, 6 rule hỏng — `PHASE0_RULE_DIFF.md`) |
| D4 | 1 schema `VehicleState`; field/enum theo workbook (`speed`, `day`/`night`, `door_lock_state`) |
| D5 | T3 SLM: hoãn |
| D6 | UI: hoãn |
| **T2** | **TF-IDF + LinearSVC** (char2-5 + word1-2), no-abstain, **primary**. T1 hạ vai trò. (`T2_DECISION.md`) |

**Phát hiện phụ:** T2 standalone (88.3%) > T1→T2 cascade (85.7%) — T1 trả lời
chắc-nhưng-sai hại ~2.6 điểm → T2 làm primary.

## 5. Tiêu chí gate Pha 1′ — ✅ đạt

- [x] 109/109 rule reproduce đúng outcome trên witness states + golden dataset (100%).
- [x] Báo cáo metrics classifier trên tập độc lập (frozen 88.3%).
- [x] Latency trong ngưỡng PRD §15 (engine, T2, e2e).
- [x] Fail-closed: intent không phân giải → `INTENT_UNRESOLVED` (không phải outcome).
- [x] Code cũ của Long đã xoá; facade mới chạy trên `policy/` + `classifier/`.
- [x] 19 test pass.

## 6. Giới hạn / nợ kỹ thuật (mang sang sau)

| Vấn đề | Ảnh hưởng | Kế hoạch |
|---|---|---|
| Golden dataset `reviewed=0/2313` | 100% engine = "khớp nhãn", nhãn chưa kiểm độc lập | Native-speaker review khi có thời gian |
| `policy/state.py::_STATE_DEFAULTS` | Giả định "đỗ, an toàn, ban ngày, pin đầy" để hoàn thiện state một phần | Review nếu convention đổi |
| Frozen `state_hint → outcome` chưa parse | Chưa có số pipeline end-to-end trên frozen (chỉ có intent) | TODO trong `run_frozen.py`; engine đã 100% nên không gấp |
| T2 lỗi ở cặp câu-hỏi ↔ lệnh (`get_door_lock_status`↔`lock_doors`…) | ~10/530 | Thêm sample golden hoặc rule hậu-xử-lý (câu hỏi cuối "?"/"chưa"/"hay" → `get_*`) |
| T2 OOS rejection yếu (min_score=-0.5) | Câu ngoài 53-intent có thể bị ép vào 1 intent | Catalog pilot đóng; tinh chỉnh abstain ở Pha 2′ nếu cần |
| Frozen hard-neg `ngan` bucket 18% (< 20%) | Nhẹ | Câu gen thiên dài; không block |
| venv `.venv-phobert/` (~6 GB) | Chỉ để re-run PhoBERT | Xoá được, số đã ghi lại |

## 7. Sang Pha 2′ — Contract / HTTP layer

Wrap `Guardrail` (đã có, đã đo) vào HTTP service v1:
- 4 endpoint (`/v1/evaluate/action|query`, `/v1/confirmations/confirm`, `/v1/monitor/evaluate`)
- `ActionProposal` + `proposal_digest`; `ActionPermit` cho ALLOW (digest-bound, single-use, expiry); `policy_checksum` + `state_version`; typed error envelope
- CONFIRM lifecycle + re-evaluate; Monitor engine (5 rule)
- Swap `MockGuardrail` → service thật trong E2E của `vivi-agent/`

Contract cứng: `vivi-agent/src/vivi_agent/authorization/contract.py`.
Chi tiết: `AUDIT.md` §6 "Pha 2′".
