# EVAL-01 — Xây Vietnamese tool-selection evaluation set

**Trạng thái:** planned  
**Sprint:** sprint-3  
**Code area:** evals  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục EVAL-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** MAP-02, MOD-01

**Mô tả:** Đánh giá `gpt-5-mini` và `gemini-3.6-flash` trên cùng bộ câu tiếng Việt về khả năng chọn domain tool và arguments; không đánh giá lại T1/T2/T3 của team Guardrail.

**Công việc chi tiết:**

- Câu rõ ràng/paraphrase cho 53 intents.
- Ambiguous parameter/target.
- Multi-action, negation, conditional và unknown capability.
- Prompt injection/tool hijacking.
- Expected tool, arguments, clarification/reject.
- Held-out split và so sánh OpenAI/Gemini trên cùng dataset/config logic.
- Ghi tỷ lệ lỗi API, latency và malformed tool calls theo provider.

**Đầu ra:** Dataset và Agent Model Evaluation Report.

**Acceptance criteria:**

- Report có tool accuracy, argument exact match, clarification và invalid-call rate.
- Không trộn Guardrail classifier accuracy vào Agent metric.
- Model được freeze dựa trên kết quả thực đo.

