# ViVi Agent

ViVi Agent là package Python độc lập nhận text, chọn tool xe đã đăng ký, đọc
`VehicleState`, thực thi handler tương ứng và trả kết quả có cấu trúc. Package
này chứa toàn bộ code, tests, evaluation và tài liệu cần thiết để chuyển giao
Agent sang repository hoặc deployment khác bằng một file zip.

Agent **không sở hữu policy an toàn**. Khi tích hợp production, Guardrail bên
ngoài quyết định `ALLOW`, `CONFIRM` hoặc `BLOCK`; UI bên ngoài chỉ gửi/nhận
closed public payload. Agent giữ prompt containment riêng để giảm prompt
injection nhưng lớp này không thay thế Guardrail.

## Trạng thái

- Runtime catalog: **123 intents** gồm baseline 53 và 70 capability từ
  `Intents_Candidate.xlsx` đã được đóng băng trong code với checksum.
- Tool registry: **11 domain tools**, **148 reviewed mappings**.
- Execution coverage: **112 action handlers**, **10 query responders** và
  **1 explicit refusal handler**.
- Model mặc định: `gemini-3.5-flash-lite`; process-local rate limit mặc định
  `12 RPM`.
- Phạm vi thực thi: simulator/adapter command. Package không chứa CAN/ECU hoặc
  actuator xe thật.

## Đọc gì trước

1. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — kiến trúc, data flow và module map.
2. [docs/INTEGRATION.md](docs/INTEGRATION.md) — ghép Guardrail, UI, model và actuator.
3. [docs/OPERATIONS.md](docs/OPERATIONS.md) — cấu hình, test, troubleshooting và zip.
4. [docs/PACKAGE_REPORT.md](docs/PACKAGE_REPORT.md) — scope, evidence và limitations.
5. [docs/AI_CONTEXT.md](docs/AI_CONTEXT.md) — context cô đọng cho AI/code agent mới.

## Quick start

Yêu cầu Python 3.11+:

```powershell
cd vivi-agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest -q
```

Chạy Agent với Gemini:

```powershell
$env:AGENT_MODEL_PROVIDER = "gemini"
$env:GEMINI_API_KEY = "<backend-secret>"
$env:GEMINI_MODEL_ID = "gemini-3.5-flash-lite"
$env:AGENT_MODEL_RPM = "12"
.\.venv\Scripts\python.exe examples\standalone_agent.py "Bật điều hòa"
```

Không đặt key trong source, file zip, UI payload hoặc log.

## Public Python API tối thiểu

```python
from vivi_agent import build_agent_runtime_from_env

agent = build_agent_runtime_from_env()
result = agent.handle_text(
    "Mở cửa ghế lái",
    session_id="demo",
    request_id="req-001",
)
print(result.status.value, result.message)
```

`handle_text` cung cấp request idempotency trong process và serialize side
effects theo session. Action có field mô phỏng sẽ cập nhật state atomically;
command-only capability phát typed one-shot command và chờ adapter/telemetry
bên ngoài cập nhật state.

## Tạo file bàn giao

```powershell
python scripts\verify_package.py
python scripts\build_zip.py
```

Output mặc định là `vivi-agent.zip` ở thư mục cha. Script loại `.env`, cache,
virtualenv, kết quả tạm và secret-like files khỏi archive.
