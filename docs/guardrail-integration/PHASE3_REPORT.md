# Pha 3′ — Báo cáo hoàn thành

**Kỳ:** 2026-09-07 · **Nhánh:** `feat/guardrail-phase3` (từ `guardrail-integration`)
· **Trạng thái: HOÀN THÀNH cả 3 tăng (3′.1–3′.3).**

> Điểm vào session mới: `STATUS.md`. Pha trước: `PHASE1_REPORT.md`, `PHASE2_REPORT.md`.

---

## 1. Mục tiêu

Đóng nốt phần guardrail+agent cho DoD (PRD §20, trừ UI):
- **P2-D3** — đường `ANSWER` hoạt động end-to-end (fact-shaping),
- **PRD §16 / FR-14** — trace/event guardrail đầy đủ,
- demo `run_both.py` + báo cáo phủ tự động + latency đo được + README nêu rõ MÔ PHỎNG.

## 2. Đã giao

| Hạng mục | File | Ghi chú |
|---|---|---|
| **Fact-shaping ANSWER/UNKNOWN** | `service/answer_facts.py` | 5 state query → `{"<field>": <value>}`; `explain_feature` → `{"feature", "kb_has_feature"}`. `request_params_for()` cấp `kb_has_feature` cho engine (14 feature workbook = 14 target `explain_vehicle_feature` trong bảng map). |
| Action + query path gắn `answer` | `service/app.py`, `service/envelope.py` | `ANSWER` → `answer={grounded:true, facts}`; `UNKNOWN` → `answer={grounded:false, facts}`. `query_decision_envelope` chuẩn schema (bỏ dict tạm). |
| **Trace guardrail** | `service/trace.py` | `TraceRecorder`: `guardrail_started / tool_mapped / mapping_failed / constraint_evaluated / confirmation_requested / confirmation_resolved / monitor_evaluated / guardrail_completed / guardrail_error`. Mỗi event có `session_id, request_id, timestamp, stage, policy_checksum`, `stage_ms` (thời gian từ event trước) và `since_start_ms`; `guardrail_completed` thêm `end_to_end_ms`. Ring buffer 256 request + JSONL sink tùy chọn. Không log secret/prompt. |
| Trace read-back | `service/http.py` | `GET /v1/trace/{request_id}`. |
| CLI | `service/__main__.py` | `--trace-file trace.jsonl`. |
| **Demo end-to-end** | `run_both.py` | 5 kịch bản ALLOW / BLOCK_UNSAFE / CONFIRM(+confirm) / ANSWER / MONITOR qua `AgentOrchestrator` + `GuardrailClientAdapter(REAL)` thật; in trace guardrail đầy đủ + latency; banner **MÔ PHỎNG** đầu & cuối. |
| **Báo cáo phủ** | `evals/run_coverage.py` → `COVERAGE_REPORT.md` | 109/109 rule · 53/53 intent · 104 gate · 5 monitor · 53/53 intent reachable qua tool_map · 7/7 outcome có trong workbook · 5 monitor rule liệt kê. Exit≠0 nếu lệch. |
| **Latency HTTP** | `evals/run_benchmark.py` | Thêm round-trip p50/p95/p99 cho `/v1/evaluate/action|query`, `/v1/monitor/evaluate`. |
| Docs | `vf_guardrails/service/README.md` (mới), `README.md`, `STATUS.md`, `PHASE2_PLAN.md` | |

## 3. Bằng chứng

**Test:** `vf_guardrails` **79/79** (61 + `test_answer_3p1.py` 8 + `test_trace_3p2.py` 10) ·
`vivi-agent` **941/941** (+1 e2e: query intent chạy qua orchestrator thật → `completed`,
actuator 0×). Không sửa logic agent.

**Latency (máy dev, warm):**

| | p50 | p95 | p99 | target |
|---|---|---|---|---|
| PolicyEngine gate | 0.03 | 0.08 | **0.11 ms** | ≤5 ms (PRD §15) |
| `Guardrail.process` e2e | 1.95 | 2.44 | **2.82 ms** | ≤25 ms |
| `POST /v1/evaluate/action` (HTTP loopback) | 1.16 | 17.0 | **19.0 ms** | ≤25 ms |
| `POST /v1/monitor/evaluate` | 1.25 | 17.1 | **18.2 ms** | — |

`COVERAGE_REPORT.md`: ✅ ĐẠT (109/109, 53/53, 104/5, 7/7, 0 intent unreachable).

**Demo `run_both.py`** — mỗi outcome kèm trace guardrail:
`ALLOW R001` · `BLOCK_UNSAFE R002` · `CONFIRM R091` → confirm → `ALLOW R090` (+permit) ·
`ANSWER R099` · monitor `BLOCK_UNSAFE R048` (autopark active @ 40 km/h).

## 4. DoD (PRD §20) — trạng thái

| Mục | Trạng thái |
|---|---|
| PRD & kiến trúc đồng bộ | ✅ (không đổi contract) |
| giao diện chạy bằng text | ⏸ UI hoãn (D6); `run_both.py` + orchestrator nhận text |
| báo cáo tự động 53/53 intent + 109/109 rule | ✅ `run_coverage.py` / `COVERAGE_REPORT.md` |
| mọi outcome có hướng xử lý | ✅ 7/7 routing (action + query) |
| `BLOCK_*` / `UNKNOWN` không gọi actuator | ✅ (orchestrator + `test_e2e_real_guardrail.py`) |
| confirm đánh giá lại + có hạn + dùng 1 lần | ✅ (`test_confirm_2p2.py`, AC 14–16) |
| 5 monitor rule đều có kịch bản | ✅ (`test_monitor_2p3.py`) |
| nhật ký hiển thị đủ luồng đầu-cuối | ✅ `TraceRecorder` + `/v1/trace/{id}` + `run_both.py` |
| latency đo trên máy mục tiêu | ✅ `run_benchmark.py` (chạy lại trên máy demo trước khi trình bày) |
| README + kịch bản demo nêu rõ mô phỏng | ✅ banner + `service/README.md` + `README.md` |
| không tuyên bố xe thật / OEM | ✅ |

## 5. Nợ còn lại (ngoài phạm vi guardrail+agent)

- **UI** (D6) — Pha scale.
- **T3 SLM** (D5) — hoãn; đường tất định đã đủ cho demo.
- `turnon_LKA` — agent map, workbook chưa có rule → typed error (PM chấp nhận; chờ Long).
- `/v1/evaluate/query` chưa nằm trên đường orchestrator hiện tại (orchestrator route query qua `/v1/evaluate/action`); endpoint giữ contract-complete cho đường Gateway sau này.
- Golden dataset `reviewed=0/2313`; `_STATE_DEFAULTS` là giả định Pha 1.

## 6. Git

Nhánh `feat/guardrail-phase3` (từ `guardrail-integration` a8b3a7f). Sau khi PM duyệt →
PR → `guardrail-integration`, rồi `guardrail-integration` → `main` (bước cuối của dự án phần này).
