"""Phase 1' — PhoBERT T2 candidate. Train on golden pool, eval on FROZEN.

CANNOT run in the repo's default env (E:\\anaconda3 has a broken torch/
transformers DLL). Run it in a clean venv:

    py -3 -m venv .venv-phobert
    .venv-phobert\\Scripts\\activate          # Windows
    pip install "sentence-transformers>=3" "scikit-learn" "numpy"
    python vf_guardrails/evals/run_t2_phobert.py

It downloads `dangvantuan/vietnamese-embedding` (~500 MB, PhoBERT-base sentence
model) on first run. Embeds 2,313 golden + 530 frozen utterances (CPU: a few
minutes), fits a linear SVM on the embeddings — the SAME classifier head as the
TF-IDF candidate, only the features differ — and reports on the frozen set so
the two are directly comparable.

Output: docs/guardrail-integration/METRICS_PHASE1_T2_PHOBERT.md
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
_GOLDEN = _REPO / "golden-dataset/driver-constraints/output/pipeline/dataset.jsonl"
_FROZEN = _REPO / "vf_guardrails/evals/data/frozen_testset.jsonl"
_MD = _REPO / "docs/guardrail-integration/METRICS_PHASE1_T2_PHOBERT.md"
_MODEL = "dangvantuan/vietnamese-embedding"


def _rows(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _acc(rows, preds) -> tuple[int, int, int, int, int]:
    ok = ok_pos = tot_pos = ok_hn = tot_hn = 0
    for r, p in zip(rows, preds):
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
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.svm import LinearSVC
    except Exception as exc:  # pragma: no cover - env guard
        print(f"Missing deps ({exc}). See the module docstring for the venv setup.")
        return 1

    try:
        from pyvi import ViTokenizer
        seg = ViTokenizer.tokenize
    except Exception:
        print("[warn] pyvi not available — PhoBERT expects word-segmented input; "
              "install `pyvi` for the intended result.")
        seg = lambda s: s  # noqa: E731

    train, frozen = _rows(_GOLDEN), _rows(_FROZEN)
    n = len(frozen)

    model = SentenceTransformer(_MODEL)
    t0 = time.perf_counter()
    Xtr = model.encode([seg(r["utterance"]) for r in train], batch_size=64,
                       show_progress_bar=True, normalize_embeddings=True)
    Xfz = model.encode([seg(r["utterance"]) for r in frozen], batch_size=64,
                       show_progress_bar=True, normalize_embeddings=True)
    embed_s = time.perf_counter() - t0

    ytr = [r["intent"] for r in train]
    clf = LinearSVC(C=1.0, class_weight="balanced").fit(Xtr, ytr)
    preds = clf.predict(Xfz)

    ok, okp, tp, okh, th = _acc(frozen, preds)
    conf = Counter((r["intent"], p) for r, p in zip(frozen, preds) if p != r["intent"])

    L = [
        "# Phase 1' — PhoBERT T2 candidate (trained on golden pool, evaluated on FROZEN)",
        "",
        f"> `vf_guardrails/evals/run_t2_phobert.py` · {time.strftime('%Y-%m-%d %H:%M')} · "
        f"model `{_MODEL}` · embed {embed_s:.0f}s",
        f"> eval: {n} frozen rows ({tp} positive + {th} hard-negative)",
        "> Classifier head = LinearSVC on sentence embeddings (same head as the TF-IDF candidate).",
        "",
        "| metric | value |",
        "|---|---|",
        f"| **intent accuracy (all)** | **{ok / n:.1%}** |",
        f"| positive only | {okp / tp:.1%} |",
        f"| hard-negative only | {okh / th:.1%} |",
        "",
        "## Top confusions on frozen",
        "",
        "| true | predicted | n |",
        "|---|---|---|",
        *[f"| `{t}` | `{p}` | {c} |" for (t, p), c in conf.most_common(20)],
        "",
        "---",
        "> So sánh với TF-IDF: `METRICS_PHASE1_T2.md`. Kết luận: `STATUS.md`.",
    ]
    _MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
