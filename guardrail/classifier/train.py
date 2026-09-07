"""Train the T2 (TF-IDF) intent classifier on the golden pool and save it.

Decision: char_wb(2,5) + word(1,2) + LinearSVC, no abstain by default
(docs/DECISIONS.md). Evaluated only on the frozen
independent test set — see run_t2.py.

Usage:  py -3 guardrail/classifier/train.py [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .tfidf import TfidfIntentClassifier

_REPO = Path(__file__).resolve().parents[2]
_GOLDEN = _REPO / "golden-dataset/driver-constraints/output/pipeline/dataset.jsonl"
_DEFAULT_OUT = Path(__file__).resolve().parent / "model_tfidf.pkl"


def train(golden_path: Path = _GOLDEN) -> TfidfIntentClassifier:
    rows = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return TfidfIntentClassifier(estimator="svc", char_ngram=(2, 5), word_ngram=(1, 2)).fit(
        [r["utterance"] for r in rows], [r["intent"] for r in rows]
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = ap.parse_args()
    t0 = time.perf_counter()
    clf = train()
    clf.save(args.out)
    size_kb = args.out.stat().st_size / 1024
    print(f"trained in {time.perf_counter() - t0:.1f}s → {args.out.relative_to(_REPO)} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
