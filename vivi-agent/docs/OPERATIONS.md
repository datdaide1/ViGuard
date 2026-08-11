# Operations, testing và đóng gói

## 1. Môi trường

Python 3.11+; runtime dependency duy nhất là `requests`. Test dependency là
`pytest`. Tạo environment sạch thay vì dùng environment dự án khác:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Copy `.env.example` thành cấu hình của deployment nhưng không đặt `.env` vào
Git hoặc zip. Package không tự load `.env`; caller chịu trách nhiệm inject env.

## 2. Validation commands

```powershell
python scripts\verify_package.py
python -m pytest -q
python -m compileall -q src
```

Các gate quan trọng:

- catalog/mapping/behavior/query coverage;
- standalone runtime + duplicate request concurrency;
- model provider schema, rate limiting, retry và error redaction;
- Guardrail allow/confirm/block coordinator;
- UI consumer contract, event ordering, reconnect;
- state invariants, handlers, integration/E2E/adversarial scenarios;
- EVAL-01 baseline và EVAL-02 candidate mapping dataset.

Live model smoke cần key thật và phải tuân thủ quota. Với Gemini dùng
`gemini-3.5-flash-lite`, `AGENT_MODEL_RPM=12`; không chạy live smoke như unit
test mặc định.

## 3. Build zip

```powershell
python scripts\build_zip.py
```

Script chạy package verification trước, scan tên file nguy hiểm và tạo archive
deterministic ở `../vivi-agent.zip`. Archive chỉ có một top-level folder
`vivi-agent/`. Có thể chỉ định output:

```powershell
python scripts\build_zip.py --output D:\handoff\vivi-agent.zip
```

Excluded: `.env`, virtualenv, Git metadata, caches, bytecode, temporary results,
coverage output và archive cũ.

## 4. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Xử lý |
| --- | --- | --- |
| `ModuleNotFoundError: vivi_agent` | chưa install hoặc sai cwd | `pip install -e .` từ `vivi-agent/` |
| readiness false | thiếu key/transport | kiểm tra provider env; không fallback mock ngầm |
| clarification | thiếu target/value hoặc mapping invalid | log reason code, không bypass validator |
| `UNKNOWN` query | telemetry field chưa có | bổ sung trusted state/adapter, không dùng model đoán |
| 429 | vượt provider quota | giữ RPM ≤ quota; runtime default 12 |
| action completed nhưng state chưa đổi | command-only capability | chờ actuator ack/telemetry và update state |
| duplicate UI event | ACK cursor sai | deduplicate theo `(session_id, sequence)` |

## 5. Versioning và change process

Khi thêm intent: cập nhật candidate/manifest, tool signature, mapping, handler hoặc
query responder, tests và EVAL dataset trong cùng change. Startup coverage phải
fail nếu thiếu bất kỳ layer nào. Khi đổi public Guardrail/UI schema, tăng contract
version thay vì silently chấp nhận field lạ.
