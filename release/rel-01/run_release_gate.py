#!/usr/bin/env python3
"""Run REL-01 and write auditable JSON/Markdown outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vivi_agent.release.gate import ReleaseGate, ReleaseStatus, render_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-evidence", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("release/rel-01/evidence"))
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    result = ReleaseGate(REPO_ROOT).evaluate(args.external_evidence)
    result_path = output_dir / "release-result.json"
    report_path = output_dir / "AGENT_RELEASE_REPORT.md"
    result_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_report(result), encoding="utf-8")
    source_evidence = {
        "performance": REPO_ROOT / "tests/performance/perf-01/results/local_run.json",
        "release_result": result_path,
        "release_report": report_path,
    }
    manifest = {
        "schema_version": "1.0.0",
        "source_commit": result.commit,
        "agent_release_status": result.status.value,
        "test_command": [sys.executable, "-m", "pytest", "-q", "--import-mode=importlib"],
        "artifacts": {
            name: {"path": path.relative_to(REPO_ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for name, path in source_evidence.items()
        },
    }
    (output_dir / "FROZEN_AGENT_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"REL-01 Agent: {result.status.value}; integrated demo: {result.integrated_demo_status.value}")
    return 0 if result.status is ReleaseStatus.PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
