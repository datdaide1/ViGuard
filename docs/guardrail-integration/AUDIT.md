# Guardrail ↔ Agent — Audit tích hợp & Plan rebuild

> 👉 **Session mới đọc [`STATUS.md`](STATUS.md) trước** — đó là bản tổng quan
> tiến độ + việc tiếp theo. File này là audit kỹ thuật chi tiết (bảng giữ/sửa/
> xây, roadmap §6, quyết định §5.5).

**Ngày:** 2026-09-06
**Nhánh:** `feat/guardrail-agent-integration`
**Tác giả:** Đạt (với Claude Code)
**Mục tiêu tài liệu:** đối chiếu contract mà ViVi Agent (`vivi-agent/`) được xây theo với hiện trạng code guardrail của Long (`vf_guardrails/`, sibling repo, import vào branch này), ra bảng **giữ / sửa / xây mới / quyết định** từng thành phần kèm ước lượng effort. Đây là plan để hoàn thiện pipeline `text → Guardrail → Agent`.

---

## 0. Nguồn đối chiếu

| Nguồn | Vai trò |
|---|---|
| `specs/prd/PRD_Guardrail_FINAL.md` | Yêu cầu chức năng (FR-01…FR-14), invariant (BR-01…BR-12), acceptance criteria, success metrics |
| `specs/architecture/Architecture_Guardrail_FINAL.md` | Component boundary, API |
| `vivi-agent/src/vivi_agent/authorization/contract.py` | **Contract v1.0.0** — validator fail-closed cho envelope Guardrail↔Agent (đây là "hợp đồng cứng") |
| `vivi-agent/src/vivi_agent/integrations/viguard/client.py` | HTTP client agent dùng để gọi guardrail |
| `vivi-agent/src/vivi_agent/integrations/viguard/wire/examples.json` | Ví dụ payload đúng cho 7 outcome + error + confirm + monitor |
| `vf_guardrails/` | Code guardrail của Long (import 2026-09-06 từ `E:/V-GUARDRAIL/vf_guardrails` @ `7fb7074`) |

---

## 1. Verdict

Long **không làm sai hướng** — lớp phân loại + đánh giá điều kiện + rule format + state model đều đúng tinh thần PRD và **giữ lại được**. Nhưng code dừng lại **trước lớp contract-conformance**: nó là một thư viện Python `process(text, state) -> {intent, action, response}` với ~50% policy được mã hoá, **không phải** một service HTTP nói đúng protocol v1 mà agent chờ.

**Khối lượng thực tế của "nối guardrail + agent": ~25–40 ngày-người** (solo + AI assist), chia 4 pha ở §6. Không phải "2 ngày viết adapter".

**1 bug an toàn phải sửa ngay:** guardrail hiện **fail-OPEN** — intent không khớp rule nào → trả `ALLOW` (`vf_guardrails/src/guardrail.py:60-63`). Vi phạm BR-02, BR-09, FR-07. Xem §4.

---

## 2. Contract v1 — agent chờ gì từ guardrail

Agent gọi guardrail qua **HTTP JSON POST**, 4 endpoint:

| Endpoint | Khi nào | Input | Output |
|---|---|---|---|
| `POST /v1/evaluate/action` | intent state-changing | `ActionProposal` | `GuardrailDecision` (+ `permit` nếu ALLOW) hoặc `GuardrailError` |
| `POST /v1/evaluate/query` | intent hỏi state/knowledge | payload query | `GuardrailDecision` (ANSWER/UNKNOWN) |
| `POST /v1/confirmations/confirm` | user xác nhận sau CONFIRM | `{request_id, confirmation_id, session_id}` | `GuardrailDecision` mới (đánh giá lại trên state mới) |
| `POST /v1/monitor/evaluate` | tick monitor cho active action | `{request_id, active_action_id, intent}` | `GuardrailDecision` |

### `GuardrailDecision` — field bắt buộc (contract.py `_DECISION_REQUIRED`)

```
contract_version="1.0.0", kind="decision", request_id, proposal_id,
intent, outcome, rule_id, state_version (int), policy_checksum ("sha256:<64hex>"),
reason_code, relevant_state (object)
```
Optional: `answer`, `confirmation`, `permit`. **Field lạ = fail closed.**

### `ActionPermit` — CHỈ khi `outcome == ALLOW`, và bắt buộc khi ALLOW

```
permit_id, proposal_digest ("sha256:…"), intent, rule_id, state_version,
policy_checksum, issued_at (tz-aware ISO), expires_at (> issued_at), single_use=true
```
- `proposal_digest` = sha256 của projection `{arguments, contract_version, proposal_id, session_id, source_turn_id, tool}` (đã sort key, `client.py` verify permit bound đúng proposal).
- `intent / rule_id / state_version / policy_checksum` trong permit **phải bằng** giá trị trong decision.
- Outcome ≠ ALLOW mà kèm `permit` → `PERMIT_FORBIDDEN`, fail closed.

### `GuardrailError` (kind="error")

```
contract_version, kind="error", request_id, error{code, message, retryable, details?}
```
Typed error là **lỗi tích hợp, không phải outcome policy**. Không được chứa `permit`.

### Semantics agent enforce sẵn (không cần guardrail lo, nhưng guardrail phải tương thích)

- ALLOW không permit hợp lệ → agent tự chặn thực thi.
- `proposal_id` trả về ≠ `proposal_id` gửi đi → `PROPOSAL_MISMATCH`.
- timeout/không kết nối → `GUARDRAIL_UNAVAILABLE`, `execution_allowed=False`.

---

## 3. Hiện trạng `vf_guardrails/` — đo được

| Thành phần | File | Ghi nhận |
|---|---|---|
| T1 intent classifier | `src/intent_classifier.py` `_classify_level1` | Aho-Corasick, khớp **action + entity đồng thời**, score theo tổng độ dài keyword. Hợp lý. |
| T2 semantic fallback | `src/intent_classifier.py` `_classify_level2` | PhoBERT ONNX + cosine similarity với anchor, threshold 0.65. **Hiện tắt** — `model/model.onnx` không có trong folder (chỉ có tokenizer). Cần `setup_model.py`. Không có margin-check vs nhãn nhì. |
| T3 SLM fallback | — | **Không có.** |
| Constraint engine | `src/safety_engine.py` | `evaluate_condition` hỗ trợ `== != > < >= <=` + logic AND/OR, **không dùng `eval()`** ✅. Index rule theo `intent` ✅. |
| Rule store | `config/safety_rules.yaml` | **52 policy** (ids R002…R102, khớp đánh số workbook). Actions: 24 `BLOCK_UNAVAILABLE`, 15 `BLOCK_UNSAFE`, 12 `CONFIRM`, 1 `NOT_VOICE_ACTIONABLE`. **0 ALLOW, 0 ANSWER, 0 monitor, không có field `check_mode`.** |
| Keyword catalog | `config/intent_keywords.json` | `{intent: {actions[], entities[], anchors[]}}`. |
| Vehicle state | `car_status.py` | pydantic `VehicleState`, ~45 field (gear/speed/doors/seats/ADAS/lights/modes/env). **Không versioned.** |
| Decision result | `src/models.py` `GuardrailResult` | `{intent, action, response, reason, latency_ms}`. |
| Orchestrator | `src/guardrail.py` | `process()`: T1→T2 → `SafetyEngine.evaluate` → **fallthrough ALLOW** + **hardcode câu trả lời ANSWER** cho ~6 intent. |
| Agent (của Long) | `src/agent.py` (66KB) | Agent riêng, 67 OpenAI tool, mock-mode. **Trùng vai với `vivi-agent/`.** |
| Sim | `app_sim.py` (CLI), `simulator/` (`index.html`+`app.js`+`css`) | Sim tự chứa, gắn với model 2-outcome đơn giản. |
| Benchmark | `tests/run_benchmark.py`, `data/vinfast_test_data.json` (3MB) | Harness đo latency. |
| Model | `model/` (tokenizer PhoBERT, ~2MB, **thiếu `.onnx`**) | |

**Không tồn tại:** HTTP server, ActionProposal ingestion, permit, `policy_checksum`, `state_version`, typed-error envelope, Monitor Engine, trace/event theo PRD §16, policy loader đọc `.xlsx` thật.

---

## 4. Bug an toàn — fail-OPEN (ưu tiên P0, sửa trước mọi thứ)

`vf_guardrails/src/guardrail.py`:

```python
else:
    action = "ALLOW"
    reason = "NO_SAFETY_VIOLATION"
    response = "Yêu cầu hợp lệ và an toàn. Đang gửi lệnh thực thi..."
```

Khi (a) intent không phân loại được, hoặc (b) không rule nào match, engine trả **ALLOW**.

- **PRD BR-02:** "Lỗi phân loại không được đánh giá constraint hoặc gọi actuator."
- **PRD BR-09:** "Policy invalid làm toàn hệ thống fail closed."
- **PRD FR-07:** "Không match hoặc multi-match ngoài thiết kế phải **fail closed** và không gọi actuator."
- **PRD §7.3:** text không map được vào catalog = lỗi phân loại → yêu cầu diễn đạt lại, **không phải outcome**.

**Đúng phải là:**
- Không phân loại được intent → `GuardrailError` (vd `code=INTENT_UNRESOLVED`), KHÔNG đánh giá constraint.
- Phân loại được nhưng 0 rule gate match → cần quyết định thiết kế: outcome mặc định theo workbook (nhiều intent action có rule `ALLOW` tường minh trong `Driver_constraints.xlsx`) — **phải mã hoá rule ALLOW đó**, không suy ra ALLOW bằng fallthrough.
- Multi-match mâu thuẫn → `GuardrailError` / `UNKNOWN`, fail closed.

---

## 5. Bảng giữ / sửa / xây mới / quyết định

### 5.1. GIỮ — Long làm đúng, tái dùng gần như trực tiếp

| # | Thành phần | Điều kiện tái dùng | Effort điều chỉnh |
|---|---|---|---|
| K1 | T1 Aho-Corasick (`_classify_level1`) + `intent_keywords.json` | Bổ sung keyword để phủ đủ 53 intent; giữ scoring | 1–2 d |
| K2 | T2 PhoBERT ONNX semantic approach (`_classify_level2`, `_get_embedding`) | Wire model (`setup_model.py`), thêm **margin vs nhãn nhì** (FR-03), calib threshold trên golden dataset | 1–2 d |
| K3 | `SafetyEngine.evaluate_condition` (operator an toàn, no-`eval`) | Giữ nguyên; thêm operator nếu workbook cần (`in`, range) | 0.5 d |
| K4 | YAML rule schema (`intent` + `target_state` + `logic` + `enforcement`) | Giữ làm **policy format**; bổ sung `check_mode`, `rule_id` chuẩn, `outcome` đủ 7 loại | — (dùng ở B7) |
| ~~K5~~ | ~~Nội dung 52 rule đã mã hoá~~ | **BỎ** — Phase 0 diff ([PHASE0_RULE_DIFF.md](PHASE0_RULE_DIFF.md)): chỉ phủ 47/109, 6 rule trỏ sai intent, sai enum case / field name / boolean structure. Không dịch tay nữa — parse `condition` canonical trực tiếp | → B7 |
| K6 | `VehicleState` field catalog (~45 field) | Giữ danh mục field; bọc trong lớp versioned (xem F4) | 0.5 d |
| K7 | `tests/run_benchmark.py` + `data/vinfast_test_data.json` | Harness đo latency §15 PRD | 0.5 d |

### 5.2. SỬA — cần thiết nhưng sai/thiếu

| # | Thành phần | Vấn đề | Hướng sửa | Effort |
|---|---|---|---|---|
| F1 | `guardrail.py` fallthrough → ALLOW | **Fail-open** (§4) | Fail-closed: classification error → typed error; 0-match → outcome theo workbook, không suy ra | 1–2 d |
| F2 | `GuardrailResult` model | Thiếu `rule_id`, `state_version`, `policy_checksum`, `reason_code`, `relevant_state`, `permit`; field `response` sai ranh giới | Thay bằng `GuardrailDecision` đúng contract (§2) | 1–2 d |
| F3 | Guardrail tự sinh `response` (kể cả hardcode ANSWER) | PRD §5.2: agent sinh text hướng người dùng. Contract cho phép field `answer` optional → cần **chốt ranh giới** (xem D2) | Bỏ text sinh sẵn; nếu giữ ANSWER thì trả `answer={grounded, facts}` như `examples.json` | 1–2 d |
| F4 | `VehicleState` không versioned | FR-05: mỗi mutation tăng `state_version`, mỗi decision dùng immutable snapshot | Bọc store versioned (tham chiếu `vivi-agent` `vehicle/` VehicleStateMachine để đồng bộ schema) | 1–2 d |
| F5 | T2 threshold-only | FR-03 yêu cầu confidence **và** margin | Thêm margin check + tính khoảng cách nhãn 1–2 | (gộp K2) |
| F6 | `safety_rules.yaml` thiếu ~57 rule + monitor + ALLOW/ANSWER | Chỉ có 52/109, toàn rule "chặn" | Mã hoá nốt từ workbook (xem B7) | (xem B7) |

### 5.3. XÂY MỚI — không tồn tại, phải xây đúng contract

| # | Thành phần | Yêu cầu nguồn | Effort |
|---|---|---|---|
| B1 | HTTP service 4 endpoint (`/v1/evaluate/action`, `/v1/evaluate/query`, `/v1/confirmations/confirm`, `/v1/monitor/evaluate`) | contract, `client.py` | 3–5 d |
| B2 | Ingest `ActionProposal` + `validate_action_proposal` + tính `proposal_digest` | `contract.py` | 1 d |
| B3 | Phát hành `ActionPermit` (digest-bound, `single_use`, `issued_at`/`expires_at`, khớp field decision) | `contract.py` `_PERMIT_REQUIRED` | 2–3 d |
| B4 | `policy_checksum` — hash tất định workbook đã nạp (`sha256:<64hex>`) | FR-06, User story policy owner | 0.5 d |
| B5 | Typed-error envelope (`kind=error`), phân biệt rõ với outcome | contract, BR-01/BR-02 | 1 d |
| B6 | Monitor Engine + monitor session lifecycle + **5 monitor rule** | FR-13, PRD §7.1 (104 gate / 5 monitor) | 3–4 d |
| B7 | Policy loader đọc `Driver_constraints.xlsx` thật, validate 109 rule / 53 intent / 104 gate / 5 monitor, **fail closed nếu thiếu**; sinh YAML từ workbook (hoặc dùng thẳng) | FR-06, AC 1/12 | 2–4 d |
| B8 | Trace/event theo PRD §16 (`command_received` … `command_completed`, mỗi event có `session_id`, `request_id`, checksum) | FR-14 | 2–3 d |
| B9 | T3 SLM fallback (whitelist 53 intent, không tạo action/outcome) — **có thể hoãn (P1-ish)** | FR-03, G-08 | 2–3 d |
| B10 | E2E harness thật: thay `MockGuardrail` bằng service thật trong test agent | AC 5–19 | 2–3 d |

### 5.4. BỎ — hoặc chỉ giữ làm tham khảo

| # | Thành phần | Lý do |
|---|---|---|
| X1 | `vf_guardrails/src/agent.py` (66KB) | `vivi-agent/` (934 test, contract-driven) là canonical. Giữ tạm để tham khảo tool catalog rồi xoá. |
| X2 | `vf_guardrails/app_sim.py` | Thay bằng tích hợp thật |
| X3 | Hardcode câu ANSWER trong `guardrail.py` | Sai ranh giới (F3) |
| X4 | `golden_dataset_review.json` / `.csv` trong `vf_guardrails/` | Trùng `golden-dataset/driver-constraints/` của Đạt — không import |

### 5.5. QUYẾT ĐỊNH — ✅ đã chốt 2026-09-06 (PM: Đạt)

| # | Quyết định | ✅ Chốt |
|---|---|---|
| D1 | Layout repo | **2 service tách**, nói chuyện qua HTTP contract v1. `vf_guardrails/` = service guardrail, `vivi-agent/` = service agent, `docs/guardrail-integration/` = seam. Runner boot cả hai |
| D2 | Ai sinh text ANSWER | **Guardrail trả `answer={grounded, facts}` (facts có cấu trúc)**, agent verbalize thành câu tiếng Việt |
| D3 | Source of truth 109 rule | **`golden-dataset/.../data/rules.json`** (== `Driver_constraints.xlsx#Constraints`, cột `condition` biểu thức) là gốc. **Parse `condition` trực tiếp** (tái dùng `derive_witness_states.py`), retire `safety_rules.yaml`. Bằng chứng: [PHASE0_RULE_DIFF.md](PHASE0_RULE_DIFF.md) |
| D4 | VehicleState schema | **1 schema chung** trong wire contract, cả 2 bên import. Gốc = `car_status.py` (~45 field) + `state_version`. Chuẩn hoá enum (`'day'/'night'` lowercase theo workbook) và field name (`speed` không `speed_kmh`) |
| D5 | T3 SLM | **Hoãn** — sau khi T1/T2 đạt metric trên golden dataset |
| D6 | UI | **Hoãn sang pha 2** (scale + UI) |

---

## 6. Trình tự (ĐÃ ĐẢO — chốt 2026-09-06)

> **Vì sao đảo:** `golden-dataset/.../tools/derive_witness_states.py` đã chứa closed
> AST evaluator hoàn chỉnh (`evaluate_condition`, `normalize`, `MANUAL_REWRITES` cho 7
> rule `=`-typo / pseudo-function), chạy sạch **109/109** condition, có test. Phần tôi
> ước lượng nặng nhất & rủi ro nhất của Pha 1 cũ (parser condition) → đã xong. Kéo
> decision core + metrics lên trước; HTTP/contract layer (rủi ro thấp, đã đặc tả kỹ,
> agent đã có `MockGuardrail`) đẩy xuống sau. Estimate tổng: **~15–22 dev-days** (từ 25–40).

### Pha 0 — Chốt & chuẩn bị ✅ XONG
- Import `vf_guardrails/`, chốt D1–D6, rule diff ([PHASE0_RULE_DIFF.md](PHASE0_RULE_DIFF.md)), sửa bug fail-open (`a167eaa`).

### Pha 1′ — Decision core + metrics golden dataset (≈1 tuần) ← ĐANG LÀM
Mục tiêu: **guardrail phân giải + đánh giá đúng 109 rule, đo được trên 2.313 dòng golden dataset.** Zero phụ thuộc agent/HTTP/UI.
1. `vf_guardrails/policy/conditions.py` — tách `evaluate_condition` + `normalize` + `MANUAL_REWRITES` từ `derive_witness_states.py`, giữ **byte-identical** (kể cả rewrite `speed<3→==0` — đây là quyết định PM đã chốt ở PLAN.md §6a, golden dataset gán nhãn theo nó nên runtime phải theo).
2. `vf_guardrails/policy/rules.py` — nạp 109 rule từ `Driver_constraints(Constraints).csv` (đã trong repo, == `rules.json`), index `(intent, check_mode)`, fail-closed nếu ≠ 109 / ≠ 53 intent / 104 gate / 5 monitor.
3. `vf_guardrails/policy/state.py` — `VehicleState` canonical: field name + enum theo `derive_witness_states.DOMAINS` (21 biến, lowercase `day`/`night`, `speed` không `speed_kmh`, `door_lock_state` không `doors_locked`). D4.
4. `vf_guardrails/policy/engine.py` — `PolicyEngine.evaluate(intent, state, phase)` → `Decision(outcome, rule_id, reason_code, relevant_state)`; đúng 1 outcome; **fail closed** 0-match / multi-match / parse-error / unknown-var.
5. Test oracle: với mỗi rule, các witness state trong `rule_witness_states.json` phải cho ra outcome của rule đó.
6. T1 (`intent_keywords.json` mở rộng 53 intent) + T2 (`setup_model.py` nạp PhoBERT) + margin check.
7. Harness `vf_guardrails/evals/run_golden.py` — chạy classifier + PolicyEngine trên 2.313 dòng → confusion matrix, accuracy / F1 / FN-rate / FP-rate theo intent & outcome, latency p50/p95/p99 (T1 ≤5ms, T2 ≤20ms, gate ≤5ms p99 — §15 PRD).
8. `docs/guardrail-integration/METRICS_PHASE1.md`.
- **Gate:** 109/109 rule reproduce đúng outcome trên witness states; báo cáo metrics per-intent trên golden dataset; xoá `safety_rules.yaml` + `safety_engine.py` cũ.

### Pha 2′ — Contract / HTTP layer (≈1–1.5 tuần)
- Wrap engine đã chứng minh vào service HTTP v1: B1 (4 endpoint), B2 (proposal + digest), B3 (permit ALLOW), B4 (`policy_checksum`), B5 (typed error), F2 (GuardrailDecision), F4 (`state_version` + immutable snapshot).
- CONFIRM lifecycle `/v1/confirmations/confirm` + re-evaluate (FR-10, AC 14–16).
- B6 Monitor Engine + 5 monitor rule (FR-13, AC-19).
- D2 ANSWER: guardrail trả `answer={grounded, facts}`.
- B10: swap `MockGuardrail` → service thật trong E2E agent.
- **Gate:** 7/7 outcome routing xanh; confirmation state-machine xanh; AC-9 + AC-10 qua HTTP thật.

### Pha 3′ — End-to-end demo + polish (≈3–5 d)
- `run_both.py` boot agent + guardrail; demo `text → guardrail → agent → mock actuator → trace` cho ALLOW/BLOCK/CONFIRM.
- B8 trace đầy đủ §16. T3 SLM nếu còn thời gian (D5).
- **Gate:** Definition of Done phần guardrail+agent (PRD §20, trừ UI).

> Pha "scale (multi-agent/multi-vehicle) + UI" — brainstorm riêng sau Pha 3′.

---

## 7. Rủi ro

| Rủi ro | Ảnh hưởng | Giảm thiểu |
|---|---|---|
| `safety_rules.yaml` (52) lệch nội dung với workbook/`rules.json` | Metrics Pha 3 dựa trên policy sai | Diff từng dòng ở Pha 0; B7 sinh YAML từ `.xlsx` |
| Schema `VehicleState` 2 bên lệch tên field | Rule không đọc được state → fail-closed nhầm | D4 chốt schema chung, đặt trong wire contract |
| T2 model không hội tụ / thiếu `.onnx` | T2 chết, dồn hết về T1 (kém recall paraphrase) | K2 sớm ở Pha 2; có đường T1-only tất định làm fallback |
| Solo dev, 25–40 ngày-người | Trượt lịch nếu ước lượng lạc quan | Gate theo pha; walking skeleton (Pha 1) cho tín hiệu sớm |
| `agent.py` của Long bị vô tình dùng làm spine | Chia đôi effort agent | Xoá X1 ngay sau khi tham khảo xong |

---

## 8. Việc đã làm trong branch này

- [x] Git: về main, pull, xoá nhánh phụ local + **remote** (`datalexander/agent-completion`, `vivi-agent/scafford` — đã merge hết), tạo `feat/guardrail-agent-integration`. Repo = `main` + branch làm việc.
- [x] Viết audit này.
- [x] Import `vf_guardrails/` vào repo (commit `cbfea6f`; loại `.git/`/`.idea/`/cache/`golden_dataset_review.*`; gitignore `model/` + fixture 3MB).
- [x] **PM chốt D1–D6** (§5.5).
- [x] **Pha 0 — rule diff:** [PHASE0_RULE_DIFF.md](PHASE0_RULE_DIFF.md). Kết luận: `safety_rules.yaml` bỏ, parse `condition` canonical trực tiếp.
- [x] **Pha 0 — sửa bug fail-open** `vf_guardrails/src/guardrail.py` (commit riêng).
- [x] **Pha 1′ — decision core** (`vf_guardrails/policy/`: `conditions.py`, `rules.py`, `state.py`, `engine.py`) + oracle test + harness `evals/run_golden.py`.
  → **[METRICS_PHASE1.md](METRICS_PHASE1.md): constraint engine 2313/2313 = 100% trên golden dataset, latency p99 0.14 ms.** 15 test pass.
- [x] **Pha 1′ — T1 baseline** ([METRICS_PHASE1_CLASSIFIER.md](METRICS_PHASE1_CLASSIFIER.md)): T1-only 58.1% intent / 59% pipeline / 37% UNKNOWN. T2 (PhoBERT) chặn môi trường (`E:\anaconda3` hỏng `torch`/`onnxruntime`).
- [x] **Pha 1′ — chốt phương pháp đo**: CV trên golden pool bị leakage (pool sinh theo khuôn, nhiều câu gần trùng). Cần **frozen independent test set** trước khi đo T2 → [FROZEN_TESTSET_SPEC.md](FROZEN_TESTSET_SPEC.md) (bản hướng dẫn tự chứa cho agent gen, ~530 dòng). T1 58.1% vẫn hợp lệ (T1 không train).
- [x] **Pha 1′ XONG** — frozen test set (v2), T2 quyết định (TF-IDF 88.3% > PhoBERT 79.2% — `T2_DECISION.md`), `classifier/` + `guardrail.py` facade mới, xoá `safety_engine.py`/`safety_rules.yaml`/`agent.py`/`app_sim.py`/`car_status.py`. E2E p99 2.4 ms, 19 test.
- [ ] **Pha 2′** ← TIẾP THEO — HTTP service v1, permit, CONFIRM lifecycle, Monitor wiring, swap MockGuardrail. Xem §6 "Pha 2′".

### Việc git còn treo
- Worktree cũ `.claude/worktrees/great-yalow-d7b474` (detached HEAD) — dọn nếu không dùng (`git worktree remove`).
- `reports/` + `reports.zip` (báo cáo Sprint 2) — PM chọn để **untracked, quyết sau**.
