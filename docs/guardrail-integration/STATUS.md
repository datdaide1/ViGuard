# ViGuard — Guardrail↔Agent Integration · STATUS (đọc file này trước)

**Cập nhật:** 2026-09-06
**Nhánh làm việc:** `feat/guardrail-agent-integration` (nhánh từ `main`)
**Người thực thi:** Đạt (solo). Long, Công đã rời dự án.

> Đây là bản tổng quan cho **session/chat mới**. Đọc xong file này là nắm được:
> dự án đang ở đâu, đã quyết gì, làm gì tiếp. Chi tiết nằm ở các doc được link.

---

## 1. Dự án là gì (1 phút)

ViGuard = một **Guardrail** đứng trước một **AI Agent trên xe điện**. Người dùng
gõ câu lệnh tiếng Việt → Guardrail (1) phân loại thành 1 trong **53 intent**,
(2) đánh giá **109 rule** theo trạng thái xe → ra 1 trong **7 outcome**
(`ALLOW / BLOCK_UNSAFE / BLOCK_UNAVAILABLE / CONFIRM / NOT_VOICE_ACTIONABLE /
ANSWER / UNKNOWN`). Chỉ `ALLOW` mới được gọi actuator. Agent nhận outcome và
biến thành phản hồi / hành động mô phỏng, **không tự đổi outcome**.

Nguồn spec: `specs/prd/PRD_Guardrail_FINAL.md`, `specs/architecture/Architecture_Guardrail_FINAL.md`.

**Chuyển hướng gần đây (quan trọng):** từ dự án sprint ngắn hạn → dự án dài hạn,
1 người. Hướng tương lai: multi-agent + nhiều loại xe + UI. **Nhưng việc trước
mắt là hoàn thiện pipeline guardrail+agent cho VF8 đã.** Phần scale/UI brainstorm
riêng SAU khi pipeline xong.

---

## 2. Tài sản & bối cảnh code

| Thành phần | Ở đâu | Trạng thái |
|---|---|---|
| **ViVi Agent** | `vivi-agent/` (package Python, 934 test) | ✅ Xong mức sản phẩm. Do Đạt làm. Đã có `MockGuardrail` nói đúng contract v1. |
| **Contract v1** (Guardrail↔Agent) | `vivi-agent/src/vivi_agent/authorization/contract.py` + `integrations/viguard/` | ✅ Validator fail-closed hoàn chỉnh: HTTP JSON, 4 endpoint, permit digest-bound, typed error. |
| **Guardrail cũ của Long** | `vf_guardrails/` (import từ repo sibling 2026-09-06, commit `cbfea6f`) | ⚠️ Bản đơn giản, lệch spec. Xem §4. `src/agent.py` 66KB = agent riêng của Long, **sẽ xoá** (dùng `vivi-agent/` là canonical). |
| **Guardrail mới (đang xây)** | `vf_guardrails/policy/` | 🔨 Constraint engine ✅ xong 100%. Classifier + HTTP layer chưa. |
| **Golden dataset** | `golden-dataset/driver-constraints/` (gitignored) | 2.313 câu gán nhãn, `reviewed=0/2313`. `data/rules.json` = 109 rule canonical. `tools/derive_witness_states.py` có AST evaluator tái dùng được. |
| **Workbook gốc** | `Driver_constraints.xlsx` + `vf_guardrails/Driver_constraints(Constraints).csv` | 109 rule, 53 intent, 104 gate + 5 monitor. Source of truth. |

---

## 3. Kế hoạch & tiến độ

Chi tiết đầy đủ: **`docs/guardrail-integration/AUDIT.md`** (§6 là roadmap, §5 là bảng giữ/sửa/xây, §5.5 là quyết định).

| Pha | Mục tiêu | Trạng thái |
|---|---|---|
| **0** | Import guardrail, chốt quyết định, rule diff, sửa bug fail-open | ✅ **XONG** |
| **1′** | Decision core + đo trên golden dataset | 🔨 **ĐANG** — engine ✅ 100%; classifier ⏳ chờ frozen test set |
| **2′** | HTTP service v1 wrap engine + permit + CONFIRM + Monitor + swap MockGuardrail | ⬜ chưa bắt đầu |
| **3′** | End-to-end demo (`run_both.py`) + trace + polish | ⬜ chưa bắt đầu |
| *sau* | Brainstorm scale (multi-agent / multi-vehicle) + UI | ⬜ ngoài phạm vi hiện tại |

Ước lượng còn lại: ~15–22 dev-days (đã sập từ 25–40 nhờ engine dựng sẵn từ golden-dataset tooling).

### Quyết định đã chốt (D1–D6, không mở lại trừ khi có lý do mới)

| # | Chốt |
|---|---|
| D1 | **2 service tách** (`vf_guardrails/` + `vivi-agent/`), nói chuyện qua HTTP contract v1. Không gộp monorepo. |
| D2 | Guardrail trả `answer={grounded, facts}` (facts có cấu trúc); **agent** verbalize thành câu tiếng Việt. |
| D3 | Source of truth 109 rule = `golden-dataset/.../data/rules.json` (== `Driver_constraints.xlsx`). **Parse cột `condition` trực tiếp**, retire `vf_guardrails/config/safety_rules.yaml`. |
| D4 | 1 schema `VehicleState` chung: field name + enum theo workbook (`speed` không `speed_kmh`, lowercase `day`/`night`, `door_lock_state` không `doors_locked`). |
| D5 | T3 SLM: **hoãn** — sau khi T1/T2 đạt metric. |
| D6 | UI: **hoãn** sang pha scale. |

---

## 4. Đã làm gì trong nhánh này (6 commit)

| Commit | Việc |
|---|---|
| `cbfea6f` | Import `vf_guardrails/` + `AUDIT.md` (bảng giữ/sửa/xây từng thành phần vs contract). |
| `a167eaa` | **Sửa bug fail-open** trong `vf_guardrails/src/guardrail.py`: intent không phân giải → `CLASSIFICATION_ERROR` (không phải ALLOW); 0 rule match → `BLOCK_UNAVAILABLE` (không ALLOW ngầm). Vi phạm cũ: BR-02/BR-09/FR-07. |
| `7e068c8` | **Rule diff** (`PHASE0_RULE_DIFF.md`): `safety_rules.yaml` của Long chỉ phủ 47/109, 6 rule (R100–102) trỏ sai intent, sai enum case / field name / boolean structure → **bỏ hẳn**, không cứu. D1–D6 lock. |
| `c1e0457` | **Constraint engine mới** `vf_guardrails/policy/` (`conditions.py`, `rules.py`, `state.py`, `engine.py`). Kết quả: **2313/2313 = 100%** outcome đúng trên golden dataset, latency p99 **0.14 ms**. 15 test pass. Chi tiết: `METRICS_PHASE1.md`. |
| `58a5c43` | **T1 classifier baseline**: `evals/run_classifier.py` + thêm keyword 8 intent thiếu. Kết quả T1-only: **intent 58.1%**, UNKNOWN 37%, pipeline 59%. Chi tiết: `METRICS_PHASE1_CLASSIFIER.md`. |
| `de5c609` | **`FROZEN_TESTSET_SPEC.md`** — hướng dẫn tự chứa để 1 agent khác (không đọc repo) gen tập test độc lập. |

### Bằng chứng đã có (con số thật)

> Số liệu tự sinh: `METRICS_PHASE1.md` (engine), `METRICS_PHASE1_CLASSIFIER.md`
> (classifier). Hai file đó bị ghi đè mỗi lần chạy harness — **diễn giải nằm ở
> đây, không nằm trong file metrics.**

**Constraint engine** (`run_golden.py`, engine-only — dùng intent có sẵn của mỗi dòng):
- **2313/2313 = 100%** outcome đúng, đủ 7 outcome. Latency p50/p95/p99 = 0.04/0.11/**0.14 ms** (PRD §15: gate ≤5 ms p99).
- Chứng minh: parser 109/109 condition, nạp workbook fail-closed, 3 rule precedence mode-exclusion (R034/R038/R041), tách phase gate/monitor, `speed<3→==0`.
- **Đây là deliverable Sprint 3 chưa từng làm.**

**T1 intent classifier** (`run_classifier.py`, T1-only vì T2 chặn môi trường):
- **intent 58.1%** · macro-F1 0.658 · INTENT_UNKNOWN **37%** · pipeline (classified intent → engine) 59% · latency ~0.01 ms.
- Hợp lệ làm **sàn** (T1 là keyword hand-authored, không train → không leakage).
- **Kiểu lỗi áp đảo = `INTENT_UNKNOWN`** (T1 không khớp action+entity trên câu phương ngữ / diễn đạt biến thể). Vài confusion thật: `get_door_lock_status→lock_doors` (39), `unlock_doors→lock_doors` (29). `restore_driverseat_pos` & `ad_driverseat_pos` recall 0%.
- Vì engine đã 100%, **toàn bộ khoảng cách end-to-end = intent classification**, và ~37 điểm của nó chính là phần T2 sinh ra để cứu.

**Giới hạn chung:** golden dataset `reviewed=0/2313` (100% = "khớp nhãn", nhãn
chưa kiểm độc lập). `_STATE_DEFAULTS` là giả định Pha 1. Chưa đo determinism
qua nhiều lần chạy, tier distribution.

---

## 5. Frozen independent test set — ĐÃ CÓ, đang review

**Vì sao cần:** đo T2 (trained classifier) trên golden pool bị **leakage** —
pool sinh theo khuôn, nhiều câu gần trùng → mọi train/test split đều rò rỉ.
Tập test độc lập (DATA-10) chưa bao giờ build.

**Trạng thái (2026-09-07):** file đã về: `vf_guardrails/evals/data/frozen_testset.jsonl`
(530 dòng) + `frozen_testset_generation_notes.md`. Gen từ `FROZEN_TESTSET_SPEC.md`.

**Review:** `docs/guardrail-integration/FROZEN_TESTSET_REVIEW.md` — **dùng được**.
Cấu trúc PASS (53/53 intent, 8+2 mỗi intent, 0 dup, balance OK). Positive labels
chính xác. T1 trên frozen = **55.3%** (golden pool 58.1%) — số hơi thấp hơn +
failure mode giống → frozen đo đúng, không bị thổi.

**Quyết định (2026-09-07):**
- **3a → regen** 106 hard-negative (bị đóng khuôn "[X] chớ k phải [Y]").
  Brief: `docs/guardrail-integration/FROZEN_TESTSET_REGEN_HARDNEG.md` → Đạt đưa
  cho agent gen. Kết quả `frozen_hardneg_v2.jsonl` → Claude merge + re-validate.
- **3b → xong.** `fix_frozen_metadata.py` đã sửa 94 `length_bucket`.

**Môi trường T2:** `E:\anaconda3` hỏng `torch`/`onnxruntime` → PhoBERT không
chạy được ở đây (xem §8). Dùng venv sạch, hoặc hướng nhẹ (TF-IDF sklearn — chạy được).

---

## 6. VIỆC TIẾP THEO (thứ tự — làm lần lượt, không song song)

### Bước 1 — Frozen test set: gen + review + fix ✅ / ⏳
- ✅ Gen vòng 1 (`vf_guardrails/evals/data/frozen_testset.jsonl`), review (`FROZEN_TESTSET_REVIEW.md`), metadata fix 3b (`fix_frozen_metadata.py`).
- ⏳ **(Đạt) Regen 106 hard-neg** từ `FROZEN_TESTSET_REGEN_HARDNEG.md` → `frozen_hardneg_v2.jsonl`.

### Bước 2 — (Claude) Merge hard-neg v2 + adapter + đo T1 ← TIẾP THEO
- Merge `frozen_hardneg_v2.jsonl` (106 + FROZEN-0294) vào `frozen_testset.jsonl`; chạy `validate_frozen.py` + `fix_frozen_metadata.py --write`.
- `run_classifier.py`: thêm `--dataset` + đọc format frozen; parse `state_hint` → `vehicle_state` → engine → `expected_outcome`.
- Chạy → ghi `METRICS_PHASE1_FROZEN.md`. Baseline T1 thật. (Đo tay vòng 1: **55.3%**.)

### Bước 3 — (Claude + Đạt) Quyết & làm T2
- **Ưu tiên đề xuất: TF-IDF (char+word n-gram) + LinearSVC**, sklearn thuần
  (chạy được ở env hiện tại), train trên golden pool, **eval CHỈ trên frozen**.
  Có confidence + margin → abstain về `INTENT_UNKNOWN` (FR-03).
- Phương án B: PhoBERT ONNX trong venv sạch (`setup_model.py` + `pyvi` +
  `onnxruntime`), nếu TF-IDF không đủ.
- Tune keyword T1 từ domain knowledge (KHÔNG mine từ eval set) — nhắm intent
  recall 0% (`restore_driverseat_pos`, `ad_driverseat_pos`) + confusion `lock_doors`.

### Bước 4 — (Claude) Dọn & chốt Pha 1′
- Xoá `vf_guardrails/src/safety_engine.py` + `config/safety_rules.yaml` + `src/agent.py` (Long) + `app_sim.py`.
- Cập nhật `vf_guardrails/src/guardrail.py` (hoặc thay bằng module mới) dùng `policy/` engine + classifier mới.
- Gate Pha 1′: 109/109 rule đúng (đã có) + báo cáo metrics classifier trên frozen + xoá code cũ.

### Bước 5 — Pha 2′ (HTTP layer) — xem `AUDIT.md` §6

---

## 7. Bản đồ file (đọc gì khi cần)

| Cần biết | Đọc |
|---|---|
| Tổng quan + roadmap + quyết định | **`docs/guardrail-integration/AUDIT.md`** |
| Vì sao bỏ `safety_rules.yaml` | `docs/guardrail-integration/PHASE0_RULE_DIFF.md` |
| Constraint engine đúng bao nhiêu | `docs/guardrail-integration/METRICS_PHASE1.md` |
| Classifier T1 đúng bao nhiêu | `docs/guardrail-integration/METRICS_PHASE1_CLASSIFIER.md` |
| Spec tập test độc lập | `docs/guardrail-integration/FROZEN_TESTSET_SPEC.md` |
| Review tập test độc lập (đã gen) | `docs/guardrail-integration/FROZEN_TESTSET_REVIEW.md` |
| Tập test độc lập + notes | `vf_guardrails/evals/data/frozen_testset*.` |
| Contract Guardrail↔Agent (cứng) | `vivi-agent/src/vivi_agent/authorization/contract.py` |
| Wire protocol ví dụ | `vivi-agent/src/vivi_agent/integrations/viguard/wire/examples.json` |
| Yêu cầu sản phẩm | `specs/prd/PRD_Guardrail_FINAL.md` |
| Precedence rule (R034/R038/R041) | `golden-dataset/driver-constraints/COVERAGE_SPEC.md` §"Confirmed precedence" |

### Code mới (Pha 1′)

```
vf_guardrails/policy/
  conditions.py   AST evaluator (no eval()) + normalize + 7 MANUAL_REWRITES
  rules.py        RuleSet.load() — 109 rule từ CSV, fail-closed, policy_checksum
  state.py        VehicleState canonical + _STATE_DEFAULTS (giả định Pha 1, cần review)
  engine.py       PolicyEngine.evaluate(intent, state, check_mode) -> Decision
vf_guardrails/evals/
  run_golden.py       metrics constraint engine vs golden dataset
  run_classifier.py   metrics classifier + pipeline
vf_guardrails/tests/
  test_policy_engine.py   12 test + oracle 2313 dòng
```

---

## 8. Cách chạy / verify

```bash
# Python: dùng "py -3" (KHÔNG "python" — nó là stub WindowsApps hỏng ở máy này)
# Output tiếng Việt: prefix PYTHONIOENCODING=utf-8 (console cp1258)

cd E:/V-GUARDRAIL/guardrail-for-agent

# test engine + guardrail
py -3 -m pytest vf_guardrails/tests/test_policy_engine.py vf_guardrails/tests/test_guardrail.py -q

# metrics constraint engine (ghi METRICS_PHASE1.md)
PYTHONIOENCODING=utf-8 py -3 vf_guardrails/evals/run_golden.py

# metrics classifier (ghi METRICS_PHASE1_CLASSIFIER.md)
PYTHONIOENCODING=utf-8 py -3 vf_guardrails/evals/run_classifier.py

# regen rule diff
py -3 docs/guardrail-integration/phase0_diff.py
```

**Gotcha môi trường:**
- `py -3` = Python 3.11 anaconda. `torch` / `transformers` hỏng DLL → T2 không chạy được ở đây.
- `onnxruntime` đã bị reinstall `1.19.2` (fix DLL) → `protobuf 7.x` xung đột soft với `streamlit`/`weaviate` (không do dự án này).
- `pyahocorasick`, `pyyaml`, `sklearn`, `scipy`, `pyvi` đã cài.

---

## 9. Việc git còn treo

- Worktree cũ `.claude/worktrees/great-yalow-d7b474` (detached HEAD) — dọn nếu không dùng: `git worktree remove`.
- `reports/` + `reports.zip` (báo cáo Sprint 2) — **cố ý để untracked**, PM quyết sau.
- Nhánh phụ local + remote (`datalexander/agent-completion`, `vivi-agent/scafford`) — đã xoá hết. Repo = `main` + `feat/guardrail-agent-integration`.

---

## 10. Rủi ro / thứ cần để mắt

| Rủi ro | Ghi chú |
|---|---|
| Golden dataset `reviewed=0/2313` | 100% của engine = "khớp nhãn", nhãn chưa được kiểm độc lập. Frozen set giảm rủi ro này cho classification; outcome vẫn dựa nhãn. |
| `_STATE_DEFAULTS` trong `policy/state.py` | Giả định Pha 1 ("đỗ, an toàn, ban ngày, pin đầy") để hoàn thiện state một phần. Nếu review golden dataset đổi convention → chạy lại metrics. |
| 8 intent keyword vừa thêm (`58a5c43`) | Seed, chưa review bản ngữ. |
| `speed < 3 → == 0` | Là quyết định PM (PLAN.md §6a), áp cả runtime cho khớp oracle. Nếu PM đổi ý → sửa `conditions.py::normalize`. |
| Solo dev, ~15–22 ngày còn lại | Gate theo pha. Walking skeleton (Pha 3′) cho tín hiệu sớm. |
