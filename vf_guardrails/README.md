# VinFast Context-Aware AI Guardrail Engine (Local Embedded)

Hệ thống kiểm soát an toàn AI theo ngữ cảnh (Cyber-Physical Operational Guardrail) chạy cục bộ cho xe điện VinFast, giúp phát hiện ý định nguy hiểm từ giọng nói của tài xế và đối chiếu với trạng thái thực tế của xe (`VehicleState`) để đưa ra quyết định chặn (`BLOCK`) hoặc cho qua (`PASS`).

## Đặc trưng nổi bật
- **Thời gian thực**: Độ trễ trung bình < 10ms (Deterministic In-Memory Execution).
- **Hoàn toàn Offline**: Không có cuộc gọi mạng, không sử dụng API bên ngoài, đảm bảo an ninh và tính tin cậy.
- **Phân loại ý định cực nhanh**: Tầng 1 sử dụng thuật toán cây tiền tố Trie từ thư viện C-extension `pyahocorasick` với độ trễ < 2ms.
- **Ràng buộc an toàn dạng khai báo (Declarative Rules)**: Các quy tắc an toàn được khai báo bằng tệp YAML (`config/safety_rules.yaml`), dễ dàng mở rộng và bảo trì mà không cần sửa đổi logic mã nguồn.

## Yêu cầu hệ thống & Cài đặt
1. Cài đặt các thư viện cần thiết:
   ```bash
   pip install -r requirements.txt
   ```

## Hướng dẫn sử dụng

### 1. Tích hợp thư viện vào dự án Python
```python
from car_status import VehicleState
from src.guardrail import VinFastGuardrail

# Khởi tạo Engine
guardrail = VinFastGuardrail()

# Định nghĩa trạng thái xe điện (ví dụ xe đang chạy tốc độ cao)
state = VehicleState(
    speed_kmh=80.0,
    gear="D",
    doors_locked=True,
    trunk_open=False,
    driver_seat_angle_deg=95.0,
    passenger_seat_angle_deg=95.0,
    has_passenger=False,
    ambient_light="DAY",
    rain_sensor=False,
    battery_level=85.0,
    tire_pressure_psi=32.0
)

# Xử lý câu nói của tài xế
result = guardrail.process("mở cốp sau giúp tôi", state)

# Kiểm tra kết quả
print(f"Ý định: {result.intent}")       # INTENT_OPEN_TRUNK
print(f"Hành động: {result.action}")     # BLOCK
print(f"Phản hồi: {result.response}")   # "Xe đang chạy với tốc độ 80.0 km/h. Không thể mở cốp sau vì lý do an toàn."
print(f"Độ trễ: {result.latency_ms} ms")
```

### 2. Chạy ứng dụng giả lập tương tác (CLI Simulation)
Trình giả lập cho phép bạn nhập câu lệnh giọng nói bất kỳ và thay đổi trạng thái động cơ bằng các lệnh `set`:
```bash
python app_sim.py
```
*Gõ `state` để xem thông tin xe, `set speed_kmh 50` để chỉnh xe chạy, hoặc nhập câu lệnh mở cốp, ngả ghế, tắt đèn để kiểm tra.*

### 3. Chạy đo đạc hiệu năng (Benchmark Suite)
Chạy đo hiệu năng với dữ liệu mẫu trong `data/vinfast_test_data.json`:
```bash
python tests/run_benchmark.py
```

### 4. Chạy bộ kiểm thử tự động
```bash
pytest tests/test_guardrail.py -v
```
