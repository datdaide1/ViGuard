# Pha 2′ — Báo cáo hoàn thành

**Kỳ:** 2026-09-07 · **Nhánh:** `feat/guardrail-phase2-http`
· **Trạng thái: HOÀN THÀNH cả 4 tăng (2′.1–2′.4).** Sang Pha 3′.

> Chi tiết kế hoạch + trạng thái từng tăng: `PHASE2_PLAN.md`. Điểm vào session mới: `STATUS.md`.

---

## 1. Mục tiêu Pha 2′

Bọc decision core của Pha 1′ trong **HTTP contract layer v1** cho đường
**CON-01** (agent authorization): agent LLM chọn `tool`+`arguments` → gửi
`ActionProposal` (không kèm intent/text) → Guardrail map lại độc lập
`(tool,action,target,value)→intent`, đánh giá policy, trả `GuardrailDecision` +
`ActionPermit` digest-bound. Cộng với vòng đời **CONFIRM** và đường **Monitor**.

TF-IDF của Pha 1 KHÔNG nằm trên đường này (nó phục vụ Gateway/Simulator —
Pha 3′). `PolicyEngine` dùng chung, không sửa.

## 2. Đã giao

| Hạng mục | File | Ghi chú |
|---|---|---|
| **Bảng tool→intent** | `vf_guardrails/service/tool_map.py` | 79 dòng explicit của agent, **copy nguyên** (D1: không import chéo). Lookup exact `(tool,action,target,value)`, miss → `UNSUPPORTED_TOOL_MAPPING` (fail-closed). |
| **Vehicle State Mock** | `service/state_store.py` | `VehicleStateStore`: `state_version` int đơn điệu, snapshot bất biến mỗi request, 4 preset (`parked_safe`/`driving`/`rainy`/`low_battery`) (P2-D2). |
| **Wire envelope** | `service/envelope.py` | Copy `proposal_digest` + `validate_action_proposal` từ contract v1 (byte-for-byte). Build `GuardrailDecision`/`GuardrailError`/`ActionPermit`/`confirmation` **đúng schema**. Permit CHỈ trên `ALLOW`, digest-bound, `single_use`, TTL 2 s, field `==` decision. |
| **CONFIRM store** | `service/confirmations.py` | `PendingConfirmationStore`: id `confirm-<hex>` single-use, TTL 30 s, giữ nguyên proposal + `origin_rule_id`. `consume()` nguyên tử. |
| **Active-action registry** | `service/active_actions.py` | `ActiveActionRegistry` + `MONITORED_INTENTS` (5, assert khớp workbook + agent manifest). |
| **Request core** | `service/app.py` | `GuardrailService.handle(path,payload) → (status,body)` — transport-free, test trực tiếp. 4 route. |
| **HTTP shell** | `service/http.py` + `__main__.py` | stdlib `ThreadingHTTPServer` (P2-D4), `GET /healthz`, `py -3 -m vf_guardrails.service` (P2-D5). |
| **Demo 2 service** | `run_both.py` (repo root) | Boot service (thread) + `AgentOrchestrator` (adapter REAL), 3 kịch bản ALLOW/BLOCK/CONFIRM. |
| **Test** | `vf_guardrails/tests/` + 1 file vivi-agent | `test_tool_map.py` (11), `test_service_http.py` (~15), `test_gate_2p1.py` (5), `test_confirm_2p2.py` (6), `test_monitor_2p3.py` (8), `conftest.py` (bootstrap cross-repo); `vivi-agent/.../test_e2e_real_guardrail.py` (3). |

## 3. Route + hành vi

| Route | Vào | Ra | Fail-closed |
|---|---|---|---|
| `POST /v1/evaluate/action` | `ActionProposal` | `ALLOW`+permit / `BLOCK_*` / `CONFIRM`+`confirmation` / `ANSWER` | version→409 · malformed→400 · unsupported-mapping / engine fail-closed→422 (typed error) |
| `POST /v1/confirmations/confirm` | `{confirmation_id, session_id, request_id}` | re-eval **state mới**: `ALLOW`+permit mới (hoặc `CONFIRM` cùng rule) / `BLOCK_*` / `CONFIRM` rule khác→pending mới | unknown/expired/replay → `CONFIRMATION_NOT_ACTIVE` (409) · session ≠ session gốc → `CONFIRMATION_SESSION_MISMATCH` (403, **không tiêu token**) |
| `POST /v1/monitor/evaluate` | `{active_action_id, intent, vehicle_state?}` | no-trigger / monitor-`ALLOW` → `ALLOW`+permit tổng hợp ("keep running") · monitor block → outcome+`rule_id` (no permit) | non-monitored → `NOT_A_MONITORED_INTENT` · `vehicle_state` sai kiểu/field lạ → `INVALID_VEHICLE_STATE` (400) · engine lỗi bất ngờ → `ENGINE_EVAL_ERROR` (422, fail-closed) → agent **fail-safe stop** |
| `POST /v1/evaluate/query` | `{tool, arguments}` | 🟡 skeleton: `ANSWER`{grounded, facts thô từ `relevant_state`} | not-a-query-intent → 422 |

## 4. Bằng chứng (gate)

| Gate | Kịch bản | Kết quả |
|---|---|---|
| **AC-9** (2′.1) | `open_door`, parked → qua `GuardrailClientAdapter(REAL)` | `ALLOW` + permit, `proposal_digest` khớp **byte-for-byte** `examples.json` (`sha256:19059c4c…`) |
| **AC-10** (2′.1) | `open_door`, gear D speed 50 | `BLOCK_UNSAFE` R002, **không permit** |
| **AC-14** (2′.2) | CONFIRM decision | không permit; `confirmation` single-use |
| **AC-15** (2′.2) | `open_sunroof` rain+40 → CONFIRM; speed→120 trước confirm | confirm → `BLOCK_UNSAFE` R051, không permit |
| **AC-16** (2′.2) | confirm 2 lần | lần 1 `ALLOW`+permit; lần 2 → `CONFIRMATION_NOT_ACTIVE` |
| CNF e2e (2′.2) | `ConfirmationManager` + executor thật | actuator gọi **đúng 1 lần**, chỉ sau `ALLOW` mới |
| **AC-19** (2′.3) | `activate_hda`, hands-off 20 s | `BLOCK_UNSAFE` **R073** + rule_id |
| Monitor (2′.3) | pin thấp → camp-mode; no-trigger; monitor-`ALLOW` R070; agent-supplied state | đúng hết |
| **E2E swap** (2′.4) | `AgentOrchestrator` thật ↔ service in-process, không mock | ALLOW (actuator 1×, state_version 1) · BLOCK (R002, 0×) · CONFIRM (`needs_confirmation`, 0×) |

**Test:** 61/61 `vf_guardrails` · **940/940 `vivi-agent` (không regress, không sửa logic agent)** · 43 test contract vivi-agent xanh với service thật.

## 5. Quyết định thực thi (khớp P2-D1..D5)

| # | Thực thi |
|---|---|
| P2-D1 | Copy `DEFAULT_MAPPING_RULES` (79 dòng) + `test_tool_map.py` so **từng dòng** với `vivi_agent.tools.mapping.mapper` (skip nếu vivi-agent vắng). Lệch → đỏ. |
| P2-D2 | Guardrail sở hữu state; `state_version` +1 mỗi mutation; snapshot bất biến. Monitor path chấp nhận `vehicle_state` của agent nếu có. |
| P2-D3 | `ANSWER={grounded, facts}` — mới ở mức thô trên query path (fact-shaping đầy đủ → Pha 3′). |
| P2-D4 | `http.server` stdlib, zero dep. |
| P2-D5 | 1 process `127.0.0.1:<port>`, `py -3 -m vf_guardrails.service`; `run_both.py` boot cả hai. |

## 6. Phát hiện / nợ (chuyển Pha 3′ hoặc PM)

1. **`turnon_LKA`** — có dòng map (agent) nhưng KHÔNG có rule workbook (chỉ `turnoff_LKA`). Service → typed error `INTENT_NOT_IN_CATALOG` (422), **không bao giờ ALLOW**. *PM 2026-09-07: chấp nhận tạm; phần của Long có thể thêm intent workbook/agent chưa có, bổ sung sau.*
2. **Monitor "keep running"** phải mượn `outcome=ALLOW` + permit tổng hợp — contract v1 không có tín hiệu monitor-continue riêng (agent adapter coi mọi outcome ≠ `ALLOW` là stop). Ghi nhận cho contract v1.1 nếu có.
3. **`/v1/evaluate/query`** mới skeleton — P2-D3 fact-shaping đầy đủ để Pha 3′ (đường query không nằm trên gate Pha 2′ nào).
4. **Trace/event stream (PRD §16)** — `AgentEventPipeline` có sẵn agent-side, wiring đầy đủ để Pha 3′.
5. `_STATE_DEFAULTS` / preset `rainy`,`low_battery` vẫn là giả định Pha 1.

## 7. Git

Nhánh `feat/guardrail-phase2-http`: 2′.1 = commit `1069fac`; 2′.2–2′.4 = commit kế tiếp.
**Local, chưa push, chưa PR.** Kế: PR → `guardrail-integration` (cùng PR #48 hoặc gộp — PM quyết).
