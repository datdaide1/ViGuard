# P1-CACHE — Model/session optimization

**Trạng thái:** completed
**Sprint:** backlog
**Code area:** `src/vivi_agent/model_providers`
**Nguồn:** `specs/agent/VIVI_IMPLEMENTATION_PLAN.md` (mục P1-CACHE)

**Mức:** P1
**Phụ thuộc:** MOD-01, PERF-01

## Mô tả

Giảm chi phí CPU lặp lại trước mỗi model call bằng cách tái sử dụng adapter theo
provider và cache tool/workflow schema sinh từ registry bất biến. Payload mỗi
request vẫn nhận defensive clone để transport không thể làm bẩn cache.

## Phạm vi an toàn

- Chỉ cache cấu hình model và schema từ registry bất biến.
- Không cache conversation, model response, Guardrail decision, permit,
  Vehicle State/PIP, execution result hoặc session lock.
- Provider failover và turn pinning giữ nguyên.
- Cache adapter được khởi tạo thread-safe, tối đa một instance mỗi provider.
- Transport rotation dùng API `replace_transport()` để rebind và invalidate
  đúng cache entry; không mutate constructor input mapping.

## Acceptance criteria

- Benchmark offline chứng minh giảm chi phí adapter/schema preparation.
- Cùng provider tái sử dụng đúng một adapter kể cả khi truy cập đồng thời.
- Mutation trên payload của một request không ảnh hưởng request sau.
- Không thay đổi model proposal contract hoặc safety/authorization boundary.
- Unit tests mục tiêu và full regression suite pass.

## Evidence

- `src/vivi_agent/model_providers/selection.py`
- `src/vivi_agent/model_providers/adapters.py`
- `tests/model_providers/test_model_providers.py`
- `tests/performance/p1-cache/benchmark.py`
- `tests/performance/p1-cache/BENCHMARK_REPORT.md`
