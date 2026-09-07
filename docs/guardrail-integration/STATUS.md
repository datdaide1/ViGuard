# ViGuard — Guardrail↔Agent Integration · STATUS (đọc file này trước)

**Cập nhật:** 2026-09-07 (**Pha 1′ + 2′ đã MERGE vào `guardrail-integration`**)
**Người thực thi:** Đạt (solo). Long, Công đã rời dự án.

> Đây là bản tổng quan cho **session/chat mới**. Đọc xong file này là nắm được:
> dự án đang ở đâu, đã quyết gì, làm gì tiếp. Chi tiết ở các doc được link.

### Nhánh (2026-09-07)

```
main  (d9d4746 — chưa có gì của guardrail)
└── guardrail-integration  (a8b3a7f)  ← nhánh tích lũy. Pha 1′ + 2′ ĐÃ VÀO.
      │     PR #48 (Pha 1′) + PR #49 (Pha 2′) — MERGED, nhánh phụ đã xoá.
      │
      └── feat/guardrail-phase3  ← ĐANG Ở ĐÂY. Pha 3′.
```

**Session mới:** `git checkout feat/guardrail-phase3` (nhánh từ `guardrail-integration`).
Pha 1′ + 2′ đã merge. Còn lại: Pha 3′ → PR → `guardrail-integration`, rồi
`guardrail-integration` → `main` (bước cuối, chưa làm).

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
| **Guardrail mới** | `vf_guardrails/guardrail.py` + `policy/` + `classifier/` + `service/` | ✅ Pha 1′: engine 100%, T2 88.3% frozen. ✅ Pha 2′: `service/` HTTP contract layer đầy đủ (action + confirm + monitor), gate AC-9/10/14–16/19 xanh qua adapter REAL, `run_both.py` chạy 3 kịch bản. |
| ~~Guardrail cũ của Long~~ | ~~`src/safety_engine.py`, `config/safety_rules.yaml`, `src/agent.py`, `app_sim.py`, `car_status.py`~~ | ❌ **đã xoá** (Bước 3). `src/intent_classifier.py` (T1) giữ lại cho eval. |
| **Golden dataset** | `golden-dataset/driver-constraints/` (gitignored) | 2.313 câu gán nhãn, `reviewed=0/2313`. `data/rules.json` = 109 rule canonical. `tools/derive_witness_states.py` có AST evaluator tái dùng được. |
| **Workbook gốc** | `Driver_constraints.xlsx` + `vf_guardrails/Driver_constraints(Constraints).csv` | 109 rule, 53 intent, 104 gate + 5 monitor. Source of truth. |

---

## 3. Kế hoạch & tiến độ

Chi tiết đầy đủ: **`docs/guardrail-integration/AUDIT.md`** (§6 là roadmap, §5 là bảng giữ/sửa/xây, §5.5 là quyết định).

| Pha | Mục tiêu | Trạng thái |
|---|---|---|
| **0** | Import guardrail, chốt quyết định, rule diff, sửa bug fail-open | ✅ **XONG** |
| **1′** | Decision core + classifier + đo trên frozen | ✅ **XONG** — engine 100%, T2 (TF-IDF) 88.3% frozen, guardrail facade mới, code cũ đã xoá. Trong PR #48. |
| **2′** | HTTP service v1 (CON-01) + permit + CONFIRM + Monitor + swap MockGuardrail | ✅ **XONG (4/4 tăng).** `service/` đầy đủ; 45 test mới; gate AC-9/10/14–16/19 xanh qua adapter REAL. `run_both.py` chạy. |
| **3′** | End-to-end demo polish + trace/event (PRD §16) + query fact-shaping (P2-D3) | 🔨 **bắt đầu** trên `feat/guardrail-phase3` (`run_both.py` skeleton đã có) |
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
| `…` | Frozen test set v1→v2 (regen hard-neg), `run_frozen.py`, `validate_frozen.py`. |
| `1c89e80` | **T2 quyết định** — TF-IDF 88.3% vs PhoBERT 79.2% trên frozen → chọn TF-IDF. `T2_DECISION.md`. |
| *(Bước 3)* | `classifier/` (train/save + IntentResolver + model), `guardrail.py` facade mới, **xoá** `safety_engine.py`/`safety_rules.yaml`/`agent.py`/`app_sim.py`/`car_status.py`. E2E latency p99 2.4 ms. |

### Bằng chứng đã có (con số thật)

> Số liệu tự sinh: `METRICS_PHASE1.md` (engine), `METRICS_PHASE1_CLASSIFIER.md`
> (classifier). Hai file đó bị ghi đè mỗi lần chạy harness — **diễn giải nằm ở
> đây, không nằm trong file metrics.**

**Constraint engine** (`run_golden.py`, engine-only — dùng intent có sẵn của mỗi dòng):
- **2313/2313 = 100%** outcome đúng, đủ 7 outcome. Latency p50/p95/p99 = 0.04/0.11/**0.14 ms** (PRD §15: gate ≤5 ms p99).
- Chứng minh: parser 109/109 condition, nạp workbook fail-closed, 3 rule precedence mode-exclusion (R034/R038/R041), tách phase gate/monitor, `speed<3→==0`.
- **Đây là deliverable Sprint 3 chưa từng làm.**

**Intent classifier** (đo trên frozen independent test set 530 dòng — leakage-free):

| | frozen all | positive | hard-neg |
|---|---|---|---|
| T1 (keyword, không train) | 53.4% | 58.3% | 34.0% |
| **T2 — TF-IDF + LinearSVC** ✅ CHỌN | **88.3%** | **91.0%** | 77.4% |
| T2 — PhoBERT emb + LinearSVC (đối chứng) | 79.2% | 80.2% | 75.5% |

- **Quyết định T2: chọn TF-IDF** (`char2-5+word1-2`, no-abstain, **primary**).
  Hơn PhoBERT ~9 điểm, nhẹ hơn (sklearn only), nhanh hơn ~7–50×. Chi tiết +
  lý do: `docs/guardrail-integration/T2_DECISION.md`.
- **T2 standalone (88.3%) > T1→T2 cascade (85.7%)** → T2 làm primary, T1 hạ vai
  trò (chỉ xác nhận / hoặc bỏ). Lỗi còn lại: cặp câu-hỏi↔lệnh (`get_door_lock_status`↔`lock_doors`…).
- (`run_classifier.py` cũ đo T1 trên golden pool = 58.1% — chỉ để tham chiếu, KHÔNG dùng cho T2 vì leakage.)

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

**Vòng 2 — ĐÓNG BĂNG ĐƯỢC (2026-09-07).** Hard-neg đã regen + merge, metadata
đã sửa. `validate_frozen.py` → 0 error/warning. Mẫu phủ định 15% (từ 84–98%).
**T1 trên frozen v2: 53.4% toàn tập / 58.3% positive-only** (golden pool 58.1%
→ khớp ⇒ frozen là thước đo độc lập hợp lệ). Chi tiết: `FROZEN_TESTSET_REVIEW.md`
"VÒNG 2". Số liệu: `run_frozen.py` → `METRICS_PHASE1_FROZEN.md`.

**Môi trường T2:** `E:\anaconda3` hỏng `torch`/`onnxruntime` → PhoBERT không
chạy được ở đây (xem §8). Dùng venv sạch, hoặc hướng nhẹ (TF-IDF sklearn — chạy được).

---

## 6. VIỆC TIẾP THEO (thứ tự — làm lần lượt, không song song)

### Bước 1 — Frozen test set: gen + review + regen + merge ✅ XONG
- v1 gen + review + metadata fix + hard-neg regen (v2) + merge. Final: 530 dòng,
  `validate_frozen.py` sạch. `run_frozen.py` đo T1 = **53.4%** (positive 58.3%).
- Còn thiếu: parse `state_hint` → outcome (pipeline end-to-end) — hoãn tới khi cần
  (TODO trong `run_frozen.py`; engine đã 100% nên chưa gấp).

### Bước 2 — T2 classifier ✅ XONG
- Đo cả TF-IDF (88.3%) và PhoBERT (79.2%) trên frozen → **chọn TF-IDF**
  (`vf_guardrails/classifier/tfidf.py`). `T2_DECISION.md`.
- T2 làm **primary**, T1 hạ vai trò.

### Bước 3 — Dọn & chốt Pha 1′ ✅ XONG
- `classifier/`: `tfidf.py` (train/save/load) + `train.py` + `model_tfidf.pkl` (3.5 MB, committed — golden dataset gitignored nên model đi kèm repo) + `intent.py` (`IntentResolver`, T2 primary, abstain `min_score=-0.5`).
- `vf_guardrails/guardrail.py` — facade mới: `IntentResolver` → `PolicyEngine` → `GuardrailResult`. Fail-closed: intent unresolved → `INTENT_UNRESOLVED` (không phải outcome).
- Xoá: `src/safety_engine.py`, `src/guardrail.py`, `src/models.py`, `src/agent.py`, `config/safety_rules.yaml`, `app_sim.py`, `car_status.py`, `tests/run_benchmark.py` (chuyển sang `evals/run_benchmark.py`).
- **Gate Pha 1′ ✅:** engine 100% (2313/2313), T2 88.3% frozen, e2e latency **p99 2.4 ms** (target ≤25 ms), 19 test pass, code cũ đã xoá.

### Bước 4 — Pha 2′ (HTTP contract layer) ✅ XONG — **`PHASE2_PLAN.md`** · **`PHASE2_REPORT.md`**

**Phát hiện quan trọng (PHASE2_PLAN.md §0):** có **2 đường phân giải intent**.
Đường CON-01 (agent authorization — cái Pha 2′ làm) **KHÔNG dùng TF-IDF** —
agent LLM chọn `tool`+`arguments`, guardrail map tất định `(tool,action,target,value)→intent`
(gương với `vivi-agent/.../tools/mapping/mapper.py`). TF-IDF của Pha 1 phục vụ
đường Gateway/Simulator (Pha 3′/UI). `PolicyEngine` dùng chung.

**Pha 2′ — ✅ XONG cả 4 tăng (2026-09-07).** `vf_guardrails/service/` = HTTP contract
layer đầy đủ cho đường CON-01:

| Route | Trạng thái |
|---|---|
| `POST /v1/evaluate/action` | ✅ map intent tất định → engine gate → decision + permit (chỉ ALLOW), digest-bound |
| `POST /v1/confirmations/confirm` | ✅ `PendingConfirmationStore` single-use/TTL 30 s; re-eval trên **state mới**; replay → `CONFIRMATION_NOT_ACTIVE`; session ≠ gốc → `CONFIRMATION_SESSION_MISMATCH` |
| `POST /v1/monitor/evaluate` | ✅ 5 monitor rule; no-trigger/monitor-ALLOW → "keep running"; block → outcome+`rule_id`; fail-closed → typed error (agent fail-safe stop) |
| `POST /v1/evaluate/query` | 🟡 skeleton (route + validate + ANSWER thô) — fact-shaping đầy đủ để Pha 3′ |

- **45 test mới; 61/61 vf_guardrails, 940/940 vivi-agent, không regress.** Gate AC-9/AC-10
  (2′.1), AC 14–16 (2′.2), AC-19 (2′.3) xanh qua `GuardrailClientAdapter(REAL)` +
  `ConfirmationManager` thật. `proposal_digest` khớp byte-for-byte `examples.json`.
- E2E swap: `vivi-agent/.../test_e2e_real_guardrail.py` (agent orchestrator thật ↔ service thật, không mock).
- Demo: **`py -3 run_both.py`** (boot service + agent, 3 kịch bản ALLOW/BLOCK/CONFIRM).
- Chạy service: `py -3 -m vf_guardrails.service` (P2-D5).

Chi tiết từng tăng + nợ kỹ thuật: `PHASE2_PLAN.md` §2. **Nợ nổi bật:** `turnon_LKA` map
nhưng không có rule (PM chấp nhận tạm — Long có thể thêm intent sau); query fact-shaping +
trace/event stream (PRD §16) → Pha 3′.

**Tiếp theo — Pha 3′:** end-to-end demo polish, trace/event stream đầy đủ, `/v1/evaluate/query`
fact-shaping (P2-D3), gộp PR. Xem `AUDIT.md` §6.

**Nguồn contract (đọc trước khi code):**
- `vivi-agent/src/vivi_agent/authorization/contract.py` — validator fail-closed
- `vivi-agent/src/vivi_agent/integrations/viguard/wire/guardrail-agent.schema.json` — JSON Schema
- `vivi-agent/src/vivi_agent/integrations/viguard/wire/examples.json` — payload mẫu 7 outcome
- `vivi-agent/src/vivi_agent/integrations/viguard/client.py` — client agent gọi (4 endpoint, retry)
- `vivi-agent/src/vivi_agent/integrations/viguard/mock_server.py` — cái đang thay
- `vivi-agent/src/vivi_agent/tools/mapping/mapper.py` — `DEFAULT_MAPPING_RULES` (nguồn tool→intent)

---

## 7. Bản đồ file (đọc gì khi cần)

| Cần biết | Đọc |
|---|---|
| Pha 2′ — plan + báo cáo | `docs/guardrail-integration/PHASE2_PLAN.md` · `PHASE2_REPORT.md` |
| **Pha 2′ — báo cáo hoàn thành** | **`docs/guardrail-integration/PHASE2_REPORT.md`** |
| HTTP contract layer (code) | `vf_guardrails/service/` — `app.py` (core), `http.py`, `tool_map.py`, `state_store.py`, `confirmations.py`, `active_actions.py`, `envelope.py` |
| Demo E2E 2 service | `run_both.py` (repo root) |
| Báo cáo hoàn thành Pha 1′ | `docs/guardrail-integration/PHASE1_REPORT.md` |
| Tổng quan + roadmap + quyết định | `docs/guardrail-integration/AUDIT.md` |
| Vì sao bỏ `safety_rules.yaml` | `docs/guardrail-integration/PHASE0_RULE_DIFF.md` |
| Constraint engine đúng bao nhiêu | `docs/guardrail-integration/METRICS_PHASE1.md` |
| Classifier T1 trên golden pool | `docs/guardrail-integration/METRICS_PHASE1_CLASSIFIER.md` |
| Classifier T1 trên frozen | `docs/guardrail-integration/METRICS_PHASE1_FROZEN.md` (`run_frozen.py`) |
| **T2: TF-IDF vs PhoBERT + quyết định** | **`docs/guardrail-integration/T2_DECISION.md`** (+ `METRICS_PHASE1_T2*.md`) |
| Spec tập test độc lập | `docs/guardrail-integration/FROZEN_TESTSET_SPEC.md` |
| Review tập test độc lập (đã gen) | `docs/guardrail-integration/FROZEN_TESTSET_REVIEW.md` |
| Tập test độc lập + notes | `vf_guardrails/evals/data/frozen_testset*.` |
| Contract Guardrail↔Agent (cứng) | `vivi-agent/src/vivi_agent/authorization/contract.py` |
| Wire protocol ví dụ | `vivi-agent/src/vivi_agent/integrations/viguard/wire/examples.json` |
| Yêu cầu sản phẩm | `specs/prd/PRD_Guardrail_FINAL.md` |
| Precedence rule (R034/R038/R041) | `golden-dataset/driver-constraints/COVERAGE_SPEC.md` §"Confirmed precedence" |

### Code mới (Pha 1′)

```
vf_guardrails/
  guardrail.py      Guardrail.process(text, state) -> GuardrailResult   ← facade
  policy/
    conditions.py   AST evaluator (no eval()) + normalize + 7 MANUAL_REWRITES
    rules.py        RuleSet.load() — 109 rule từ CSV, fail-closed, policy_checksum
    state.py        VehicleState canonical + _STATE_DEFAULTS (giả định Pha 1)
    engine.py       PolicyEngine.evaluate(intent, state, check_mode) -> Decision
  classifier/
    tfidf.py        TfidfIntentClassifier (train/save/load; char2-5 + word1-2 + LinearSVC)
    train.py        fit trên golden pool -> model_tfidf.pkl
    intent.py       IntentResolver — T2 primary, abstain min_score=-0.5
    model_tfidf.pkl 3.5 MB, committed
  src/intent_classifier.py   T1 (Aho-Corasick) — GIỮ, chỉ dùng cho eval so sánh
  evals/
    run_golden.py       engine vs golden dataset (100%)
    run_frozen.py       T1 vs frozen
    run_t2.py           TF-IDF T2 train+eval frozen
    run_t2_phobert.py   PhoBERT T2 (venv .venv-phobert)
    run_benchmark.py    latency p50/p95/p99
    validate_frozen.py / fix_frozen_metadata.py
  tests/
    test_policy_engine.py   12 test + oracle 2313 dòng
    test_guardrail.py       7 test e2e facade
```

### Code mới (Pha 2′ — `vf_guardrails/service/`)

```
vf_guardrails/
  __init__.py        (mới) — cho `py -3 -m vf_guardrails.service`
  service/
    tool_map.py      79 dòng (tool,action,target,value)->intent — copy nguyên của agent, exact lookup, fail-closed
    state_store.py   VehicleStateStore — state_version đơn điệu, snapshot bất biến, 4 preset
    confirmations.py PendingConfirmationStore — id single-use, TTL 30s, giữ proposal + origin_rule_id
    active_actions.py ActiveActionRegistry + MONITORED_INTENTS (5)
    envelope.py      copy proposal_digest + validate_action_proposal (contract v1); build decision/permit/error/confirmation schema-exact
    app.py           GuardrailService.handle(path,payload) -> (status,body) — core không transport
    http.py          stdlib ThreadingHTTPServer + /healthz
    __main__.py      `py -3 -m vf_guardrails.service` (P2-D5)
  tests/
    conftest.py            (mới) bootstrap cross-repo: path vivi-agent + shim `src`
    test_tool_map.py       11 — conformance row-by-row vs agent + coverage 53 intent
    test_service_http.py   ~15 — routing/status/state_store/query
    test_gate_2p1.py       5 — AC-9/AC-10 qua adapter REAL
    test_confirm_2p2.py    7 — AC-14/15/16 + session-mismatch + ConfirmationManager e2e
    test_monitor_2p3.py    10 — AC-19 + keep-running + INVALID_VEHICLE_STATE
run_both.py          (repo root) demo: service + agent, 3 kịch bản
vivi-agent/tests/e2e/vertical_slice/e2e-01/test_e2e_real_guardrail.py  (mới, 3) — orchestrator thật ↔ service thật
```

---

## 8. Cách chạy / verify

```bash
# Python: dùng "py -3" (KHÔNG "python" — nó là stub WindowsApps hỏng ở máy này)
# Output tiếng Việt: prefix PYTHONIOENCODING=utf-8 (console cp1258)

cd E:/V-GUARDRAIL/guardrail-for-agent

# train lại T2 model (nếu golden dataset có mặt)
py -3 -m vf_guardrails.classifier.train

# test toàn bộ (58: policy engine + facade + service HTTP contract layer)
py -3 -m pytest vf_guardrails/tests/ -q
# test contract phía agent không regress (940)
cd vivi-agent && py -3 -m pytest -q && cd ..

# Pha 2′: chạy service riêng, hoặc demo 2-service
py -3 -m vf_guardrails.service            # http://127.0.0.1:8089  (+ GET /healthz)
PYTHONIOENCODING=utf-8 py -3 run_both.py  # boot service + agent, 3 kịch bản ALLOW/BLOCK/CONFIRM

# metrics: engine (100%), T1/frozen (53.4%), T2 TF-IDF/frozen (88.3%), latency
PYTHONIOENCODING=utf-8 py -3 vf_guardrails/evals/run_golden.py
PYTHONIOENCODING=utf-8 py -3 vf_guardrails/evals/run_frozen.py
PYTHONIOENCODING=utf-8 py -3 vf_guardrails/evals/run_t2.py
PYTHONIOENCODING=utf-8 py -3 vf_guardrails/evals/run_benchmark.py

# PhoBERT đối chứng (venv)
.venv-phobert/Scripts/python vf_guardrails/evals/run_t2_phobert.py
```

**Gotcha môi trường:**
- `py -3` = Python 3.11 anaconda. CPU `torch`/`transformers` hỏng DLL (cả máy). **CUDA torch chạy được** → venv `.venv-phobert/` (torch cu124 + sentence-transformers + pyvi) cho PhoBERT: `.venv-phobert\Scripts\python <script>`.
- `onnxruntime` đã reinstall `1.19.2` → `protobuf 7.x` xung đột soft với `streamlit`/`weaviate` (không do dự án này).
- Default env đã cài: `pyahocorasick`, `pyyaml`, `pydantic`, `scikit-learn`, `scipy`, `pytest`. TF-IDF T2 chạy ở đây bình thường.

---

## 9. Việc git còn treo

- **PR #48** (Pha 1′) + **PR #49** (Pha 2′): **MERGED** vào `guardrail-integration` (a8b3a7f). Nhánh `feat/guardrail-agent-integration` + `feat/guardrail-phase2-http` đã xoá (local + remote).
- Nhánh hiện tại: **`feat/guardrail-phase3`** (từ `guardrail-integration`). Sau Pha 3′ → PR → `guardrail-integration`.
- **Bước cuối (chưa làm):** `guardrail-integration` → `main`.
- venv `.venv-phobert/` (~6 GB, gitignored) — chỉ để re-run PhoBERT, xoá được.
- `reports/` + `reports.zip` (báo cáo Sprint 2) — **cố ý để untracked**, PM quyết sau.
- Worktree cũ `.claude/worktrees/great-yalow-d7b474` — dọn nếu không dùng: `git worktree remove`.

---

## 10. Rủi ro / thứ cần để mắt

| Rủi ro | Ghi chú |
|---|---|
| Golden dataset `reviewed=0/2313` | 100% của engine = "khớp nhãn", nhãn chưa được kiểm độc lập. Frozen set giảm rủi ro này cho classification; outcome vẫn dựa nhãn. |
| `_STATE_DEFAULTS` trong `policy/state.py` | Giả định Pha 1 ("đỗ, an toàn, ban ngày, pin đầy") để hoàn thiện state một phần. Nếu review golden dataset đổi convention → chạy lại metrics. |
| 8 intent keyword vừa thêm (`58a5c43`) | Seed, chưa review bản ngữ. |
| `speed < 3 → == 0` | Là quyết định PM (PLAN.md §6a), áp cả runtime cho khớp oracle. Nếu PM đổi ý → sửa `conditions.py::normalize`. |
| Solo dev, ~15–22 ngày còn lại | Gate theo pha. Walking skeleton (Pha 3′) cho tín hiệu sớm. |
