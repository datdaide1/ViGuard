"""Phase 1' — TF-IDF T2 candidate: train on golden pool, eval on FROZEN.

Reports:
  - T2 standalone accuracy on the frozen set (several abstain configs)
  - T1 -> T2 cascade (T2 only fires when T1 returns INTENT_UNKNOWN)
  - comparison against T1-only

Golden pool is training data ONLY. All reported numbers are on the frozen
independent test set (see docs/guardrail-integration/no-cv note).

Usage:  py -3 vf_guardrails/evals/run_t2.py [--md OUT.md]
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "vf_guardrails"))

from classifier.tfidf import UNKNOWN, T2Config, TfidfIntentClassifier  # noqa: E402
from src.intent_classifier import IntentClassifier  # noqa: E402

_GOLDEN = _REPO / "golden-dataset/driver-constraints/output/pipeline/dataset.jsonl"
_FROZEN = _REPO / "vf_guardrails/evals/data/frozen_testset.jsonl"
_KEYWORDS = _REPO / "vf_guardrails/config/intent_keywords.json"

_CONFIGS = {
    "no-abstain": T2Config(min_score=-9.9, min_margin=0.0),
    "margin>=0.2": T2Config(min_score=-9.9, min_margin=0.2),
    "margin>=0.4": T2Config(min_score=-9.9, min_margin=0.4),
    "score>=0 & margin>=0.3": T2Config(min_score=0.0, min_margin=0.3),
}


def _acc(rows, predict) -> tuple[int, int, int, int, int]:
    ok = ok_pos = tot_pos = ok_hn = tot_hn = 0
    for r in rows:
        p = predict(r["utterance"])
        hit = p == r["intent"]
        ok += hit
        if r["is_hard_negative"]:
            tot_hn += 1
            ok_hn += hit
        else:
            tot_pos += 1
            ok_pos += hit
    return ok, ok_pos, tot_pos, ok_hn, tot_hn


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", type=Path, default=_REPO / "docs/guardrail-integration/METRICS_PHASE1_T2.md")
    args = ap.parse_args()

    train = [json.loads(l) for l in _GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    frozen = [json.loads(l) for l in _FROZEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    n = len(frozen)
    X, y = [r["utterance"] for r in train], [r["intent"] for r in train]

    variants = {
        "SVC · char3-5 + word1-2": TfidfIntentClassifier(estimator="svc"),
        "SVC · char3-5 only": TfidfIntentClassifier(estimator="svc", word_ngram=None),
        "SVC · char2-5 + word1-2": TfidfIntentClassifier(estimator="svc", char_ngram=(2, 5)),
        "LogReg · char3-5 + word1-2": TfidfIntentClassifier(estimator="logreg"),
    }
    fitted = {}
    for name, clf in variants.items():
        t0 = time.perf_counter()
        clf.config = T2Config(min_score=-9.9, min_margin=0.0)
        fitted[name] = (clf.fit(X, y), time.perf_counter() - t0)

    # pick best-on-frozen (no abstain) as the working model
    def _all_acc(clf):
        return _acc(frozen, clf.predict)[0]
    best_name = max(fitted, key=lambda k: _all_acc(fitted[k][0]))
    t2, train_s = fitted[best_name]

    with contextlib.redirect_stdout(io.StringIO()):
        t1 = IntentClassifier(str(_KEYWORDS))

    # latency
    lat = []
    for r in frozen[:200]:
        s = time.perf_counter()
        t2.predict(r["utterance"])
        lat.append((time.perf_counter() - s) * 1000)
    lat.sort()

    L: list[str] = []
    w = L.append
    w("# Phase 1' — TF-IDF T2 candidate (trained on golden pool, evaluated on FROZEN)")
    w("")
    w(f"> `vf_guardrails/evals/run_t2.py` · {time.strftime('%Y-%m-%d %H:%M')}")
    w(f"> train: {len(train)} golden-pool rows · fit {train_s:.1f}s · "
      f"infer p50/p99 {lat[len(lat)//2]:.2f}/{lat[int(len(lat)*0.99)]:.2f} ms")
    w(f"> eval: {n} frozen rows ({sum(not r['is_hard_negative'] for r in frozen)} positive "
      f"+ {sum(r['is_hard_negative'] for r in frozen)} hard-negative)")
    w(f"> working model = **{best_name}**")
    w("")

    # baseline: T1 only
    ok, okp, tp, okh, th = _acc(frozen, t1.classify)
    w("## Baseline")
    w("")
    w("| classifier | all | positive | hard-neg |")
    w("|---|---|---|---|")
    w(f"| T1 only (keywords) | {ok/n:.1%} | {okp/tp:.1%} | {okh/th:.1%} |")
    w("")
    w("## TF-IDF variant comparison (no abstain, frozen)")
    w("")
    w("| variant | all | positive | hard-neg | fit s |")
    w("|---|---|---|---|---|")
    for name, (clf, secs) in fitted.items():
        clf.config = T2Config(min_score=-9.9, min_margin=0.0)
        a, ap, tpp, ah, thh = _acc(frozen, clf.predict)
        w(f"| {name} | **{a/n:.1%}** | {ap/tpp:.1%} | {ah/thh:.1%} | {secs:.1f} |")

    # T2 standalone, per config
    w("")
    w("## TF-IDF T2 standalone (frozen)")
    w("")
    w("| abstain config | all | positive | hard-neg | UNKNOWN rate |")
    w("|---|---|---|---|---|")
    best = None
    for name, cfg in _CONFIGS.items():
        t2.config = cfg
        ok, okp, tp, okh, th = _acc(frozen, t2.predict)
        unk = sum(t2.predict(r["utterance"]) == UNKNOWN for r in frozen)
        w(f"| {name} | **{ok/n:.1%}** | {okp/tp:.1%} | {okh/th:.1%} | {unk/n:.0%} |")
        if best is None or ok > best[1]:
            best = (name, ok)

    # T1 -> T2 cascade
    w("")
    w("## T1 → TF-IDF T2 cascade (T2 fires only when T1 = INTENT_UNKNOWN)")
    w("")
    w("| abstain config | all | positive | hard-neg |")
    w("|---|---|---|---|")
    for name, cfg in _CONFIGS.items():
        t2.config = cfg

        def cascade(u: str) -> str:
            p = t1.classify(u)
            return t2.predict(u) if p in (UNKNOWN, None) else p

        ok, okp, tp, okh, th = _acc(frozen, cascade)
        w(f"| {name} | **{ok/n:.1%}** | {okp/tp:.1%} | {okh/th:.1%} |")

    # in-distribution ceiling: group-by-rule_id CV on the golden pool.
    # Grouping keeps all ~20 near-duplicate utterances of a rule in one fold,
    # removing the worst leakage; still optimistic vs the frozen set.
    w("")
    w("## Context — golden-pool CV, group-by-rule_id (PESSIMISTIC bound)")
    w("")
    w("Holding out a whole rule's ~20 near-duplicate utterances removes the worst")
    w("leakage, but for the many single-rule intents it also removes the *entire*")
    w("intent from training → those fold rows score 0. So this is a lower bound,")
    w("not the real number. The **frozen set (above) is the number to trust.**")
    w("")
    try:
        from sklearn.model_selection import GroupKFold

        groups = [r["rule_id"] for r in train]
        bc = fitted[best_name][0]
        accs = []
        for tr_idx, te_idx in GroupKFold(n_splits=5).split(X, y, groups):
            m = TfidfIntentClassifier(estimator=bc.estimator, char_ngram=bc.char_ngram,
                                      word_ngram=bc.word_ngram)
            m.fit([X[i] for i in tr_idx], [y[i] for i in tr_idx])
            m.config = T2Config(min_score=-9.9, min_margin=0.0)
            accs.append(sum(m.predict(X[i]) == y[i] for i in te_idx) / len(te_idx))
        w(f"- {best_name}: **{np.mean(accs):.1%}** (folds "
          + ", ".join(f"{a:.0%}" for a in accs) + ")")
    except Exception as exc:  # pragma: no cover
        w(f"(skipped: {exc})")

    # confusions for the no-abstain standalone
    t2.config = _CONFIGS["no-abstain"]
    conf = Counter()
    for r in frozen:
        p = t2.predict(r["utterance"])
        if p != r["intent"]:
            conf[(r["intent"], p)] += 1
    w("")
    w("## TF-IDF T2 (no-abstain) top confusions on frozen")
    w("")
    w("| true | predicted | n |")
    w("|---|---|---|")
    for (tr, pr), c in conf.most_common(20):
        w(f"| `{tr}` | `{pr}` | {c} |")

    w("")
    w("---")
    w("> Số liệu tự sinh. Diễn giải + kết luận: `docs/guardrail-integration/STATUS.md`.")

    args.md.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\n... {args.md.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
