"""Metrics — intent classifier vs the FROZEN independent test set.

This is the leakage-free classifier metric (see
docs/METRICS.md). T1 is hand-authored
keywords (not trained) so running it here has no train/eval leakage; a trained
T2 MUST also be measured here, never on a split of the golden pool.

Reports intent accuracy overall / positive-only / hard-negative-only, per-intent
recall, top confusions, and tier usage.

TODO(phase 2'): parse `state_hint` -> VehicleState -> PolicyEngine to also
report end-to-end outcome accuracy on this set. Not needed yet — the constraint
engine is already at 100% on the golden dataset (METRICS_PHASE1.md).

Usage:  py -3 guardrail/evals/run_frozen.py [--md OUT.md]
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "guardrail"))

from classifier.keyword import IntentClassifier  # noqa: E402

_FROZEN = _REPO / "guardrail/evals/data/frozen_testset.jsonl"
_KEYWORDS = _REPO / "guardrail/config/intent_keywords.json"
_RULES = _REPO / "golden-dataset/driver-constraints/data/rules.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", type=Path, default=_FROZEN)
    ap.add_argument("--md", type=Path, default=_REPO / "docs/metrics/classifier-frozen-t1.md")
    args = ap.parse_args()

    catalog = {r["intent"] for r in json.loads(_RULES.read_text(encoding="utf-8"))}
    with contextlib.redirect_stdout(io.StringIO()):
        clf = IntentClassifier(str(_KEYWORDS))
    t2_on = False  # T1 is keyword-only; T2 is classifier/tfidf.py

    rows = [json.loads(l) for l in args.frozen.read_text(encoding="utf-8").splitlines() if l.strip()]
    n = len(rows)

    ok = ok_pos = tot_pos = ok_hn = tot_hn = unknown = 0
    per_recall = defaultdict(lambda: [0, 0])
    pred_count = Counter()
    confusion = Counter()
    errs: list[tuple] = []
    lat: list[float] = []

    for r in rows:
        t = r["intent"]
        assert t in catalog, f"{r['id']}: intent {t} not in catalog"
        t0 = time.perf_counter()
        p = clf.classify(r["utterance"])
        lat.append((time.perf_counter() - t0) * 1000.0)
        pred_count[p] += 1
        hit = p == t
        ok += hit
        per_recall[t][0] += hit
        per_recall[t][1] += 1
        if p in ("INTENT_UNKNOWN", None):
            unknown += 1
        if r["is_hard_negative"]:
            tot_hn += 1
            ok_hn += hit
        else:
            tot_pos += 1
            ok_pos += hit
        if not hit:
            confusion[(t, p)] += 1
            if len(errs) < 80:
                errs.append((r["id"], t, p, r["utterance"]))

    macro_f1 = 0.0
    for it in catalog:
        c, tt = per_recall[it]
        pt = pred_count.get(it, 0)
        prec = c / pt if pt else 0.0
        rec = c / tt if tt else 0.0
        macro_f1 += 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    macro_f1 /= len(catalog)

    lat.sort()
    q = lambda x: lat[min(len(lat) - 1, int(len(lat) * x))] if lat else 0.0

    L: list[str] = []
    w = L.append
    w("# Engine metrics — intent classifier vs FROZEN independent test set")
    w("")
    w(f"> `guardrail/evals/run_frozen.py` · {time.strftime('%Y-%m-%d %H:%M')} · {n} rows "
      f"({tot_pos} positive + {tot_hn} hard-negative)")
    w(f"> tiers: **T1{' + T2' if t2_on else ' only (T2 model not loaded)'}**")
    w("> Leakage-free: T1 is hand-authored keywords (not trained). A trained T2 must also run here.")
    w("")
    w("| metric | value |")
    w("|---|---|")
    w(f"| **intent accuracy (all)** | **{ok}/{n} = {ok/n:.1%}** |")
    w(f"| intent accuracy (positive only) | {ok_pos}/{tot_pos} = {ok_pos/tot_pos:.1%} |")
    w(f"| intent accuracy (hard-negative only) | {ok_hn}/{tot_hn} = {ok_hn/tot_hn:.1%} |")
    w(f"| macro-F1 | {macro_f1:.3f} |")
    w(f"| INTENT_UNKNOWN rate | {unknown}/{n} = {unknown/n:.1%} |")
    w(f"| classifier latency p50 / p95 / p99 | {q(.5):.2f} / {q(.95):.2f} / {q(.99):.2f} ms |")
    w("")
    w("## Per-intent recall (worst 20)")
    w("")
    w("| intent | recall | n |")
    w("|---|---|---|")
    for it in sorted(catalog, key=lambda k: per_recall[k][0] / max(1, per_recall[k][1]))[:20]:
        c, tt = per_recall[it]
        w(f"| `{it}` | {c/max(1,tt):.0%} | {tt} |")
    w("")
    w("## Top confusions (true → predicted)")
    w("")
    w("| true | predicted | n |")
    w("|---|---|---|")
    for (t, p), c in confusion.most_common(25):
        w(f"| `{t}` | `{p}` | {c} |")
    w("")
    w(f"## Errors — first {len(errs)}")
    w("")
    w("| id | true | predicted | utterance |")
    w("|---|---|---|---|")
    for rid, t, p, u in errs:
        w(f"| {rid} | `{t}` | `{p}` | {u} |")
    w("")
    w("---")
    w("> Generated — overwritten on each run. Interpretation and context:")
    w("> `docs/METRICS.md`.")

    args.md.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:16]))
    print(f"\n... full report: {args.md.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
