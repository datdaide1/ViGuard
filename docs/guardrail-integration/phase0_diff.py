"""Phase 0: diff Long's safety_rules.yaml against the canonical 109-rule workbook.

Canonical source: golden-dataset/driver-constraints/data/rules.json
                  (== Driver_constraints.xlsx#Constraints == vf_guardrails CSV)
Long's encoding:  vf_guardrails/config/safety_rules.yaml
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # docs/guardrail-integration/ -> repo root

CANON = json.loads((REPO / "golden-dataset/driver-constraints/data/rules.json").read_text(encoding="utf-8"))

import yaml  # noqa
LONG = yaml.safe_load((REPO / "vf_guardrails/config/safety_rules.yaml").read_text(encoding="utf-8"))
LONG_POLICIES = LONG.get("policies", [])

canon_by_id = {r["rule_id"]: r for r in CANON}
long_by_id = {}
long_dupes = []
for pol in LONG_POLICIES:
    rid = pol.get("id")
    if rid in long_by_id:
        long_dupes.append(rid)
    long_by_id.setdefault(rid, []).append(pol)

canon_ids = set(canon_by_id)
long_ids = set(long_by_id)

lines = []
def out(s=""):
    lines.append(s)

out("# Phase 0 — Rule coverage diff: safety_rules.yaml vs canonical 109-rule workbook")
out()
out(f"- Canonical rules (rules.json / xlsx#Constraints): **{len(CANON)}**")
out(f"- Long safety_rules.yaml policy entries: **{len(LONG_POLICIES)}** ({len(long_ids)} distinct rule ids)")
if long_dupes:
    out(f"- Duplicate rule ids in Long's YAML: {sorted(set(long_dupes))}")
out()

# --- canonical outcome / mode distribution
from collections import Counter
c_out = Counter(r["outcome"] for r in CANON)
c_mode = Counter(r["check_mode"] for r in CANON)
out("## Canonical distribution")
out(f"- check_mode: {dict(c_mode)}")
out(f"- outcome: {dict(sorted(c_out.items()))}")
out()

# --- coverage
missing = sorted(canon_ids - long_ids, key=lambda x: int(x[1:]))
extra = sorted(long_ids - canon_ids, key=lambda x: int(re.sub(r'\D','',x) or 0))
present = sorted(canon_ids & long_ids, key=lambda x: int(x[1:]))

out(f"## Coverage: {len(present)}/{len(CANON)} canonical rules encoded in Long's YAML")
out()
out(f"### Missing from Long's YAML ({len(missing)})")
out()
mc_out = Counter(canon_by_id[r]["outcome"] for r in missing)
mc_mode = Counter(canon_by_id[r]["check_mode"] for r in missing)
out(f"By outcome: {dict(sorted(mc_out.items()))}")
out(f"By check_mode: {dict(mc_mode)}")
out()
out("| rule_id | intent | outcome | mode | condition |")
out("|---|---|---|---|---|")
for rid in missing:
    r = canon_by_id[rid]
    out(f"| {rid} | `{r['intent']}` | {r['outcome']} | {r['check_mode']} | `{r['condition']}` |")
out()

if extra:
    out(f"### Rule ids in Long's YAML not in canonical ({len(extra)})")
    for rid in extra:
        for pol in long_by_id[rid]:
            out(f"- {rid}: intent=`{pol.get('intent')}` action={pol.get('enforcement',{}).get('action')}")
    out()

# --- semantic mismatches on shared ids
out("## Mismatches on shared rule ids (intent / outcome)")
out()
out("| rule_id | field | canonical | Long's YAML |")
out("|---|---|---|---|")
mismatch_count = 0
for rid in present:
    canon = canon_by_id[rid]
    for pol in long_by_id[rid]:
        li = pol.get("intent")
        lo = pol.get("enforcement", {}).get("action")
        if li != canon["intent"]:
            out(f"| {rid} | intent | `{canon['intent']}` | `{li}` |")
            mismatch_count += 1
        if lo != canon["outcome"]:
            out(f"| {rid} | outcome | {canon['outcome']} | {lo} |")
            mismatch_count += 1
if mismatch_count == 0:
    out("| — | — | (none) | — |")
out()
out(f"Total field mismatches: {mismatch_count}")
out()

# --- condition fidelity spot check on shared ids
out("## Condition fidelity — shared rule ids")
out()
out("Long's YAML stores `target_state: {field: {operator, value}}` + `logic`, a hand")
out("decomposition of the canonical `condition` expression. Spot check:")
out()
out("| rule_id | canonical condition | Long target_state | logic |")
out("|---|---|---|---|")
for rid in present[:25]:
    canon = canon_by_id[rid]
    pol = long_by_id[rid][0]
    ts = pol.get("target_state", {})
    ts_str = "; ".join(f"{k} {v.get('operator')} {v.get('value')!r}" for k, v in ts.items())
    out(f"| {rid} | `{canon['condition']}` | {ts_str} | {pol.get('logic','AND')} |")
out()

# --- intents covered
canon_intents = sorted(set(r["intent"] for r in CANON))
long_rule_intents = sorted(set(p.get("intent") for p in LONG_POLICIES))
out("## Intent coverage")
out(f"- Canonical distinct intents: {len(canon_intents)}")
out(f"- Intents appearing in Long's rules: {len(long_rule_intents)}")
missing_intents = sorted(set(canon_intents) - set(long_rule_intents))
out(f"- Canonical intents with **zero** rules in Long's YAML ({len(missing_intents)}): {missing_intents}")
out()

Path(REPO / "docs/guardrail-integration/PHASE0_RULE_DIFF.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
