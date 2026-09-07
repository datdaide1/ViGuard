"""Automated coverage report for the guardrail+agent slice (PRD §20 Definition of Done).

Writes ``docs/guardrail-integration/COVERAGE_REPORT.md``:

  - 109/109 rules / 53 intents / 104 gate / 5 monitor loaded and fail-closed
  - every workbook intent reachable through the copied tool->intent map
  - all 7 outcomes present in the workbook
  - the 5 monitor rules enumerated
  - known gap: turnon_LKA (agent maps it, workbook has no rule)

Run:  PYTHONIOENCODING=utf-8 py -3 vf_guardrails/evals/run_coverage.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from policy import RuleSet  # noqa: E402
from service.tool_map import DEFAULT_MAPPER, DEFAULT_MAPPING_RULES  # noqa: E402

_OUT = _ROOT.parent / "docs" / "guardrail-integration" / "COVERAGE_REPORT.md"
_SEVEN = ("ALLOW", "BLOCK_UNSAFE", "BLOCK_UNAVAILABLE", "CONFIRM", "NOT_VOICE_ACTIONABLE", "ANSWER", "UNKNOWN")


def build_report() -> tuple[str, bool]:
    rs = RuleSet.load()
    rules = rs.all()
    workbook_intents = set(rs.intents)
    gate = sum(r.check_mode == "gate" for r in rules)
    monitor = [r for r in rules if r.check_mode == "monitor"]
    outcomes_present = {r.outcome for r in rules}
    mapped_intents = DEFAULT_MAPPER.intents

    unreachable = sorted(workbook_intents - mapped_intents)
    mapped_not_in_workbook = sorted(mapped_intents - workbook_intents)
    missing_outcomes = [o for o in _SEVEN if o not in outcomes_present]

    ok = (
        len(rules) == 109 and len(workbook_intents) == 53 and gate == 104
        and len(monitor) == 5 and not unreachable and not missing_outcomes
    )

    lines = [
        "# Coverage Report — Guardrail + Agent (PRD §20 DoD)",
        "",
        f"**Sinh tự động:** `vf_guardrails/evals/run_coverage.py` · {date.today().isoformat()}",
        f"**Kết quả:** {'✅ ĐẠT' if ok else '❌ CHƯA ĐẠT'}",
        "",
        "## 1. Workbook policy",
        "",
        "| Chỉ số | Kỳ vọng | Thực tế | |",
        "|---|---|---|---|",
        f"| rule | 109 | {len(rules)} | {'✅' if len(rules)==109 else '❌'} |",
        f"| intent | 53 | {len(workbook_intents)} | {'✅' if len(workbook_intents)==53 else '❌'} |",
        f"| gate rule | 104 | {gate} | {'✅' if gate==104 else '❌'} |",
        f"| monitor rule | 5 | {len(monitor)} | {'✅' if len(monitor)==5 else '❌'} |",
        f"| policy_checksum | — | `{rs.policy_checksum}` | |",
        "",
        "RuleSet.load() fail-closed nếu bất kỳ số nào lệch (PRD FR-06, AC-1/12).",
        "",
        "## 2. Độ phủ intent qua bảng tool→intent",
        "",
        f"- Bảng copy của agent: **{len(DEFAULT_MAPPING_RULES)} dòng** → **{len(mapped_intents)} intent**.",
        f"- Workbook intent **không** tới được qua map: {unreachable or 'không có ✅'}",
        f"- Intent map được nhưng **không** có trong workbook: {mapped_not_in_workbook or 'không có'}",
    ]
    if mapped_not_in_workbook:
        lines.append(
            "  - `turnon_LKA` — agent map `control_driver_assistance/activate/lane_keeping_assist` "
            "nhưng workbook chỉ có `turnoff_LKA`. Service trả typed error (không bao giờ ALLOW). "
            "PM chấp nhận tạm; chờ Long bổ sung intent."
        )
    lines += [
        "",
        "## 3. Bảy outcome",
        "",
        f"- Có mặt trong workbook: {sorted(outcomes_present)}",
        f"- Thiếu: {missing_outcomes or 'không có ✅'}",
        "- Bằng chứng routing đủ 7 outcome trên 2.313 dòng golden dataset: `run_golden.py` (100%).",
        "",
        "## 4. Năm monitor rule (đều có kịch bản — `test_monitor_2p3.py`)",
        "",
        "| rule_id | intent | outcome | condition |",
        "|---|---|---|---|",
    ]
    for r in sorted(monitor, key=lambda x: x.rule_id):
        lines.append(f"| {r.rule_id} | {r.intent} | {r.outcome} | `{r.raw_condition}` |")
    lines += [
        "",
        "## 5. Kịch bản demo end-to-end",
        "",
        "`py -3 run_both.py` — ALLOW / BLOCK_UNSAFE / CONFIRM(+confirm) / ANSWER / MONITOR, "
        "mỗi lượt in trace guardrail đầy đủ (PRD FR-14 / §16) + latency.",
        "",
        "> Giới hạn: golden dataset `reviewed=0/2313` (khớp nhãn, nhãn chưa kiểm độc lập). "
        "`_STATE_DEFAULTS` là giả định Pha 1. Đây là MÔ PHỎNG, không phải xe thật.",
        "",
    ]
    return "\n".join(lines), ok


def main() -> int:
    report, ok = build_report()
    _OUT.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n-> {_OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
