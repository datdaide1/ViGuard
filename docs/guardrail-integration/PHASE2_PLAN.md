# Pha 2′ — Plan: HTTP contract layer

**Nhánh:** `feat/guardrail-phase2-http` (từ tip Pha 1′) · PR sẽ nhắm `guardrail-integration`.

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

### 2′.1 — Contract layer + walking skeleton (~3–5 d)
- `vf_guardrails/service/tool_map.py` — `(tool, action, target, value) → intent` + conformance test vs agent.
- `vf_guardrails/service/state_store.py` — `VehicleStateStore`: state + `state_version`, snapshot bất biến, preset (parked-safe / driving / rainy / low-battery).
- `vf_guardrails/service/envelope.py` — build `GuardrailDecision` / `GuardrailError` đúng schema; `proposal_digest` (sha256 projection); `ActionPermit` (digest-bound, single_use, issued_at/expires_at, field == decision).
- `vf_guardrails/service/http.py` — `POST /v1/evaluate/action` + `/v1/evaluate/query`, stdlib `http.server`, contract-version check → 409, malformed → typed error.
- **Gate:** `vivi-agent` `GuardrailClientAdapter(REAL)` gọi service thật, AC-9 (`open_door` parked → ALLOW + permit hợp lệ) + AC-10 (đang chạy → BLOCK_UNSAFE, không permit) xanh qua HTTP.

### 2′.2 — CONFIRM lifecycle (~2–3 d)
- `PendingConfirmationStore` — id single-use, expiry, gắn 1 proposal.
- `CONFIRM` decision kèm `confirmation={confirmation_id, proposal_id, expires_at, single_use}`.
- `POST /v1/confirmations/confirm` — đọc state MỚI, re-evaluate gate policy, trả decision mới (ALLOW+permit hoặc block mới). Confirm cũ/hết hạn/dùng lại → `CONFIRMATION_NOT_ACTIVE`.
- **Gate:** AC 14–16 (chưa confirm → 0 actuator; state xấu đi trước confirm → block; confirm 2 lần → lần 2 từ chối).

### 2′.3 — Monitor engine (~3–4 d)
- 5 monitor rule đã nạp sẵn trong `policy/` (`check_mode="monitor"`). `POST /v1/monitor/evaluate` → `engine.evaluate(intent, state, check_mode="monitor")`.
- `NO_MONITOR_TRIGGER` (không phải outcome) vs block → decision.
- Active-action registry phía guardrail (theo dõi action đang chạy).
- **Gate:** AC-19 (monitored action active, monitor rule trả block → decision block + rule_id).

### 2′.4 — E2E swap + demo (~2–3 d)
- Test trong `vivi-agent/` thay `MockGuardrail` bằng service thật (spawn subprocess hoặc in-process `ThreadingHTTPServer`).
- `run_both.py` — boot guardrail service + agent, chạy 3 kịch bản (ALLOW/BLOCK/CONFIRM) end-to-end.
- Trace/event theo PRD §16.
- **Gate:** Definition of Done phần guardrail+agent (PRD §20, trừ UI).

## 3. Không đụng tới ở Pha 2′

- `classifier/` (TF-IDF) — đường Gateway, để Pha 3′/UI.
- `policy/` — reuse nguyên, không sửa (engine đã 100%).
- `vivi-agent/` core — chỉ thêm 1 test dùng `REAL` provider, không sửa logic agent.

## 4. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Bảng `tool→intent` lệch với agent | Conformance test so từng dòng, chạy trong CI |
| `proposal_digest` không khớp (serialization) | Dùng đúng spec: sorted keys, no whitespace, `ensure_ascii=False`, reject NaN. Test với `examples.json` của agent |
| Contract v1 có field/nghĩa tôi hiểu sai | Chạy `vivi-agent` contract test (`test_consumer_contract`) với service thật — nó validate fail-closed |
| State schema đường monitor (agent gửi snapshot) khác đường action (guardrail sở hữu) | Xử lý 2 nhánh riêng trong `envelope`/`http` |
