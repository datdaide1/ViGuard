# ViGuard

ViGuard là lớp uỷ quyền hành động thời gian thực cho AI Agent trên xe. Hệ thống kiểm tra một hành động có an toàn trong trạng thái hiện tại của xe hay không, ra quyết định theo policy và cưỡng chế quyết định trước khi lệnh được gửi tới bộ chấp hành.

> **Trạng thái:** Dự án đang ở giai đoạn đặc tả và chuẩn bị pilot; repository hiện chứa tài liệu nghiên cứu, PRD và dữ liệu thiết kế, chưa có ứng dụng chạy được.

## Bài toán

Các guardrail ngôn ngữ có thể phát hiện prompt injection, jailbreak hoặc nội dung độc hại, nhưng không đủ để xác định một hành động vật lý có an toàn hay không. Ví dụ, yêu cầu “mở cửa xe” hợp lệ về ngôn ngữ nhưng nguy hiểm khi xe đang chạy.

ViGuard bổ sung một đường kiểm soát dựa trên:

- intent đã được chuẩn hoá;
- trạng thái xe tại thời điểm xử lý;
- policy có thể truy vết nguồn và phiên bản;
- điểm cưỡng chế duy nhất trước actuator, không cho phép gọi vòng.

## Phạm vi pilot

Pilot tập trung vào ba nhóm yêu cầu:

1. **Hành động:** đánh giá intent theo trạng thái xe và policy.
2. **Hỏi trạng thái:** trả lời từ dữ liệu xe hiện tại, không suy đoán.
3. **Hỏi kiến thức:** trả lời từ knowledge base và đối chiếu với trạng thái xe khi cần.

Đối với hành động, hệ thống trả một trong năm kết quả:

- `BLOCK_UNSAFE`
- `BLOCK_UNAVAILABLE`
- `CONFIRM`
- `ALLOW`
- `NOT_VOICE_ACTIONABLE`

## Kiến trúc định hướng

ViGuard tách các trách nhiệm theo mô hình uỷ quyền:

- **PIP (Policy Information Point):** cung cấp trạng thái xe đáng tin cậy.
- **PDP (Policy Decision Point):** khớp intent và state với policy để ra quyết định.
- **PEP (Policy Enforcement Point):** xác thực và cưỡng chế quyết định trước actuator.
- **PAP (Policy Administration Point):** quản lý policy và tham số cấu hình.

Các nguyên tắc chính là fail-safe khi thiếu dữ liệu, kiểm tra lại state trước khi thực thi, chống dùng lại authorization token, giám sát liên tục với hành động kéo dài và ghi log có thể truy vết tới từng rule.

## Cấu trúc repository

```text
.
├── brief/                       # Brief bài toán ban đầu
├── research/                    # Nghiên cứu và phân tích cạnh tranh
├── specs/
│   └── prd/                     # Product Requirements Document
├── Driver_intent_PILOT_v1.1.xlsx
├── AGENTS.md                    # Quy tắc cộng tác trong workspace
└── CLAUDE.md                    # Chỉ dẫn tương thích cho AI assistant
```

Tài liệu trung tâm: [`specs/prd/PRD_ViGuard_v4.md`](specs/prd/PRD_ViGuard_v4.md).

## Bắt đầu

Repository chưa có runtime để cài đặt hoặc khởi chạy. Để nắm dự án:

1. Đọc [`brief/brief.md`](brief/brief.md) để hiểu bài toán guardrail ban đầu.
2. Đọc PRD để xem phạm vi, user stories, requirements và acceptance criteria.
3. Tham khảo `Driver_intent_PILOT_v1.1.xlsx` cho catalog intent của pilot.
4. Xem thư mục `research/` để biết bối cảnh kỹ thuật và cạnh tranh.

## Chỉ số đánh giá dự kiến

Đánh giá không chỉ dựa trên độ chính xác mô hình. Các nhóm chỉ số chính gồm:

- tỷ lệ quyết định đúng và tỷ lệ chặn nhầm;
- khả năng từ chối hành động không an toàn và ngăn gọi vòng qua PEP;
- grounding/faithfulness cho câu hỏi trạng thái và kiến thức;
- latency theo từng đường xử lý;
- độ phủ policy, khả năng truy vết và tính đầy đủ của audit log.

Chi tiết benchmark, test strategy và ngưỡng thành công được duy trì trong PRD.

## Quy ước version control

- Mọi thư mục tên `old` ở bất kỳ cấp nào đều không được đưa vào Git.
- `ViGuard_Tracker.xlsx` và file khóa Excel được tạm thời loại khỏi Git.
- Chỉ cập nhật tài liệu đang hoạt động; lịch sử nháp được giữ cục bộ trong các thư mục `old`.

