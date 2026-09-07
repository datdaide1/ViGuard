"""Recompute derived metadata on frozen_testset.jsonl (idempotent).

Currently: recomputes `length_bucket` from the utterance's whitespace-token
count, per FROZEN_TESTSET_SPEC.md (ngan ≤6, vua 7–15, dai >15). Leaves
utterance / intent / labels / dialect / register untouched.

Re-run this after any regeneration of rows. Prints a diff; pass --write to
apply in place.

Usage:  py -3 vf_guardrails/evals/fix_frozen_metadata.py [--write]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_FILE = _REPO / "vf_guardrails/evals/data/frozen_testset.jsonl"


def bucket(utterance: str) -> str:
    n = len(re.sub(r"[^\w\s]", " ", utterance).split())
    if n <= 6:
        return "ngan"
    if n <= 15:
        return "vua"
    return "dai"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--file", type=Path, default=_FILE)
    args = ap.parse_args()

    lines = args.file.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(l) for l in lines if l.strip()]
    changed = 0
    for r in rows:
        want = bucket(r["utterance"])
        if r.get("length_bucket") != want:
            print(f"  {r['id']}: length_bucket {r.get('length_bucket')!r} -> {want!r}  "
                  f"({len(re.sub(chr(0), '', r['utterance']).split())}w) {r['utterance'][:55]!r}")
            r["length_bucket"] = want
            changed += 1

    print(f"\n{changed} rows would change length_bucket." if not args.write else f"\n{changed} rows updated.")
    if args.write and changed:
        args.file.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
