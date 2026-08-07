#!/usr/bin/env python3
"""EVAL-01 — live evaluation CLI entry point.

Runs the real dataset against a real provider over the network. This is a
manual/CI-scheduled script, not part of the offline pytest suite (see the
module docstring in ``transports.py`` for why the network boundary is kept
out of ``dataset.py``/``scoring.py``/``runner.py``).

Usage (from repo root)::

    py -3 evals/eval-01/run_live_eval.py --provider gemini --model gemini-3.5-flash-lite \\
        --rpm 12 --out evals/eval-01/results/gemini_run.json

Reads ``GEMINI_API_KEY`` / ``OPENAI_API_KEY`` from the process environment,
falling back to a ``.env`` file at the repo root (simple ``KEY=VALUE`` lines,
no external dependency — real environment variables always win over
``.env``). A provider with no configured key is skipped cleanly (each item
scored as "skipped: missing API key"), never fabricated.

``--rpm`` paces requests to stay under the target account's real rate limit
— default 12 req/min, a safety margin under Gemini's free-tier 15 rpm for
lite models. Choose the number that matches the account actually running
this, not the theoretical provider limit.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (str(REPO_ROOT / "src"), str(REPO_ROOT), str(Path(__file__).resolve().parent)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _load_dotenv(path: Path) -> None:
    """Minimal ``.env`` loader — real environment variables always win."""
    import os

    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    _load_dotenv(REPO_ROOT / ".env")

    import os

    from vivi_agent.model_providers import GeminiAdapter, OpenAIAdapter
    from vivi_agent.tools.registry import load_registry

    from dataset import DATASET
    from runner import EvalRunner
    from transports import GeminiRestTransport, OpenAIRestTransport

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["openai", "gemini"], required=True)
    parser.add_argument("--model", required=True, help="Real provider model ID to call, e.g. gemini-3.5-flash-lite")
    parser.add_argument("--rpm", type=float, default=12.0, help="Requests per minute cap (default: 12)")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--out", required=True, help="Path to write raw JSON results")
    parser.add_argument(
        "--limit", type=int, default=None, help="Only run the first N dataset items (smoke-test / debugging)"
    )
    args = parser.parse_args()

    registry = load_registry()

    if args.provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            print("GEMINI_API_KEY is not set — nothing to run.", file=sys.stderr)
            return 1
        transport = GeminiRestTransport(api_key)
        adapter = GeminiAdapter(
            model_id=args.model,
            api_key=api_key,
            registry=registry,
            transport=transport,
            config_checksum="sha256:" + "0" * 64,
            timeout_seconds=args.timeout_seconds,
        )
    else:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            print("OPENAI_API_KEY is not set — nothing to run.", file=sys.stderr)
            return 1
        transport = OpenAIRestTransport(api_key)
        adapter = OpenAIAdapter(
            model_id=args.model,
            api_key=api_key,
            registry=registry,
            transport=transport,
            config_checksum="sha256:" + "0" * 64,
            timeout_seconds=args.timeout_seconds,
        )

    if args.rpm <= 0:
        print(f"--rpm must be positive, got {args.rpm}", file=sys.stderr)
        return 1

    items = DATASET if args.limit is None else DATASET[: args.limit]
    pace_seconds = 60.0 / args.rpm

    total = len(items)
    started_at = time.time()
    progress_count = [0]

    def _progress(item, outcome) -> None:
        progress_count[0] += 1
        if outcome.skipped_reason is not None:
            status, detail = "SKIPPED", outcome.skipped_reason
        elif outcome.error_code:
            status, detail = "ERROR", outcome.error_code
        else:
            status, detail = "OK", outcome.proposal_kind or ""
        print(f"[{progress_count[0]}/{total}] {item.item_id} -> {status} {detail}", file=sys.stderr, flush=True)

    runner = EvalRunner(adapter, pace_seconds=pace_seconds, on_item=_progress)
    outcomes = runner.run(items)

    elapsed_s = time.time() - started_at
    result_payload = {
        "provider": args.provider,
        "model_id": args.model,
        "rpm": args.rpm,
        "item_count": len(items),
        "elapsed_seconds": round(elapsed_s, 1),
        "outcomes": [
            {
                "item_id": o.item_id,
                "provider": o.provider,
                "latency_ms": o.latency_ms,
                "proposal_kind": o.proposal_kind,
                "tool": o.tool,
                "arguments": dict(o.arguments) if o.arguments is not None else None,
                "text": o.text,
                "error_code": o.error_code,
                "error_detail": o.error_detail,
                "skipped_reason": o.skipped_reason,
            }
            for o in outcomes
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(outcomes)} outcomes to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
