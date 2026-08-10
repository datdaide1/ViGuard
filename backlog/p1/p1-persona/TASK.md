# P1-PERSONA — Persona verbalization nâng cao

**Trạng thái:** completed
**Sprint:** backlog
**Code area:** `src/vivi_agent/responses`
**Nguồn:** `specs/agent/VIVI_IMPLEMENTATION_PLAN.md` (mục P1-PERSONA)

**Mức:** P1
**Phụ thuộc:** RSP-01

## Mô tả

Bổ sung các profile giọng điệu tiếng Việt cho ViVi trên lớp Grounded Response
Composer. Persona chỉ là lớp trình bày: không được thay đổi facts, policy reason,
execution result hoặc biến một failure/block thành success.

## Công việc chi tiết

- Profile bất biến với tone `neutral`, `warm`, `formal`.
- Cách xưng hô nằm trong enum đóng (`bạn`, `anh`, `chị`), không nhận prompt tùy ý.
- Fallback deterministic được áp persona trước giới hạn độ dài cuối cùng.
- Model verbalization hợp lệ được giữ nguyên; persona không tạo đường vòng để sửa
  output provider hoặc policy outcome.
- Giọng `neutral` là mặc định để giữ tương thích với RSP-01.

## Acceptance criteria

- Mỗi cấu hình tạo cùng một output cho cùng input.
- Persona không sửa nội dung grounded và không được áp lên model verbalization.
- Không có text tùy ý từ người dùng được dùng làm system/persona instruction.
- Giới hạn độ dài vẫn được thực thi sau khi áp persona.
- Unit tests của response composer và regression suite đều pass.

## Evidence

- `src/vivi_agent/responses/persona.py`
- `src/vivi_agent/responses/composer.py`
- `tests/responses/test_response_composer.py`
