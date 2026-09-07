# ViGuard — Guardrail-first ViVi Agent Simulator

ViGuard là môi trường mô phỏng và đánh giá local cho một AI Agent trên xe. Mọi
câu lệnh văn bản phải đi qua Guardrail trước khi ViVi Agent được phép phản hồi
hoặc thực hiện hành động mô phỏng.

Mục tiêu của pilot là biến một nguyên tắc kiến trúc thành bằng chứng quan sát
được: cùng một câu lệnh có thể tạo kết quả khác nhau khi trạng thái xe thay đổi;
đường bị chặn không được gọi actuator; đường được cho phép phải truy vết được từ
câu lệnh, intent, state snapshot và rule đã áp dụng.

> **Trạng thái hiện tại (2026-09): Pha 1′ + 2′ đã merge vào `guardrail-integration`;
> Pha 3′ (demo + trace + query) đang trên `feat/guardrail-phase3`.** Đọc
> **`docs/guardrail-integration/STATUS.md`** để nắm tiến độ. Tóm tắt: agent ✅;
> constraint engine ✅ 100% golden; T2 TF-IDF ✅ 88.3% frozen; HTTP contract layer
> `vf_guardrails/service/` ✅ (action + confirm + monitor + query + trace).
> Demo 2 service end-to-end: **`py -3 run_both.py`**. Báo cáo phủ: `py -3 vf_guardrails/evals/run_coverage.py`.
> Đây là **MÔ PHỎNG** — chưa phải ứng dụng điều khiển xe, không phải bằng chứng
> policy đã được chứng nhận cho xe thật, không có xác nhận an toàn của OEM.

## Luồng sản phẩm

```text
Text Input UI
      │
      ▼
Guardrail Gateway
  ├─ kiểm tra và chuẩn hóa text
  ├─ phân loại intent qua T1 → T2 → T3
  ├─ đọc Vehicle State Mock
  └─ đánh giá constraint
      │
      ▼
Guardrail Decision
      │
      ▼
ViVi Agent
  ├─ phản hồi có căn cứ
  ├─ yêu cầu xác nhận và đánh giá lại state
  └─ gọi Mock Actuator chỉ trên đường hợp lệ
      │
      ▼
Vehicle events, state changes và audit trace
```

Guardrail đứng ngoài và trước ViVi Agent. Classifier chỉ xác định người dùng
muốn gì; nó không tự quyết định an toàn. Kết quả cuối chỉ được tạo sau khi intent
được đánh giá cùng Vehicle State Mock và constraint tương ứng.

## Phạm vi pilot

Theo PRD hiện hành, sản phẩm mục tiêu bao gồm:

- text input đi qua một Guardrail Gateway duy nhất;
- catalog đóng gồm 53 intent trong phạm vi pilot;
- policy workbook gồm 109 constraint: 104 rule `gate` và 5 rule `monitor`;
- ba tầng phân loại T1/T2/T3, trong đó T3 chỉ là fallback;
- Vehicle State Mock là nguồn sự thật cho constraint evaluation;
- ViVi Agent chuyển decision thành phản hồi, confirmation hoặc hành động mô phỏng;
- Mock Actuator cho action/UI intent;
- confirmation dùng một lần và luôn re-evaluate trên state mới;
- monitor có thể dừng active action khi điều kiện không còn phù hợp;
- trace đủ để tái dựng toàn bộ lượt xử lý.

Guardrail công bố đúng bảy outcome:

| Outcome | Ý nghĩa ở biên Agent |
| --- | --- |
| `ALLOW` | Agent có thể đi vào execution path hợp lệ. |
| `BLOCK_UNSAFE` | Chặn do điều kiện an toàn hiện tại. |
| `BLOCK_UNAVAILABLE` | Chặn vì tính năng không khả dụng. |
| `CONFIRM` | Chưa được thực thi; cần xác nhận và đánh giá lại. |
| `NOT_VOICE_ACTIONABLE` | Không thực hiện qua luồng điều khiển bằng giọng nói. |
| `ANSWER` | Trả lời từ state hoặc dữ liệu mô phỏng có căn cứ. |
| `UNKNOWN` | Không có dữ liệu phù hợp để trả lời hoặc hành động. |

## Các bất biến bắt buộc

- UI không gửi raw text trực tiếp cho ViVi Agent.
- ViVi Agent không tự đổi outcome do Guardrail trả về.
- Nội dung người dùng khai báo về state không thay thế Vehicle State Mock.
- Block, error và confirmation-pending không được tạo execution hợp lệ.
- Confirmation cũ, hết hạn hoặc replay không được gọi actuator.
- Policy lỗi phải fail closed; không tiếp tục bằng tập rule bị thiếu hoặc mâu thuẫn.
- Public event không chứa permit, credential, system prompt hoặc hidden reasoning.
- Pilot đo mức độ implementation tuân theo workbook, không đo “physical safety accuracy”.

## Trạng thái triển khai

| Hạng mục | Trạng thái | Evidence |
| --- | --- | --- |
| Guardrail–Agent contract (`CON-01`) | Implementation đã merge; chờ external acceptance | `src/vivi_agent/contracts/guardrail/v1/` |
| Agent–UI contract (`CON-02`) | Implementation đã merge; chờ external acceptance | `src/vivi_agent/contracts/agent_ui/v1/` |
| Runtime Agent/Vehicle, integration, evaluation và release | Theo tracker, phần lớn chưa triển khai | `VIVI_AGENT_TASK_TRACKER.yaml` |
| Guardrail classifier/constraint runtime và web UI hoàn chỉnh | Chưa có trong checkout hiện tại | PRD và implementation plan |

Status trong tracker chỉ chuyển sang `done` khi acceptance gate tương ứng đã có
evidence; merge code không tự động đồng nghĩa với external approval.

## Cấu trúc repository

```text
.
├── specs/
│   ├── prd/                         # Product requirements và scope chuẩn
│   ├── architecture/                # Kiến trúc Guardrail
│   └── agent/                       # ViVi Agent spec và implementation plan
├── src/vivi_agent/
│   ├── contracts/                   # Contract đã triển khai và task specs
│   └── ...                          # Feature boundaries cho các task tiếp theo
├── tests/                           # Contract, integration, E2E và performance
├── evals/                           # Evaluation task boundaries
├── docs/agent/                      # Integration/runbook work
├── Driver_constraints.xlsx         # Policy workbook trong workspace hiện tại
├── VIVI_AGENT_TASK_TRACKER.yaml     # Tracker và acceptance evidence
└── VIVI_AGENT_WORKSPACE.md          # Quy ước workspace triển khai Agent
```

## Kiểm tra phần đã triển khai

Checkout hiện tại chưa có application runtime hoặc quy trình cài đặt hoàn chỉnh.
Các contract tests có thể chạy bằng Python từ repository root:

```powershell
python -m unittest `
  tests.contracts.guardrail.test_consumer_contract `
  tests.contracts.agent_ui.test_consumer_contract
```

Contract suite kiểm tra version mismatch, fail-closed permit semantics, closed
public payloads, redaction, correlation, event ordering, execution lifecycle và
khả năng UI mock dựng lại ba demo scenario chỉ từ public events.

## Nguồn yêu cầu chuẩn

- [PRD Guardrail hiện hành](specs/prd/PRD_Guardrail_FINAL.md) — phạm vi sản phẩm,
  business rules, requirements, acceptance criteria và success metrics.
- [Kiến trúc Guardrail](specs/architecture/Architecture_Guardrail_FINAL.md) —
  component boundaries và quyết định kỹ thuật.
- [ViVi Agent specification](specs/agent/VIVI_VEHICLE_AGENT_SPEC.md) — contract,
  behavior và simulator requirements phía Agent.
- [ViVi Agent implementation plan](specs/agent/VIVI_IMPLEMENTATION_PLAN.md) —
  task sequencing, dependencies và release gates.

Các tài liệu có nhãn `Superseded` hoặc `Archived` không được dùng làm nguồn scope
hiện tại.

## Ngoài phạm vi

- ASR và voice pipeline production;
- CAN bus, ECU hoặc actuator xe thật;
- trợ lý hội thoại mở ngoài catalog pilot;
- cloud production deployment và multi-vehicle operation;
- chứng nhận ISO 26262, phê duyệt OEM hoặc khẳng định policy đúng cho xe thật.

ViGuard hiện là software pilot trên dữ liệu và trạng thái mô phỏng. Mọi tuyên bố
về an toàn vật lý hoặc tuân thủ thực tế cần evidence và chủ sở hữu chuyên môn bên
ngoài repository này.
