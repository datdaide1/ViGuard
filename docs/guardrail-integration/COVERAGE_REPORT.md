# Coverage Report — Guardrail + Agent (PRD §20 DoD)

**Sinh tự động:** `vf_guardrails/evals/run_coverage.py` · 2026-09-07
**Kết quả:** ✅ ĐẠT

## 1. Workbook policy

| Chỉ số | Kỳ vọng | Thực tế | |
|---|---|---|---|
| rule | 109 | 109 | ✅ |
| intent | 53 | 53 | ✅ |
| gate rule | 104 | 104 | ✅ |
| monitor rule | 5 | 5 | ✅ |
| policy_checksum | — | `sha256:8633be7eafe696114f390d3ffbe41ead2dff015ec9a96d89515c42296503b65b` | |

RuleSet.load() fail-closed nếu bất kỳ số nào lệch (PRD FR-06, AC-1/12).

## 2. Độ phủ intent qua bảng tool→intent

- Bảng copy của agent: **79 dòng** → **54 intent**.
- Workbook intent **không** tới được qua map: không có ✅
- Intent map được nhưng **không** có trong workbook: ['turnon_LKA']
  - `turnon_LKA` — agent map `control_driver_assistance/activate/lane_keeping_assist` nhưng workbook chỉ có `turnoff_LKA`. Service trả typed error (không bao giờ ALLOW). PM chấp nhận tạm; chờ Long bổ sung intent.

## 3. Bảy outcome

- Có mặt trong workbook: ['ALLOW', 'ANSWER', 'BLOCK_UNAVAILABLE', 'BLOCK_UNSAFE', 'CONFIRM', 'NOT_VOICE_ACTIONABLE', 'UNKNOWN']
- Thiếu: không có ✅
- Bằng chứng routing đủ 7 outcome trên 2.313 dòng golden dataset: `run_golden.py` (100%).

## 4. Năm monitor rule (đều có kịch bản — `test_monitor_2p3.py`)

| rule_id | intent | outcome | condition |
|---|---|---|---|
| R033 | activate_campmode | BLOCK_UNAVAILABLE | `battery_pct < 15` |
| R037 | activate_petmode | BLOCK_UNAVAILABLE | `battery_pct < 25` |
| R048 | activate_autopark | BLOCK_UNSAFE | `autopark_state == 'ACTIVE' AND NOT ( speed < 15 )` |
| R070 | activate_aac | ALLOW | `( acc_state == 'ACTIVE' ) AND speed == 0` |
| R073 | activate_hda | BLOCK_UNSAFE | `duration_seconds(hand_on_steeringwheel == False) > 15` |

## 5. Kịch bản demo end-to-end

`py -3 run_both.py` — ALLOW / BLOCK_UNSAFE / CONFIRM(+confirm) / ANSWER / MONITOR, mỗi lượt in trace guardrail đầy đủ (PRD FR-14 / §16) + latency.

> Giới hạn: golden dataset `reviewed=0/2313` (khớp nhãn, nhãn chưa kiểm độc lập). `_STATE_DEFAULTS` là giả định Pha 1. Đây là MÔ PHỎNG, không phải xe thật.
