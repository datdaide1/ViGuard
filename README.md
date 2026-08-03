# Guardrail

Guardrail là hệ thống phân loại ý định và ra quyết định theo trạng thái xe cho AI Agent trên xe VinFast. Pipeline có hai bước nối tiếp: (1) nhận một câu nói của tài xế (văn bản, đã qua nhận dạng giọng nói) và trả về một ý định (intent) đã chuẩn hoá, bằng cách rẻ và nhanh nhất có thể; (2) khớp ý định đó với một trạng thái xe mô phỏng và một bộ luật, trả về kết quả cho phép/từ chối/hỏi lại, minh hoạ bằng một actuator giả lập.

> **Trạng thái:** Dự án đang ở giai đoạn đặc tả và chuẩn bị pilot; repository hiện chứa tài liệu nghiên cứu, PRD, đề xuất kiến trúc và dữ liệu catalog, chưa có ứng dụng chạy được.

## Bài toán

Đưa mọi câu nói thẳng vào một mô hình ngôn ngữ (LLM) để hiểu ý định thì chậm (0.2–2s), tốn (phần lớn lệnh lặp lại đúng khuôn mẫu), và dễ bị lợi dụng (prompt injection — lượt nào không cần gọi LLM thì kiểu tấn công này không có cửa để len vào).

Danh mục yêu cầu của một trợ lý trên xe là hữu hạn và đóng: 55 intent, 53 trong phạm vi pilot. Đây không phải bài toán hiểu ngôn ngữ mở, mà là bài toán phân loại — hệ thống phân loại trước bằng phương pháp tất định và rẻ, chỉ gọi LLM khi thật sự cần. Nhưng phân loại đúng ý định thôi chưa đủ: "mở cửa xe" hợp lệ về ngôn ngữ nhưng nguy hiểm ở tốc độ cao — nên pilot còn phải chứng minh được bước quyết định dựa trên trạng thái xe, không dựa trên câu nói.

## Phạm vi pilot

Hai thành phần nối tiếp nhau:

- **Guardrail** — nhận văn bản, trả về một intent label thuộc 53 intent trong catalog (hoặc `UNKNOWN`), kèm tầng đã xử lý (`T1`/`T2`/`T3`) và latency. Guardrail không đọc trạng thái xe, không tự quyết định cho phép/chặn.
- **Decision Demo** — với intent thuộc lớp hành động, khớp `(intent, trạng thái xe mô phỏng)` với một bộ luật, trả về một trong 5 mức kết quả (`ALLOW`/`BLOCK_UNSAFE`/`BLOCK_UNAVAILABLE`/`CONFIRM`/`NOT_VOICE_ACTIONABLE`), rồi gọi một actuator giả lập nếu kết quả là cho phép.

Trạng thái xe trong pilot là **mô phỏng, nhập/chỉnh tay** — không đọc từ xe thật. Cơ chế cưỡng chế "không thể đi vòng" cấp production (capability object, token chống dùng lại, giám sát liên tục, tích hợp xe thật) nằm ngoài phạm vi 6 tuần — xem lý do ở `specs/architecture/Architecture_Guardrail_FINAL.md` §5.9.

## Kiến trúc định hướng

**Guardrail — pipeline phân loại 3 tầng, tất định trước, LLM là phương án dự phòng:**

- **Bộ lọc dấu hiệu buộc từ chối** — 6 nhóm (phủ định, câu ghép, nghi vấn, điều kiện/thì tương lai, đại từ mơ hồ, đa khớp), chạy trước mọi tầng.
- **T1 — Khớp mẫu tất định:** so trực tiếp với mẫu câu soạn tay cho 53 intent.
- **T2 — Nearest-neighbor text similarity:** so với tập neo paraphrase cấp intent, chỉ ship nếu đo được ngưỡng giữ accuracy 100%.
- **T3 — Input Guard + LLM:** phương án dự phòng khi hai tầng trên không xử lý được; Input Guard chỉ chạy ở tầng này.

**Decision Demo — quyết định theo trạng thái xe mô phỏng:**

- **Vehicle State Mock** — cấu trúc trong bộ nhớ, chỉnh tay qua giao diện demo.
- **Decision Function (PDP-lite)** — khớp intent × state với bộ luật đọc từ file, trả một trong 5 mức kết quả.
- **Mock Actuator** — đích thực thi giả lập, chỉ được gọi khi kết quả là `ALLOW`.

Nguyên tắc bất biến: T2 không bao giờ được suy ra ngoài một intent label; Decision Function luôn dùng giá trị thật trong Vehicle State Mock, không bao giờ dùng giá trị nêu trong câu nói.

## Cấu trúc repository

```text
.
├── brief/                             # Brief bài toán ban đầu
├── research/                          # Nghiên cứu và phân tích cạnh tranh
├── specs/
│   ├── prd/
│   │   ├── PRD_Guardrail_FINAL.md     # PRD chính thức — scope Guardrail
│   │   └── old/                       # Các bản PRD ViGuard cũ, phạm vi rộng hơn
│   └── architecture/
│       ├── Architecture_Guardrail_FINAL.md   # ADR chính thức — kiến trúc Guardrail
│       ├── Spec_T2_TFIDF_vs_PhoBERT.md       # Kế hoạch spike T2, đang hoạt động
│       └── old/                       # Các bản ADR/Proposal ViGuard cũ, phạm vi rộng hơn
├── Driver_intent_FINAL_v2.xlsx        # Catalog intent (sheet `Catalog` dùng cho Guardrail)
├── AGENTS.md                          # Quy tắc cộng tác trong workspace
└── CLAUDE.md                          # Chỉ dẫn tương thích cho AI assistant
```

Tài liệu trung tâm: [`specs/prd/PRD_Guardrail_FINAL.md`](specs/prd/PRD_Guardrail_FINAL.md) (sản phẩm) và [`specs/architecture/Architecture_Guardrail_FINAL.md`](specs/architecture/Architecture_Guardrail_FINAL.md) (kỹ thuật).

Một vài file trong `specs/prd/` và `specs/architecture/` (ngoài `old/`) vẫn đang chờ được archive thủ công vào `old/` — chúng đã được đánh dấu **Superseded** ở đầu file, không dùng để tham chiếu scope hiện tại.

## Bắt đầu

Repository chưa có runtime để cài đặt hoặc khởi chạy. Để nắm dự án:

1. Đọc [`brief/brief.md`](brief/brief.md) để hiểu bài toán guardrail ban đầu.
2. Đọc [`specs/prd/PRD_Guardrail_FINAL.md`](specs/prd/PRD_Guardrail_FINAL.md) để xem phạm vi, user stories, requirements và acceptance criteria.
3. Đọc [`specs/architecture/Architecture_Guardrail_FINAL.md`](specs/architecture/Architecture_Guardrail_FINAL.md) để xem quyết định kiến trúc T1/T2/T3, lộ trình theo sprint.
4. Tham khảo `Driver_intent_FINAL_v2.xlsx` (sheet `Catalog`) cho danh mục 55 intent của pilot.
5. Xem thư mục `research/` để biết bối cảnh kỹ thuật và cạnh tranh (lưu ý: phần lớn nội dung ở đây phục vụ lớp policy/PDP, hiện ngoài phạm vi pilot).

## Chỉ số đánh giá dự kiến

- độ chính xác đường nhanh (T1/T2) trên tập test giữ lại — ngưỡng 100%;
- độ phủ đường nhanh — đo, không đánh đổi lấy độ chính xác;
- tỷ lệ chặn prompt injection (Input Guard, T3);
- tỷ lệ từ chối oan (câu ý rõ nhưng bị đẩy xuống tầng chậm hơn);
- latency theo từng tầng, đo ở p99 và max.

Chi tiết success metrics, acceptance criteria và benchmark plan được duy trì trong PRD và Architecture doc.
