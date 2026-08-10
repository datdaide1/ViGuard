from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from vivi_agent.release.gate import (
    REQUIRED_DEPENDENCIES,
    REQUIRED_EXTERNAL_GATES,
    ReleaseGate,
    ReleaseStatus,
    _load_external_evidence,
    _parse_tracker_statuses,
    render_report,
)


class FakeRunner:
    def __init__(self, pytest_exit: int = 0, clean_exit: int = 0) -> None:
        self.pytest_exit = pytest_exit
        self.clean_exit = clean_exit

    def __call__(self, command, cwd, env):
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(command, 0, "abc123\n", "")
        if command[:3] == ["git", "diff", "--quiet"]:
            return subprocess.CompletedProcess(command, self.clean_exit, "", "")
        return subprocess.CompletedProcess(command, self.pytest_exit, "tests passed", "failure")


class ReleaseGateTests(unittest.TestCase):
    def _repo(self, root: Path, status: str = "completed") -> None:
        tracker = "\n".join(f"  - id: {task}\n    status: {status}" for task in REQUIRED_DEPENDENCIES)
        (root / "VIVI_AGENT_TASK_TRACKER.yaml").write_text(tracker, encoding="utf-8")

    def _evidence(self, root: Path) -> Path:
        payload = {}
        for gate_id in REQUIRED_EXTERNAL_GATES:
            artifact = root / f"{gate_id}.json"
            artifact.write_text(f'{{"gate":"{gate_id}"}}', encoding="utf-8")
            payload[gate_id] = {"status": "accepted", "owner": "external-team", "artifact": artifact.name, "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
        evidence = root / "external.json"
        evidence.write_text(json.dumps(payload), encoding="utf-8")
        return evidence

    def test_tracker_parser_reads_task_statuses(self) -> None:
        self.assertEqual(_parse_tracker_statuses("  - id: CON-01\n    status: done"), {"CON-01": "done"})

    def test_stale_dependency_metadata_does_not_block_executable_agent_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._repo(root, status="review")
            result = ReleaseGate(root, FakeRunner()).evaluate()
        dependency = next(check for check in result.checks if check.check_id == "dependency-metadata")
        self.assertTrue(dependency.passed)
        self.assertIn("non-blocking tracker metadata", dependency.detail)
        self.assertEqual(result.status, ReleaseStatus.PASS)

    def test_missing_external_evidence_does_not_block_agent_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._repo(root)
            result = ReleaseGate(root, FakeRunner()).evaluate()
        self.assertEqual(result.status, ReleaseStatus.PASS)
        self.assertEqual(result.integrated_demo_status, ReleaseStatus.NOT_READY)
        external = next(check for check in result.checks if check.check_id == "external-evidence")
        self.assertIn("G-EXT-02", external.detail)

    def test_all_inputs_pass_and_report_preserves_ownership_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._repo(root)
            result = ReleaseGate(root, FakeRunner()).evaluate(self._evidence(root))
        self.assertEqual(result.status, ReleaseStatus.PASS)
        self.assertEqual(result.integrated_demo_status, ReleaseStatus.PASS)
        report = render_report(result)
        self.assertIn("Agent build may be frozen", report)
        self.assertIn("remain owned and signed off", report)

    def test_tampered_external_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self._evidence(root)
            (root / "G-EXT-06.json").write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                _load_external_evidence(evidence)

    def test_failed_test_suite_blocks_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._repo(root)
            result = ReleaseGate(root, FakeRunner(pytest_exit=1)).evaluate(self._evidence(root))
        self.assertEqual(result.status, ReleaseStatus.NOT_READY)
        self.assertTrue(any(check.check_id == "automated-test-suite" for check in result.blockers))


if __name__ == "__main__":
    unittest.main()
