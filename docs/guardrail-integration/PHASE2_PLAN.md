# Pha 2′ — Plan: HTTP contract layer

**Nhánh:** `feat/guardrail-phase2-http` (từ tip Pha 1′) · PR sẽ nhắm `guardrail-integration`.

> **TRẠNG THÁI 2026-09-07: Pha 2′ XONG cả 4 tăng (2′.1–2′.4).** `vf_guardrails/service/`
> = HTTP contract layer đầy đủ (action + confirm + monitor + query-skeleton). 45 test mới
> (42 vf_guardrails + 3 e2e vivi-agent); **61/61 vf_guardrails, 940/940 vivi-agent**, không
> regress. Demo: `py -3 run_both.py`. Chi tiết dưới đây theo từng tăng.
> *(2026-09-07, sau review Sourcery: thêm session-binding cho `/v1/confirmations/confirm` +
> validate kiểu `vehicle_state` trên monitor path + guard fail-closed quanh engine — 3 test.)*

---

## 0. Phát hiện quan trọng khi đọc lại contract của agent

**Có 2 đường phân giải intent, không phải 1:**

| Đường | Consumer | Cách ra intent | Dùng gì từ Pha 1 |
|---|---|---|---|
| **Gateway / Simulator** (PRD "text → Guardrail Gateway") | Web UI pilot: user gõ text | **TF-IDF classifier** (`classifier/`) trên text | `Guardrail.process(text, state)` ✅ đã xong |
| **Agent authorization** (CON-01, cái Pha 2′ làm) | `vivi-agent/` — LLM của agent đã chọn tool | **Map tất định `(tool, action, target, value) → intent`** | `PolicyEngine` (reuse), KHÔNG dùng TF-IDF |

Trên đường CON-01: agent LLM chọn `tool` + `arguments` có cấu trúc → agent tự map
→ gửi `ActionProposal` (chỉ `tool` + `arguments`, **không** kèm intent/text) →
**Guardrail phải map lại độc lập** `tool+arguments → intent` (cùng bảng với agent),
đánh giá policy, trả `intent` + `outcome` + `permit`. Agent kiểm tra
`decision.intent == agent_mapped_intent` (`_validate_decision_correlation`).

Bảng map của agent: `vivi-agent/.../tools/mapping/mapper.py::DEFAULT_MAPPING_RULES`
(78 tổ hợp → 53 intent). Manifest 53 intent của agent **khớp đúng** 53 intent
workbook (đã verify).

→ **Pha 2′ = xây HTTP service cho đường CON-01.** TF-IDF của Pha 1 không nằm trên
đường này; nó phục vụ Gateway/Simulator (Pha 3′ hoặc phần UI sau).

## 1. Quyết định — ✅ ĐÃ CHỐT (PM: Đạt, 2026-09-07)

| # | Chốt |
|---|---|
| **P2-D1** | Bảng `tool→intent`: **copy `DEFAULT_MAPPING_RULES` sang `vf_guardrails/` + conformance test** so từng dòng với bản agent (D1: 2 service tách, không import chéo). Lệch → test đỏ. |
| **P2-D2** | Guardrail **sở hữu** Vehicle State Mock; `state_version` int tăng mỗi mutation; snapshot bất biến mỗi request. Agent KHÔNG gửi state trên đường action. *(Đường monitor: agent gửi `vehicle_state` snapshot — nhánh riêng.)* |
| **P2-D3** | `ANSWER`: guardrail đọc state → `answer={grounded, facts}` theo intent; agent verbalize. |
| **P2-D4** | HTTP = **`http.server` stdlib** (như `mock_server.py`). Zero dep. Không FastAPI/Flask. |
| **P2-D5** | 1 process `127.0.0.1:<port>`, `python -m vf_guardrails.service`. `run_both.py` (Pha 3′) boot cả hai. |

## 2. Việc — chia 4 tăng

### 2′.1 — Contract layer + walking skeleton (~3–5 d) — ✅ XONG (2026-09-07)
- `vf_guardrails/service/tool_map.py` — `(tool, action, target, value) → intent` + conformance test vs agent.
- `vf_guardrails/service/state_store.py` — `VehicleStateStore`: state + `state_version`, snapshot bất biến, preset (parked-safe / driving / rainy / low-battery).
- `vf_guardrails/service/envelope.py` — build `GuardrailDecision` / `GuardrailError` đúng schema; `proposal_digest` (sha256 projection); `ActionPermit` (digest-bound, single_use, issued_at/expires_at, field == decision).
- `vf_guardrails/service/http.py` — `POST /v1/evaluate/action` + `/v1/evaluate/query`, stdlib `http.server`, contract-version check → 409, malformed → typed error.
- **Gate:** `vivi-agent` `GuardrailClientAdapter(REAL)` gọi service thật, AC-9 (`open_door` parked → ALLOW + permit hợp lệ) + AC-10 (đang chạy → BLOCK_UNSAFE, không permit) xanh qua HTTP.

**Đã ship:**
- `vf_guardrails/service/` (7 file): `tool_map.py` (79 dòng explicit của agent, copy nguyên),
  `state_store.py`, `envelope.py` (copy `proposal_digest` + `validate_action_proposal`
  từ contract v1), `app.py` (`GuardrailService.handle` — transport-free core),
  `http.py` (stdlib `ThreadingHTTPServer` + `/healthz`), `__main__.py`
  (`py -3 -m vf_guardrails.service`, P2-D5). `vf_guardrails/__init__.py` mới.
- Test: `test_tool_map.py` (11 — conformance row-by-row vs agent + coverage 53 intent),
  `test_service_http.py` (14 — routing/409/400/422/404/healthz/state_store),
  `test_gate_2p1.py` (5 — **AC-9 + AC-10 qua `GuardrailClientAdapter(REAL)` thật**).
  `tests/conftest.py` mới (bootstrap cross-repo: path vivi-agent + shim `src`).
- `proposal_digest` khớp byte-for-byte giá trị pin trong `examples.json`
  (`sha256:19059c4c…`). Mọi decision qua `validate_guardrail_result` của agent.
- **Status codes:** 200 decision · 409 version mismatch / `CONFIRMATION_NOT_ACTIVE` ·
  403 `CONFIRMATION_SESSION_MISMATCH` · 400 malformed proposal / `INVALID_VEHICLE_STATE` ·
  422 fail-closed (unsupported mapping / engine fail-closed) · 404 route.

**Nợ / phát hiện còn mở sau Pha 2′:**
- `turnon_LKA`: có dòng map (agent) nhưng KHÔNG có rule workbook → service trả typed
  error `INTENT_NOT_IN_CATALOG` (422), không bao giờ ALLOW. **PM 2026-09-07: chấp nhận
  tạm — phần của Long có thể thêm intent mà workbook/agent chưa có, bổ sung sau.**
- `/v1/evaluate/query`: vẫn skeleton (route + validate + ANSWER thô từ `relevant_state`).
  Fact-shaping đầy đủ theo P2-D3 → Pha 3′ (đường query chưa nằm trên gate nào của Pha 2′).
- Monitor "keep running" phải mượn `outcome=ALLOW`+permit tổng hợp vì contract v1 không có
  tín hiệu monitor-continue riêng. Ghi nhận cho contract v1.1 (nếu có).
- Trace/event stream (PRD §16) chưa wire đầy đủ → Pha 3′.
- `_STATE_DEFAULTS` / preset `rainy`,`low_battery` là giả định, chưa map vào rule cụ thể.

### 2′.2 — CONFIRM lifecycle — ✅ XONG (2026-09-07)
- `service/confirmations.py` — `PendingConfirmationStore` (id single-use `confirm-<hex>`, TTL 30 s khớp examples.json, giữ nguyên proposal + `origin_rule_id`).
- Action path: engine `CONFIRM` → tạo pending + `decision.confirmation={confirmation_id, proposal_id, expires_at, single_use}` (đúng schema, KHÔNG kèm `prompt`), không permit.
- `POST /v1/confirmations/confirm` — `consume()` nguyên tử → đọc **snapshot state mới** → re-eval gate:
  `ALLOW` hoặc `CONFIRM` cùng `origin_rule_id` (PRD §3.2.7 dòng "match cùng rule → cho phép 1 lần") → `ALLOW` + permit mới; `CONFIRM` rule khác → pending mới; `BLOCK_*` → block, không permit.
  Unknown / hết hạn / replay → `CONFIRMATION_NOT_ACTIVE` (409). Session ≠ session của proposal gốc
  → `CONFIRMATION_SESSION_MISMATCH` (403), **không tiêu token** (session đúng vẫn confirm được).
- **Gate ✅:** `test_confirm_2p2.py` (7 test) qua `GuardrailClientAdapter(REAL)` + `ConfirmationManager` thật:
  AC-14 (CONFIRM không permit), AC-15 (`open_sunroof` rain→speed 120 giữa chừng → BLOCK_UNSAFE R051), AC-16 (confirm lần 2 → `CONFIRMATION_NOT_ACTIVE`), manager end-to-end (actuator đúng 1 lần, chỉ sau ALLOW mới).

### 2′.3 — Monitor engine — ✅ XONG (2026-09-07)
- `service/active_actions.py` — `ActiveActionRegistry` + `MONITORED_INTENTS` (5, assert khớp workbook + agent manifest trong test). Đăng ký khi action-path `ALLOW` cho intent monitored; xoá khi monitor block.
- `POST /v1/monitor/evaluate` → `engine.evaluate(intent, state, check_mode="monitor")`. State: `vehicle_state` trong payload (agent gửi snapshot) nếu có — **validate kiểu từng field** (`validate_wire_vehicle_state`), sai → `INVALID_VEHICLE_STATE` (400); không có thì store snapshot. Engine bọc `_evaluate()` fail-closed (`ENGINE_EVAL_ERROR`) phòng lỗi bất ngờ.
- Map ra wire: `NO_MONITOR_TRIGGER` (outcome None) **hoặc** monitor `ALLOW` (R070) → wire `ALLOW` + permit tổng hợp (bind `monitor_request_digest`) = "cứ chạy tiếp" (adapter agent coi mọi thứ ≠ ALLOW là stop). Monitor block → outcome block + `rule_id`, không permit. Fail-closed → typed error → agent fail-safe stop.
- **Gate ✅:** `test_monitor_2p3.py` (10 test): AC-19 (`activate_hda`, hands-off 20 s → BLOCK_UNSAFE R073), camp-mode pin thấp → BLOCK_UNAVAILABLE R033, no-trigger/monitor-ALLOW → "keep running", non-monitored → `NOT_A_MONITORED_INTENT`, agent-supplied `vehicle_state` được tôn trọng, sai kiểu/field lạ → `INVALID_VEHICLE_STATE`.

### 2′.4 — E2E swap + demo — ✅ XONG (2026-09-07)
- `vivi-agent/tests/e2e/vertical_slice/e2e-01/test_e2e_real_guardrail.py` (3 test, +1 file test — trong hạn mức "1 test REAL"): E2E-01 với `env.guardrail` = `GuardrailClientAdapter(REAL)` → service in-process. ALLOW (actuator 1×, state_version 1), BLOCK_UNSAFE (R002, actuator 0×), CONFIRM (`needs_confirmation`, actuator 0×). Digest binding + decision/intent correlation + CONFIRM handshake của orchestrator thật đều pass.
- `run_both.py` (repo root) — boot service (thread) + `AgentOrchestrator` (adapter REAL), chạy 3 kịch bản ALLOW/BLOCK/CONFIRM, in turn status + rule_id + actuator hits.
- Trace/event PRD §16: `AgentEventPipeline` có sẵn agent-side; wiring stream đầy đủ hoãn sang Pha 3′ (polish).
- **Gate:** DoD guardrail+agent (PRD §20, trừ UI) — 61/61 vf_guardrails, 940/940 vivi-agent, không regress.

## 3. Không đụng tới ở Pha 2′

- `classifier/` (TF-IDF) — đường Gateway, để Pha 3′/UI.
- `policy/` — reuse nguyên, không sửa (engine đã 100%).
- `vivi-agent/` core — không sửa 1 dòng logic agent. Chỉ thêm **1 file test mới**
  (`test_e2e_real_guardrail.py`, 3 case) dùng `GuardrailProvider.REAL`. 940 test cũ nguyên vẹn.

## 4. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Bảng `tool→intent` lệch với agent | Conformance test so từng dòng, chạy trong CI |
| `proposal_digest` không khớp (serialization) | Dùng đúng spec: sorted keys, no whitespace, `ensure_ascii=False`, reject NaN. Test với `examples.json` của agent |
| Contract v1 có field/nghĩa tôi hiểu sai | Chạy `vivi-agent` contract test (`test_consumer_contract`) với service thật — nó validate fail-closed |
| State schema đường monitor (agent gửi snapshot) khác đường action (guardrail sở hữu) | Xử lý 2 nhánh riêng trong `envelope`/`http` |
