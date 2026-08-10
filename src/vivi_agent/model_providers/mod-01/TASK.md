# MOD-01 — Xây ModelProviderAdapter cho OpenAI và Gemini

**Trạng thái:** review
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/model_providers  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục MOD-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Implementation evidence:**

- `src/vivi_agent/model_providers/contracts.py`
- `src/vivi_agent/model_providers/adapters.py`
- `src/vivi_agent/model_providers/selection.py`
- `src/vivi_agent/model_providers/README.md`
- `tests/model_providers/test_model_providers.py`

**Validation:** Offline unit suite covers both provider formats, configuration,
readiness, bounded failover, turn pinning, typed failures, and event metadata.
Live provider credential validation remains an integration/release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** TOOL-01

**Mô tả:** Tạo abstraction provider-neutral và hai adapter API: OpenAI dùng mặc định `gpt-5-mini`, Gemini dùng mặc định `gemini-3.5-flash-lite`. Cả hai phục vụ tool selection và response verbalization có kiểm soát, cùng trả một internal contract. Model không được kết nối Guardrail/Vehicle handlers trực tiếp.

**Công việc chi tiết:**

- Định nghĩa internal interfaces `propose_tool()` và `compose_response()`.
- OpenAI adapter dùng native strict function calling.
- Gemini adapter dùng native function calling/structured output.
- Cấu hình `AGENT_MODEL_PROVIDER=auto|openai|gemini`.
- Cấu hình `AGENT_MODEL_PROVIDER_PRIORITY`, mặc định `openai,gemini`.
- Đọc `OPENAI_API_KEY` và `GEMINI_API_KEY` chỉ ở backend.
- Cho phép đổi exact model ID qua cấu hình, không hardcode trong business logic.
- Ở `auto`, chọn provider đầu tiên có key theo priority.
- Không có key thì Agent readiness fail rõ nguyên nhân.
- Không gọi race hai provider cho cùng turn.
- Chỉ failover tối đa một lần nếu provider đầu chưa tạo valid ActionProposal.
- Sau valid proposal, Guardrail authorization hoặc execution, pin turn vào provider ban đầu.
- Bounded context, output, timeout và maximum one tool call.
- Normalize provider-specific response về shared `ModelActionProposal`.
- Health/readiness, provider/model metadata và typed API errors.
- Deterministic error response khi toàn bộ providers unavailable.
- Không lưu hidden reasoning/provider thought payload.

**Đầu ra:** ModelProviderAdapter, OpenAI adapter, Gemini adapter và provider-selection module.

**Acceptance criteria:**

- Adapter chỉ output tool proposal, clarification hoặc response draft.
- Timeout/malformed output tạo zero Guardrail-authorized action.
- Cùng internal contract được dùng cho cả OpenAI và Gemini.
- `auto` chọn đúng provider dựa trên key và priority.
- Không có key làm readiness fail; không silently dùng mock model.
- Provider, model ID, config checksum và latency xuất hiện trong event metadata.
- Failover không được xảy ra sau khi đã có valid proposal hoặc side-effect lifecycle bắt đầu.

