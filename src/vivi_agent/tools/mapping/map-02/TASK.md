# MAP-02 — Hoàn thiện tool-to-intent mapping 53/53

**Trạng thái:** review  
**Sprint:** sprint-2  
**Code area:** src/vivi_agent/tools/mapping  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục MAP-02)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** MAP-01, CAT-01

**Mô tả:** Mở rộng Tool Mapper để mọi intent hiện tại reachable qua ít nhất một valid domain tool call và không mapping nào ambiguous.

**Công việc chi tiết:**

- Mapping access, lights, cabin, modes, gear, ADAS, UI và queries.
- Parameter normalization và enums.
- Exact source intent casing trong proposal/trace.
- Unsupported combination rejection.
- Startup mapping coverage validation.
- Mapping report theo missing/duplicate/ambiguous ID.
- Đánh giá seam `map_call(ValidatedToolCall, proposal_metadata=...)` khi đã có
  consumer thực tế từ Orchestrator/Model Provider. Chỉ thêm API này nếu loại bỏ
  được validation lặp lại mà không cho phép bypass `ActionProposal` trust
  boundary hoặc proposal-digest binding.

**Đầu ra:** Full Tool Mapper và coverage report.

**Acceptance criteria:**

- 53/53 intent reachable.
- Mỗi valid combination map đúng một intent.
- Không dynamics intent ngoài catalog xuất hiện trong model tool registry.
- Nếu triển khai `map_call`, phải có consumer test chứng minh proposal metadata
  vẫn được validate và digest vẫn bind đúng canonical proposal; không tạo API
  chỉ để dự phòng khi chưa có consumer.

