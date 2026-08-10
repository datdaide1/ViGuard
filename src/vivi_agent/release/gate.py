"""Machine-checkable REL-01 release gate.

The gate deliberately separates Agent-owned checks from evidence owned by the
Guardrail and UI teams.  A green mock/contract suite can never be promoted to
proof that a real external integration passed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping, Sequence


REQUIRED_EXTERNAL_GATES = tuple(f"G-EXT-{number:02d}" for number in range(1, 7))
ACCEPTED_DEPENDENCY_STATUSES = frozenset({"done", "completed"})
REQUIRED_DEPENDENCIES = (
    "CON-01", "CON-02", "CAT-01", "TOOL-01", "MAP-01", "MOD-01",
    "ORC-01", "GRD-ADP-01", "VEH-01", "VEH-02", "EXEC-01", "EXEC-02",
    "EVT-01", "E2E-01", "MAP-02", "EXEC-03", "BEH-01", "QRY-01",
    "RSP-01", "CNF-01", "ACTV-01", "MON-ADP-01", "SIM-01", "COV-01",
    "INT-01", "INT-02", "HERO-01", "HERO-02", "HERO-03", "HERO-04",
    "SCN-01", "SCN-02", "SCN-03", "EVAL-01", "EVAL-02", "PERF-01",
    "OPS-01", "DOC-01",
)


class ReleaseStatus(str, Enum):
    PASS = "PASS"
    NOT_READY = "NOT_READY"


class EvidenceError(ValueError):
    """Raised when external evidence is malformed or over-claims ownership."""


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ReleaseResult:
    status: ReleaseStatus
    integrated_demo_status: ReleaseStatus
    commit: str
    generated_at: str
    checks: tuple[CheckResult, ...]

    @property
    def blockers(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["integrated_demo_status"] = self.integrated_demo_status.value
        return payload


CommandRunner = Callable[[Sequence[str], Path, Mapping[str, str]], subprocess.CompletedProcess[str]]


def _run_command(command: Sequence[str], cwd: Path, env: Mapping[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=dict(env), text=True, capture_output=True, check=False)


def _parse_tracker_statuses(text: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    current_id: str | None = None
    for line in text.splitlines():
        id_match = re.match(r"^  - id:\s*([A-Z0-9-]+)\s*$", line)
        if id_match:
            current_id = id_match.group(1)
            continue
        status_match = re.match(r"^    status:\s*([a-z_]+)\s*$", line)
        if current_id and status_match:
            statuses[current_id] = status_match.group(1)
    return statuses


def _load_external_evidence(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"Cannot read external evidence: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) - set(REQUIRED_EXTERNAL_GATES):
        raise EvidenceError("External evidence must be an object keyed only by G-EXT-01..G-EXT-06")
    validated: dict[str, dict[str, str]] = {}
    for gate_id, evidence in payload.items():
        if not isinstance(evidence, dict):
            raise EvidenceError(f"{gate_id} evidence must be an object")
        required = {"status", "owner", "artifact", "sha256"}
        if set(evidence) != required or evidence.get("status") != "accepted":
            raise EvidenceError(f"{gate_id} must contain accepted status, owner, artifact and sha256")
        artifact = Path(str(evidence["artifact"]))
        if not artifact.is_absolute():
            artifact = path.parent / artifact
        if not artifact.is_file():
            raise EvidenceError(f"{gate_id} artifact does not exist: {artifact}")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if digest != evidence["sha256"]:
            raise EvidenceError(f"{gate_id} artifact digest mismatch")
        validated[gate_id] = {key: str(value) for key, value in evidence.items()}
    return validated


class ReleaseGate:
    """Evaluate all REL-01 preconditions without mutating runtime state."""

    def __init__(self, repo_root: Path, runner: CommandRunner = _run_command) -> None:
        self.repo_root = repo_root.resolve()
        self.runner = runner

    def evaluate(self, external_evidence_path: Path | None = None) -> ReleaseResult:
        commit = self._git_value("rev-parse", "HEAD")
        checks: list[CheckResult] = []
        statuses = _parse_tracker_statuses(
            (self.repo_root / "VIVI_AGENT_TASK_TRACKER.yaml").read_text(encoding="utf-8")
        )
        incomplete = [
            f"{task_id}={statuses.get(task_id, 'missing')}"
            for task_id in REQUIRED_DEPENDENCIES
            if statuses.get(task_id) not in ACCEPTED_DEPENDENCY_STATUSES
        ]
        checks.append(CheckResult("dependencies", not incomplete, "all complete" if not incomplete else ", ".join(incomplete)))

        try:
            evidence = _load_external_evidence(external_evidence_path)
            missing = [gate_id for gate_id in REQUIRED_EXTERNAL_GATES if gate_id not in evidence]
            checks.append(CheckResult("external-evidence", not missing, "all accepted" if not missing else "missing: " + ", ".join(missing)))
        except EvidenceError as exc:
            checks.append(CheckResult("external-evidence", False, str(exc)))

        env = os.environ.copy()
        env.update({"PYTHONPATH": ".;src", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
        command = [sys.executable, "-m", "pytest", "-q", "--import-mode=importlib"]
        completed = self.runner(command, self.repo_root, env)
        output = (completed.stdout + "\n" + completed.stderr).strip()
        detail = "pytest passed" if completed.returncode == 0 else f"pytest exit={completed.returncode}: {output[-1200:]}"
        checks.append(CheckResult("automated-test-suite", completed.returncode == 0, detail))

        clean = self.runner(["git", "diff", "--quiet", "--", "."], self.repo_root, env)
        checks.append(CheckResult("tracked-worktree", clean.returncode == 0, "clean" if clean.returncode == 0 else "tracked changes present"))
        agent_check_ids = {"automated-test-suite", "tracked-worktree"}
        agent_ready = all(check.passed for check in checks if check.check_id in agent_check_ids)
        external_ready = next(check.passed for check in checks if check.check_id == "external-evidence")
        status = ReleaseStatus.PASS if agent_ready else ReleaseStatus.NOT_READY
        integrated_status = ReleaseStatus.PASS if agent_ready and external_ready else ReleaseStatus.NOT_READY
        return ReleaseResult(status, integrated_status, commit, datetime.now(timezone.utc).isoformat(), tuple(checks))

    def _git_value(self, *arguments: str) -> str:
        result = self.runner(["git", *arguments], self.repo_root, os.environ.copy())
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git command failed")
        return result.stdout.strip()


def render_report(result: ReleaseResult) -> str:
    rows = "\n".join(
        f"| `{check.check_id}` | {'PASS' if check.passed else 'BLOCKED'} | {check.detail.replace('|', '/').replace(chr(10), ' ')} |"
        for check in result.checks
    )
    return f"""# Agent Release Report (REL-01)\n\n- Agent release status: **{result.status.value}**\n- Integrated demo status: **{result.integrated_demo_status.value}**\n- Commit: `{result.commit}`\n- Generated (UTC): `{result.generated_at}`\n\n| Gate | Result | Evidence / blocker |\n|---|---|---|\n{rows}\n\nThe Agent build may be frozen when `Agent release status` is `PASS`. External evidence affects only `Integrated demo status`; Guardrail policy correctness and UI visual quality remain owned and signed off by their respective teams.\n"""
