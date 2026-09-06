"""Phase 1' metrics — intent classifier + full pipeline vs the golden dataset.

Two numbers:
  1. intent accuracy   — classifier(utterance) vs the labelled intent
  2. pipeline accuracy  — PolicyEngine(classified intent, state) outcome vs
                          expected_outcome (the real end-to-end number)

T2 (PhoBERT semantic fallback) runs only if ``model/model.onnx`` + onnxruntime
+ pyvi are present; otherwise this is a T1-only baseline (reported as such).

Usage:  py -3 vf_guardrails/evals/run_classifier.py [--md OUT.md]
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
sys.path.insert(0, str(_REPO / "vf_guardrails"))

from policy import PolicyEngine, RuleSet, VehicleState  # noqa: E402
from policy.state import REQUEST_PARAMS  # noqa: E402
from src.intent_classifier import IntentClassifier  # noqa: E402

_DATASET = _REPO / "golden-dataset/driver-constraints/output/pipeline/dataset.jsonl"
_KEYWORDS = _REPO / "vf_guardrails/config/intent_keywords.json"


def _pctile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * q))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", type=Path, default=_REPO / "docs/guardrail-integration/METRICS_PHASE1_CLASSIFIER.md")
    args = ap.parse_args()

    with contextlib.redirect_stdout(io.StringIO()):
        classifier = IntentClassifier(str(_KEYWORDS))
    t2_on = classifier.model_loaded

    ruleset = RuleSet.load()
    engine = PolicyEngine(ruleset)
    mode_by_rule = {r.rule_id: r.check_mode for r in ruleset.all()}
    rows = [json.loads(l) for l in _DATASET.read_text(encoding="utf-8").splitlines() if l.strip()]

    n = len(rows)
    intent_ok = 0
    pipe_ok = 0
    unknown = 0
    per_intent = defaultdict(lambda: [0, 0])       # recall: [ok, total]
    predicted_count = Counter()
    confusions = Counter()                         # (true, pred)
    lat_cls: list[float] = []
    pipe_confusion = Counter()                     # (expected, got)
    intent_errors: list[tuple] = []

    for row in rows:
        true_intent = row["intent"]
        t0 = time.perf_counter()
        pred = classifier.classify(row["utterance"])
        lat_cls.append((time.perf_counter() - t0) * 1000.0)
        predicted_count[pred] += 1
        if pred in ("INTENT_UNKNOWN", None):
            unknown += 1
        per_intent[true_intent][1] += 1
        hit = pred == true_intent
        intent_ok += hit
        per_intent[true_intent][0] += hit
        if not hit:
            confusions[(true_intent, pred)] += 1
            if len(intent_errors) < 60:
                intent_errors.append((row["sample_id"], true_intent, pred, row["utterance"][:60]))

        # end-to-end: feed the *predicted* intent into the engine
        vs = row.get("vehicle_state") or {}
        params = {k: v for k, v in vs.items() if k in REQUEST_PARAMS}
        state = VehicleState.from_partial({k: v for k, v in vs.items() if k not in REQUEST_PARAMS})
        if pred in ruleset.intents:
            d = engine.evaluate(
                pred, state,
                check_mode=mode_by_rule.get(row["rule_id"], "gate"),
                request_params=params,
            )
            got = d.outcome or f"FAIL:{d.reason_code}"
        else:
            got = "CLASSIFICATION_ERROR"
        pipe_ok += got == row["expected_outcome"]
        pipe_confusion[(row["expected_outcome"], got)] += 1

    lat_cls.sort()
    macro_f1_parts = []
    # precision needs predicted-true counts; recompute simple per-intent P/R/F1
    tp = Counter()
    for row in rows:
        pass
    # tp/fp/fn from confusions + per_intent
    for it in ruleset.intents:
        ok, tot = per_intent[it]
        pred_tot = predicted_count.get(it, 0)
        prec = ok / pred_tot if pred_tot else 0.0
        rec = ok / tot if tot else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        macro_f1_parts.append(f1)
    macro_f1 = sum(macro_f1_parts) / len(macro_f1_parts)

    L = []
    w = L.append
    w("# Phase 1' metrics — intent classifier + pipeline vs golden dataset")
    w("")
    w(f"> `vf_guardrails/evals/run_classifier.py` · {time.strftime('%Y-%m-%d %H:%M')} · {n} rows")
    w(f"> classifier tiers active: **T1{' + T2 (PhoBERT)' if t2_on else ' only (T2 model not loaded)'}**")
    w("")
    w("## Headline")
    w("")
    w("| metric | value |")
    w("|---|---|")
    w(f"| **intent accuracy** | **{intent_ok}/{n} = {intent_ok/n:.1%}** |")
    w(f"| macro-F1 (per intent) | {macro_f1:.3f} |")
    w(f"| INTENT_UNKNOWN rate | {unknown}/{n} = {unknown/n:.1%} |")
    w(f"| **pipeline outcome accuracy** (classified intent → engine) | **{pipe_ok}/{n} = {pipe_ok/n:.1%}** |")
    w(f"| classifier latency p50 / p95 / p99 | "
      f"{_pctile(lat_cls,.5):.2f} / {_pctile(lat_cls,.95):.2f} / {_pctile(lat_cls,.99):.2f} ms |")
    w("")
    w("## Per-intent recall (worst 20)")
    w("")
    w("| intent | recall | n |")
    w("|---|---|---|")
    for it in sorted(ruleset.intents, key=lambda k: per_intent[k][0] / max(1, per_intent[k][1]))[:20]:
        ok, tot = per_intent[it]
        w(f"| `{it}` | {ok/max(1,tot):.0%} | {tot} |")
    w("")
    w("## Top confusions (true → predicted)")
    w("")
    w("| true | predicted | n |")
    w("|---|---|---|")
    for (t, p), c in confusions.most_common(25):
        w(f"| `{t}` | `{p}` | {c} |")
    w("")
    w("## Pipeline mismatch confusion (expected → got)")
    w("")
    w("| expected | got | n |")
    w("|---|---|---|")
    for (e, g), c in pipe_confusion.most_common():
        if e != g:
            w(f"| {e} | {g} | {c} |")
    w("")
    w(f"## Intent errors — first {len(intent_errors)}")
    w("")
    w("| sample_id | true | predicted | utterance |")
    w("|---|---|---|---|")
    for sid, t, p, u in intent_errors:
        w(f"| {sid} | `{t}` | `{p}` | {u} |")

    L.append("")
    L.append("---")
    L.append("> Số liệu tự sinh (file này bị ghi đè mỗi lần chạy). Diễn giải + việc")
    L.append("> tiếp theo: `docs/guardrail-integration/STATUS.md`.")
    args.md.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:18]))
    print(f"\n... full report: {args.md.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
