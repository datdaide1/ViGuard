from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from src.vivi_agent import RUNTIME_INTENT_MANIFEST
from src.vivi_agent.catalog.manifest import (
    APPROVED_INTENTS,
    MANIFEST_PATH,
    MONITORED_INTENTS,
    CatalogReadinessError,
    load_manifest,
    manifest_checksum,
    validate_manifest,
)


class IntentManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = json.loads(Path(MANIFEST_PATH).read_text(encoding="utf-8"))

    def resigned(self, raw: dict[str, object]) -> dict[str, object]:
        raw["checksum"] = manifest_checksum(raw)
        return raw

    def test_checked_in_manifest_is_ready_with_exact_53_intents(self) -> None:
        manifest = load_manifest()
        self.assertEqual(len(manifest.intents), 53)
        self.assertEqual({item.intent for item in manifest.intents}, APPROVED_INTENTS)
        self.assertEqual(sum(item.is_action for item in manifest.intents), 47)
        self.assertEqual(sum(item.is_query for item in manifest.intents), 6)

    def test_runtime_package_validates_manifest_at_import_startup(self) -> None:
        self.assertEqual(RUNTIME_INTENT_MANIFEST.checksum, self.raw["checksum"])
        self.assertEqual(len(RUNTIME_INTENT_MANIFEST.intents), 53)

    def test_source_casing_and_explicit_refusal_are_preserved(self) -> None:
        manifest = load_manifest()
        self.assertIn("OPEN_BONNET", APPROVED_INTENTS)
        self.assertIn("AD_WIPER_MAX", APPROVED_INTENTS)
        refusal = manifest.by_intent("deactivate_esc")
        self.assertEqual(refusal.kind, "refusal")
        self.assertEqual(refusal.behavior_category, "explicit_refusal")

    def test_monitor_capability_matches_guardrail_metadata_without_policy(self) -> None:
        manifest = load_manifest()
        monitored = {item.intent for item in manifest.intents if item.monitor_capable}
        self.assertEqual(monitored, MONITORED_INTENTS)
        serialized = json.dumps(self.raw, ensure_ascii=False).lower()
        self.assertNotIn("condition", serialized)
        self.assertNotIn("outcome", serialized)

    def test_missing_or_extra_intent_fails_readiness(self) -> None:
        missing = copy.deepcopy(self.raw)
        missing["intents"].pop()
        with self.assertRaises(CatalogReadinessError) as missing_error:
            validate_manifest(self.resigned(missing))
        self.assertEqual(missing_error.exception.code, "INTENT_COVERAGE_MISMATCH")
        self.assertFalse(missing_error.exception.readiness)

        extra = copy.deepcopy(self.raw)
        extra["intents"].append(
            {
                "intent": "accelerate", "kind": "action", "domain_tool": "control_access",
                "behavior_category": "toggle", "required_parameters": [], "monitor_rule_ids": [],
                "sample_utterances": ["Tăng tốc"],
            }
        )
        with self.assertRaises(CatalogReadinessError) as extra_error:
            validate_manifest(self.resigned(extra))
        self.assertEqual(extra_error.exception.code, "INTENT_COVERAGE_MISMATCH")

    def test_duplicate_intent_fails_readiness(self) -> None:
        duplicate = copy.deepcopy(self.raw)
        duplicate["intents"].append(copy.deepcopy(duplicate["intents"][0]))
        with self.assertRaises(CatalogReadinessError) as raised:
            validate_manifest(self.resigned(duplicate))
        self.assertEqual(raised.exception.code, "DUPLICATE_INTENT")

    def test_tampering_without_new_checksum_fails_readiness(self) -> None:
        tampered = copy.deepcopy(self.raw)
        tampered["intents"][0]["sample_utterances"] = ["Mở cửa"]
        with self.assertRaises(CatalogReadinessError) as raised:
            validate_manifest(tampered)
        self.assertEqual(raised.exception.code, "MANIFEST_CHECKSUM_MISMATCH")

    def test_query_or_monitor_drift_fails_readiness(self) -> None:
        query_drift = copy.deepcopy(self.raw)
        query_drift["intents"][0]["kind"] = "query"
        query_drift["intents"][0]["behavior_category"] = "state_query"
        with self.assertRaises(CatalogReadinessError) as query_error:
            validate_manifest(self.resigned(query_drift))
        self.assertEqual(query_error.exception.code, "QUERY_COVERAGE_MISMATCH")

        monitor_drift = copy.deepcopy(self.raw)
        monitor_drift["intents"][0]["monitor_rule_ids"] = ["R001"]
        with self.assertRaises(CatalogReadinessError) as monitor_error:
            validate_manifest(self.resigned(monitor_drift))
        self.assertEqual(monitor_error.exception.code, "MONITOR_COVERAGE_MISMATCH")

    def test_unknown_domain_tool_fails_readiness(self) -> None:
        invalid = copy.deepcopy(self.raw)
        invalid["intents"][0]["domain_tool"] = "typo_tool"
        with self.assertRaises(CatalogReadinessError) as raised:
            validate_manifest(self.resigned(invalid))
        self.assertEqual(raised.exception.code, "INVALID_MANIFEST")

    def test_behavior_must_be_compatible_with_intent_kind(self) -> None:
        invalid = copy.deepcopy(self.raw)
        query = next(entry for entry in invalid["intents"] if entry["kind"] == "query")
        query["behavior_category"] = "toggle"
        with self.assertRaises(CatalogReadinessError) as raised:
            validate_manifest(self.resigned(invalid))
        self.assertEqual(raised.exception.code, "INVALID_MANIFEST")


if __name__ == "__main__":
    unittest.main()
