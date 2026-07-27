# Hệ thống AI Guardrails bảo vệ Agent/LLM

## 1. Bài toán

Khi đưa LLM/Agent vào môi trường production, hệ thống đối mặt với vô số rủi ro bảo mật và chất lượng đầu ra. Người dùng hoặc dữ liệu đầu vào có thể chứa mã độc nhằm vô hiệu hóa các rào cản an toàn của LLM (jailbreak, prompt injection), trích xuất trái phép hệ thống prompt (system prompt leak), hoặc truy vấn các từ khóa bị cấm. Ngoài ra, LLM có thể tạo ra thông tin sai lệch (hallucination) trong các lĩnh vực chuyên sâu.

Bài toán đặt ra là cần xây dựng một lớp bảo vệ (guardrails) bao bọc xung quanh LLM/Agent, kiểm soát chặt chẽ cả đầu vào và đầu ra để đảm bảo hệ thống hoạt động an toàn, đúng phạm vi và chính xác về mặt tri thức.

## 2. Thách thức

| Thách thức | Mô tả |
|---|---|
| Độ trễ vs. Độ chính xác | Việc thêm các lớp kiểm tra sẽ làm tăng thời gian phản hồi, gây ảnh hưởng đến trải nghiệm người dùng. Cần cân bằng giữa việc lọc kỹ và phản hồi nhanh. |
| Tỷ lệ dương tính giả (False Positives) | Nếu bộ lọc quá nghiêm ngặt, hệ thống sẽ chặn nhầm các câu hỏi hợp lệ, làm hỏng UX. |
| Sự tinh vi của tấn công | Các mẫu tấn công ngày càng phức tạp, không chỉ qua văn bản người dùng mà còn thông qua kết quả trả về từ các công cụ (tool outputs) mà Agent gọi tới. |
| Kiểm chứng tính đúng đắn (Fact-checking) | Yêu cầu hệ thống phải có khả năng đối chiếu câu trả lời với một cơ sở tri thức (RAG) theo thời gian thực để phát hiện thông tin sai lệch chuyên ngành. |

## 3. Mục tiêu cần đạt được

- Phát hiện và ngăn chặn thành công các loại tấn công: Prompt Injection, Jailbreak, System Prompt Leak.
- Hỗ trợ cấu hình blacklist/whitelist theo tổ hợp từ khóa (kết hợp logic AND/OR).
- Khả năng phát hiện thông tin sai lệch về một domain nhất định dựa trên RAG.
- Có báo cáo đánh giá hiệu quả chặn tấn công (block rate) và tỷ lệ chặn nhầm (false positive rate) trên các tập dữ liệu kiểm thử chuẩn.
