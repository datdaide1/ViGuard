# MON-ADP-01 — Deferred Follow-ups

**Trạng thái:** deferred — tạm ignore, quay lại sau khi hoàn tất build agent
**Liên quan:** src/vivi_agent/adapters/monitor/adapter.py
**Nguồn:** code review branch `vivi-agent/mon-adp-01` (2 findings bị skip khi apply review fixes)

> File này ghi lại 2 vấn đề đã xác nhận là thật (real bug/gap) nhưng **chưa sửa** vì
> cần quyết định thiết kế / phụ thuộc module khác chưa sẵn sàng. Đọc file này trước
> khi đóng task MON-ADP-01 lần cuối hoặc trước khi bật monitor trong production.

---

## 1. Stop không đi qua VehicleToolGateway — an toàn giả (P0, mức độ nghiêm trọng cao nhất)

**File:** `src/vivi_agent/adapters/monitor/adapter.py` — `GuardrailMonitorAdapter._execute_stop` (~line 197)

**Vấn đề:**
`_execute_stop` chỉ gọi `ActiveActionRegistry.stop_action`/`fail_action` — đổi field
`phase` của một object Python trong bộ nhớ. Tham số `vehicle_gateway` truyền vào
`__init__` (lưu ở `self.gateway`) **không bao giờ được đọc** ở đâu khác trong file.
Không nơi nào trong codebase gọi `registry.register_stop_handler(...)`, nên ngay cả
cơ chế callback của registry cũng không có gì để chạy.

**Kết quả:** Khi Guardrail monitor trả về BLOCK_UNSAFE/STOP cho một active action đang
chạy (HDA, AAC, autopark, camp/pet mode), registry báo "đã dừng" nhưng **không có lệnh
thực tế nào được gửi xuống xe/simulator** — action vẫn tiếp tục chạy. Log/UI/audit đọc
từ registry sẽ báo sai rằng sự cố đã được xử lý.

**Vì sao chưa sửa:**
- Route đúng chuẩn qua `VehicleToolGateway.execute()` yêu cầu một `ActionProposal` +
  permit do Guardrail cấp (`kind=="decision"`, `outcome=="ALLOW"`, digest khớp,
  chống replay...). Quyết định monitor (BLOCK_UNSAFE/STOP) **không phải** permit cho
  phép thực thi — về bản chất khác với luồng proposal→ALLOW→execute hiện có.
- Đã kiểm tra: **chưa hề tồn tại** tool/intent "stop_hda", "deactivate_hda"... nào
  được đăng ký trong `HandlerRegistry` (`src/vivi_agent/vehicle/execution/generic.py`).
  Handler hiện tại chỉ đăng ký theo đúng `intent_id` gốc (activate_*), không có khái
  niệm "stop proposal" riêng.
- Nếu tự chế ra luồng stop-proposal mà không có spec từ phía Guardrail, rủi ro là
  fail-safe stop (vốn phải luôn thành công) lại phụ thuộc vào 1 network round-trip
  khác để xin permit — nếu Guardrail đang down (đúng lúc cần dừng khẩn cấp) thì luồng
  này cũng kẹt theo.

**Cần làm trước khi sửa:**
1. Thiết kế "stop proposal" contract với Guardrail (payload shape, `/v1/evaluate/action`
   hay endpoint riêng, digest tính trên cái gì).
2. Đăng ký actuator handler cho stop/cancel per-intent trong `HandlerRegistry`.
3. Wire `_execute_stop` gọi `self.gateway.execute(stop_proposal, decision)` sau khi có
   permit, chỉ update registry SAU KHI gateway xác nhận thành công (không update trước
   như hiện tại).

---

## 2. Adapter chưa wire vào orchestrator/bootstrap — dead code trong production

**File:** `src/vivi_agent/adapters/monitor/adapter.py` — class `GuardrailMonitorAdapter` (~line 30)

**Vấn đề:** `GuardrailMonitorAdapter`, `.tick()`, `.on_state_changed()` không có nơi
nào gọi tới ngoài package của chính nó và `tests/adapters/test_monitor_adapter.py`.
Không có orchestrator, runtime bootstrap, hay cơ chế subscribe state-change nào
reference tới các symbol này.

**Kết quả:** Trong production, monitor **không bao giờ chạy** — HDA/AAC/autopark/
camp/pet mode có thể chạy vô thời hạn mà không có giám sát an toàn theo state thay
đổi, dù tracker ghi "completed".

**⚠️ Ràng buộc thứ tự quan trọng:** Việc #2 (wire vào production) **phải làm sau**
việc #1 (stop thật sự hoạt động), không được đảo ngược. Nếu bật #2 trước khi #1 xong,
hệ thống sẽ "trông như đang giám sát" (log ra metrics, evaluate liên tục mỗi lần state
đổi) nhưng cái dừng xe thực sự vẫn là giả — tạo cảm giác an toàn giả (false confidence),
còn nguy hiểm hơn cả việc để nó tắt hẳn như hiện tại.

**Cần làm trước khi sửa:**
1. Xác nhận việc #1 đã xong và verify được bằng integration test dừng được simulator thật.
2. Xác định nơi state-change được publish (VEH-02 event store / state machine?) để biết
   hook `on_state_changed` đúng chỗ, hay cần polling `tick()` theo interval.
3. Xử lý vấn đề hiệu năng đã note trong review trước: `evaluate_active_actions` hiện
   gọi HTTP tuần tự, đồng bộ, chặn (blocking) cho từng active action — cần batch hoặc
   parallelize trước khi đưa vào hot path xử lý state.

---

## Khi quay lại việc này

Đọc lại 2 mục trên theo đúng thứ tự (#1 trước #2). Không đánh dấu MON-ADP-01
"hoàn tất" theo nghĩa an toàn thực sự cho tới khi cả 2 được giải quyết.

---

## Cập nhật (HERO-02) — Mục #1 đã đóng cho `activate_hda`/`activate_aac`

**File:** `src/vivi_agent/behaviors/hero/active_driving_assist.py`

Mục #1 ở trên đã được giải quyết, nhưng **chỉ cho 2 intent `activate_hda` và
`activate_aac`** — `activate_autopark`/`activate_campmode`/`activate_petmode`
**vẫn còn nguyên vấn đề đã mô tả**, để lại cho HERO-03. (Cập nhật: HERO-03 đã
đóng mục #1 cho `activate_autopark`/`activate_campmode` — xem mục cập nhật bên
dưới. `activate_petmode` vẫn còn mở.)

Hướng đi không phải "thiết kế stop proposal contract với Guardrail" như gợi ý
ban đầu ở mục #1 — sau khi phân tích, một round-trip permit thứ hai cho một
fail-safe stop là rủi ro tự thân (nếu Guardrail down đúng lúc cần dừng khẩn
cấp, luồng dừng cũng kẹt theo). Thay vào đó:

- `register_hda_aac_stop_handlers(registry, state_machine)` đăng ký stop
  handler thật cho `"activate_hda"`/`"activate_aac"` — mutate `VehicleState`
  trực tiếp qua `VehicleStateMachine.apply(..., actor_kind=ActorKind.SYSTEM)`,
  không qua `VehicleToolGateway`/permit boundary (cùng pattern
  `reset_open_door_state` của HERO-01).
- `make_monitored_active_action_handler(...)` đóng luôn phần "chưa hề tồn tại
  lệnh gọi `registry.start_action()`" — wrap `ActiveActionHandler` để mỗi lần
  `activate_hda`/`activate_aac` chạy thành công đều tạo `ActiveActionRecord`
  thật trong registry, để `GuardrailMonitorAdapter.tick()` có gì đó để
  evaluate.
- Cascade: dừng `activate_aac` khi `hda_active=True` sẽ tắt cả hai trong CÙNG
  MỘT transition (bắt buộc bởi invariant `HDA_REQUIRES_ACTIVE_ACC` trên
  `AdasState`), rồi mới dừng record `activate_hda` trong registry.

Xác nhận bằng integration test dừng được state machine thật:
`tests/integration/hero/test_hero02_hda_aac.py::TestHero02HdaAacE2E::test_e2e_monitor_stop_flips_real_vehicle_state`.

Mục #2 (wire `GuardrailMonitorAdapter` vào orchestrator/bootstrap production)
**vẫn chưa làm** — đây là quyết định wiring toàn hệ thống (nơi state-change
được publish, polling `tick()` theo interval hay subscribe, batch/parallelize
HTTP calls), ngoài scope của một hero behavior ticket, và đúng như ràng buộc
thứ tự đã ghi ở trên, chỉ nên làm sau khi #1 đã đóng cho **toàn bộ 5** intent
(tức là sau HERO-03).

---

## Cập nhật (HERO-03) — Mục #1 đã đóng thêm cho `activate_autopark`/`activate_campmode`

**File:** `src/vivi_agent/behaviors/hero/autopark_campmode.py`

Cùng hướng đi và cùng lý do như bản cập nhật HERO-02 ở trên (không thêm một
permit round-trip thứ hai cho fail-safe stop): `register_autopark_campmode_stop_handlers(registry, state_machine)`
đăng ký stop handler thật cho `"activate_autopark"`/`"activate_campmode"`, và
`make_monitored_active_action_handler(...)` (trong module này) đóng phần
`registry.start_action()` chưa từng được gọi cho hai intent này.

Phần plumbing dùng chung giữa HERO-02 và HERO-03 (bridge handler, SYSTEM-actor
patch boilerplate, lớp base đọc monitor result không suy diễn policy) đã được
tách sang `src/vivi_agent/behaviors/hero/_active_action_common.py` để tránh
trùng lặp — `active_driving_assist.py` (HERO-02) cũng đã được refactor để dùng
lại phần dùng chung này, hành vi/API công khai không đổi (test HERO-02 hiện có
vẫn pass nguyên trạng).

Khác với HDA/AAC (chỉ có 1 kiểu cascade), autopark và camp mode không cần
cascade sang state khác khi dừng — mỗi cái tắt đúng field của mình
(`adas.autopark_state`/`modes.camp_mode_active`) và dọn `active_actions` entry
tương ứng trong cùng một transition.

`activate_petmode` **vẫn còn mở** — HERO-03 chỉ có scope autopark + camp mode
theo đúng tracker/TASK.md. Mục #2 (wire `GuardrailMonitorAdapter` vào
orchestrator/bootstrap) vẫn chưa làm, và giờ chỉ còn phụ thuộc `activate_petmode`
để đóng mục #1 cho toàn bộ 5 intent.

Xác nhận bằng integration test dừng được state machine thật:
`tests/integration/hero/test_hero03_autopark_campmode.py::TestHero03AutoparkCampmodeE2E::test_e2e_monitor_stop_flips_real_vehicle_state_for_campmode`
và `::test_e2e_monitor_stop_flips_real_vehicle_state_for_autopark`.
