# P1-STREAM — Streaming token/progress nâng cao

**Trạng thái:** completed
**Sprint:** backlog  
**Code area:** backlog/p1  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục P1-STREAM)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Mức:** P1

**Điều kiện bắt đầu:** P0 event ordering đã ổn định

Task này thuộc backlog có thể cắt và không nằm trong release gate P0 hiện tại.

## Phạm vi đã triển khai

- `turn_progress` public event với phase/progress đơn điệu và terminal duy nhất.
- `response_chunk` sau normalize/redaction với index liên tục, stream correlation và terminal duy nhất.
- Session-scoped replay + live subscription, không rò event giữa sessions.
- Subscriber lỗi không làm hỏng append-only event pipeline.
- `MessageEndpoint` phát progress/chunk cho client 1.1; client 1.0 tiếp tục chạy không stream.
- Callback chạy ngoài registry lock; queue, chunk và session store có giới hạn cứng.
- Event store validation tăng tuyến tính theo số event, không quét lại toàn stream sau mỗi chunk.
- Không stream raw provider output, hidden reasoning, policy trace hoặc permit.

## Acceptance criteria

- Progress/chunk events tuân thủ Agent-UI closed schema và global session sequence.
- Reconnect từ `since_sequence` không duplicate chunk; session subscription replay rồi follow đúng thứ tự.
- Phase/progress regression, chunk gap/replay, stream switch và event sau terminal đều fail closed.
- Response cuối hiện tại vẫn là source of truth; streaming là public UX projection, không thực thi action.
- Agent-UI 1.0 vẫn tương thích cho payload cũ; chỉ event streaming yêu cầu 1.1.

