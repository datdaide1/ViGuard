# MAP-01 — Xây mapping nền tảng cho vertical slice

**Trạng thái:** review
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/tools/mapping  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục MAP-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** TOOL-01

**Mô tả:** Xây deterministic mapper từ tool call sang canonical intent; sprint này khóa đường `control_access(open, driver_door) → open_door` và kiến trúc mở rộng cho toàn catalog.

**Công việc chi tiết:**

- Canonicalize tool arguments.
- Map exact combination về intent.
- Tính proposal digest trên canonical payload.
- Chặn ambiguous/unsupported combination.
- Ghi source tool và canonical intent vào event.
- Thiết kế startup mapping validator.

**Đầu ra:** Tool Mapper và `open_door` mapping.

**Acceptance criteria:**

- Valid call map đúng một intent.
- Unsupported target/action không tự fallback sang intent gần nhất.
- Cùng canonical proposal luôn có cùng digest.

