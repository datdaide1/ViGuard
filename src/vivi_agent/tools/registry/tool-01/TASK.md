# TOOL-01 — Định nghĩa Domain Tool Registry

**Trạng thái:** planned  
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/tools/registry  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục TOOL-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** CAT-01

**Mô tả:** Định nghĩa tool set nhỏ, có schema đóng để model từ OpenAI hoặc Gemini lựa chọn. Agent không expose 47 hàm rời hoặc arbitrary tool names.

**Công việc chi tiết:**

- Định nghĩa các tool domain: access, light, cabin, drive mode, transmission, driver assistance, special mode, UI, state query và feature explanation.
- JSON Schema cho action, target, value và enum.
- Chặn additional properties.
- Định nghĩa structured clarification khi thiếu parameter.
- Tạo tool registry checksum/version.
- Unit tests cho valid/invalid arguments.

**Đầu ra:** Domain Tool Registry và JSON Schemas.

**Acceptance criteria:**

- Model chỉ nhìn thấy registered tools.
- Invalid tool/argument bị chặn trước Guardrail call.
- Tool arguments không chấp nhận state, outcome, rule hoặc permit do model cung cấp.

