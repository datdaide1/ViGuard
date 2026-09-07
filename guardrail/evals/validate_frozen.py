"""Structural validation of the frozen test set against FROZEN_TESTSET_SPEC.md.

Checks schema, catalog membership, per-intent counts, metadata-balance
thresholds, exact/near duplicates, and hard-negative templating.
Does NOT judge label correctness — that needs a human pass.

Usage:  py -3 guardrail/evals/validate_frozen.py [path/to/frozen_testset.jsonl]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else _REPO / "guardrail/evals/data/frozen_testset.jsonl"

CATALOG = {
    r["intent"]
    for r in json.loads((_REPO / "golden-dataset/driver-constraints/data/rules.json").read_text(encoding="utf-8"))
}
DIALECT = {"bac", "trung", "nam", "trung_tinh"}
REGISTER = {"lich_su", "trung_tinh", "suong_sa", "lan_man"}
LENGTH = {"ngan", "vua", "dai"}
REQUIRED = {
    "id", "utterance", "intent", "is_hard_negative", "sounds_like",
    "dialect", "register", "length_bucket", "state_hint", "notes",
}
_NEG_TEMPLATE = re.compile(r"\b(k phải|ko phải|không phải|chứ k|chớ k|chớ không|chứ không)\b", re.I)


def main() -> int:
    rows = [json.loads(l) for l in SRC.read_text(encoding="utf-8").splitlines() if l.strip()]
    errs: list[str] = []
    warns: list[str] = []
    per_intent = defaultdict(lambda: [0, 0])
    d_cnt, r_cnt, l_cnt = Counter(), Counter(), Counter()
    ids, norms = [], defaultdict(list)
    hard_total = hard_templated = 0

    for i, r in enumerate(rows, 1):
        rid = r.get("id", f"line{i}")
        if REQUIRED - set(r):
            errs.append(f"{rid}: missing {sorted(REQUIRED - set(r))}")
        if set(r) - REQUIRED:
            errs.append(f"{rid}: extra {sorted(set(r) - REQUIRED)}")
        ids.append(rid)
        if not re.fullmatch(r"FROZEN-\d{4}", str(rid)):
            errs.append(f"line {i}: bad id {rid!r}")
        it = r.get("intent")
        if it not in CATALOG:
            errs.append(f"{rid}: intent {it!r} not in 53-catalog")
        hn, sl = r.get("is_hard_negative"), r.get("sounds_like")
        if hn:
            hard_total += 1
            per_intent[it][1] += 1
            if sl is None or sl == it or sl not in CATALOG:
                errs.append(f"{rid}: bad sounds_like {sl!r}")
            if _NEG_TEMPLATE.search(r.get("utterance", "")):
                hard_templated += 1
        else:
            per_intent[it][0] += 1
            if sl is not None:
                errs.append(f"{rid}: sounds_like set on non-hard-negative")
        for field, allowed, ctr in (("dialect", DIALECT, d_cnt), ("register", REGISTER, r_cnt), ("length_bucket", LENGTH, l_cnt)):
            v = r.get(field)
            if v not in allowed:
                errs.append(f"{rid}: bad {field} {v!r}")
            else:
                ctr[v] += 1
        u = (r.get("utterance") or "").strip()
        if not u or "\n" in u:
            errs.append(f"{rid}: empty/multiline utterance")
        norm = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", u.lower())).strip()
        norms[norm].append(rid)

    for norm, group in norms.items():
        if len(group) > 1:
            errs.append(f"identical utterance {group}")

    by_intent = defaultdict(list)
    for r in rows:
        by_intent[r["intent"]].append((r["id"], set(re.sub(r"[^\w\s]", " ", r["utterance"].lower()).split())))
    for it, lst in by_intent.items():
        for a in range(len(lst)):
            for b in range(a + 1, len(lst)):
                sa, sb = lst[a][1], lst[b][1]
                if sa and sb and len(sa & sb) / len(sa | sb) >= 0.72:
                    warns.append(f"near-dup {lst[a][0]} ~ {lst[b][0]} [{it}]")

    dup = [x for x, c in Counter(ids).items() if c > 1]
    if dup:
        errs.append(f"duplicate ids: {dup}")

    N = len(rows)
    print(f"=== {SRC.name}: {N} rows ===")
    print(f"catalog: {len({r['intent'] for r in rows})}/53   missing: {sorted(CATALOG - {r['intent'] for r in rows}) or 'none'}")
    low = [it for it in CATALOG if not (per_intent[it][0] >= 6 and per_intent[it][1] >= 1)]
    print(f"intents below (>=6 pos, >=1 hardneg): {low or 'none'}")
    print(f"dialect  {dict(d_cnt)}   (bac/trung/nam each >=20% and <=40% of {N})")
    print(f"register {dict(r_cnt)}   (each >=15%)")
    print(f"length   {dict(l_cnt)}   (each >=20%)")
    print(f"hard negatives: {hard_total} ({hard_total / N:.0%});  "
          f"using explicit-negation template: {hard_templated}/{hard_total} ({hard_templated / max(1, hard_total):.0%})")
    print(f"\nERRORS ({len(errs)}):")
    for e in errs[:80]:
        print("  " + e)
    print(f"\nWARNINGS ({len(warns)}):")
    for w in warns[:60]:
        print("  " + w)
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
