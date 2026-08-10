from __future__ import annotations

import unittest

from src.vivi_agent import RUNTIME_INTENT_MANIFEST, RUNTIME_TOOL_MAPPER
from src.vivi_agent.catalog import IntentDefinition, IntentManifest, load_manifest
from src.vivi_agent.tools.mapping import (
    DEFAULT_MAPPING_RULES,
    MappingReadinessError,
    MappingRule,
    ToolMapper,
    UnsupportedToolMappingError,
    build_coverage_report,
)
from src.vivi_agent.tools.registry import load_registry


def proposal(arguments: dict[str, str] | None = None, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_version": "1.0.0",
        "proposal_id": "prop-001",
        "session_id": "session-001",
        "source_turn_id": "turn-001",
        "tool": "control_access",
        "arguments": arguments or {"action": "open", "target": "driver_door"},
        "model_provider": "openai",
        "model_id": "gpt-5-mini",
    }
    payload.update(overrides)
    return payload


def minimal_manifest(*intents: tuple[str, str, str]) -> IntentManifest:
    """Build a tiny IntentManifest fixture for isolated mapper tests.

    Bypasses the closed-catalog checks in ``validate_manifest`` (approved
    53-intent allowlist, checksum, ...) since these tests only exercise
    `ToolMapper` against a deliberately reduced catalog, independent of the
    real 53-intent baseline.
    """
    definitions = tuple(
        IntentDefinition(
            intent=intent,
            kind="action",
            domain_tool=domain_tool,
            behavior_category=behavior_category,
            required_parameters=(),
            monitor_rule_ids=(),
            sample_utterances=("test utterance",),
        )
        for intent, domain_tool, behavior_category in intents
    )
    return IntentManifest("1.0.0", "test-fixture", "sha256:" + "0" * 64, definitions)


class ToolMapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Loaded once per class instead of per test: load_registry()/
        # load_manifest() each do a file read + JSON parse + checksum hash +
        # full schema/coverage validation, which several tests below need a
        # fresh copy of (to build a scoped ToolMapper) but don't need to
        # re-derive from disk every time.
        cls.registry = load_registry()
        cls.manifest = load_manifest()
        cls.mapper = ToolMapper(cls.registry, cls.manifest)

    def test_runtime_loads_full_baseline_and_candidate_coverage(self) -> None:
        self.assertEqual(len(RUNTIME_TOOL_MAPPER.rules), 148)
        mapped_intents = {rule.intent for rule in RUNTIME_TOOL_MAPPER.rules}
        manifest_intents = {definition.intent for definition in RUNTIME_INTENT_MANIFEST.intents}
        # Set equality also proves exact-casing preservation (e.g. OPEN_BONNET,
        # AD_WIPER_MAX, SHIFT_GEAR_REVERSE, turnoff_LKA): a casing mistake
        # would fail startup readiness (UNKNOWN_MAPPING_INTENT) long before
        # this assertion runs.
        self.assertEqual(mapped_intents, manifest_intents)
        self.assertEqual(len(manifest_intents), 123)

    def test_valid_call_maps_to_one_canonical_intent_and_event(self) -> None:
        result = self.mapper.map_proposal(proposal())
        self.assertEqual(result.canonical_action.intent, "open_door")
        self.assertEqual(result.canonical_action.behavior_id, "access_mutation")
        self.assertEqual(
            dict(result.canonical_action.normalized_arguments),
            {"action": "open", "target": "driver_door"},
        )
        self.assertEqual(result.event.source_tool, "control_access")
        self.assertEqual(result.event.canonical_intent, "open_door")
        self.assertEqual(result.event.proposal_digest, result.proposal_digest)
        with self.assertRaises(TypeError):
            result.canonical_action.normalized_arguments["target"] = "trunk"  # type: ignore[index]

    def test_canonical_proposal_has_stable_digest(self) -> None:
        first = self.mapper.map_proposal(
            proposal({"target": "driver_door", "action": "open"})
        )
        second = self.mapper.map_proposal(
            proposal(
                {"action": "open", "target": "driver_door"},
                model_provider="gemini",
                model_id="gemini-model",
            )
        )
        self.assertEqual(first.proposal_digest, second.proposal_digest)
        self.assertRegex(first.proposal_digest, r"^sha256:[0-9a-f]{64}$")

    def test_supported_registry_call_without_reviewed_mapping_does_not_fallback(self) -> None:
        # Full coverage (MAP-02) means every registry-valid combination now
        # has a reviewed mapping in DEFAULT_MAPPING_RULES, so there is no
        # longer any real "valid but unmapped" call to exercise self.mapper
        # with. This uses a deliberately reduced *manifest+rules* pair (the
        # coverage-completeness gate in _validate_rules requires the rules to
        # cover every manifest intent, so a real manifest can't pair with a
        # reduced rule set) while still going through the real, production
        # `load_registry()` -- the same registry validation `map_proposal`
        # runs against in production -- so this still exercises the real
        # lookup/no-fallback code path, just with a smaller intent catalog.
        scoped_manifest = minimal_manifest(("open_door", "control_access", "access_mutation"))
        scoped_mapper = ToolMapper(
            self.registry,
            scoped_manifest,
            (MappingRule("control_access", "open", "driver_door", "open_door"),),
        )
        with self.assertRaises(UnsupportedToolMappingError) as raised:
            scoped_mapper.map_proposal(proposal({"action": "open", "target": "trunk"}))
        self.assertEqual(raised.exception.code, "UNSUPPORTED_TOOL_MAPPING")
        self.assertFalse(raised.exception.execution_allowed)

    def test_invalid_and_incomplete_calls_are_blocked_before_mapping(self) -> None:
        cases = (
            (proposal({"action": "lock", "target": "driver_door"}), "INVALID_TARGET"),
            (proposal({"action": "open"}), "INCOMPLETE_TOOL_CALL"),
        )
        for payload, code in cases:
            with self.subTest(code=code), self.assertRaises(ValueError) as raised:
                self.mapper.map_proposal(payload)
            self.assertEqual(raised.exception.code, code)  # type: ignore[attr-defined]

    def test_malformed_proposal_identity_is_rejected_before_digest(self) -> None:
        cases = (
            ("proposal_id", 123),
            ("session_id", ""),
            ("source_turn_id", None),
        )
        for field, value in cases:
            with self.subTest(field=field), self.assertRaises(
                UnsupportedToolMappingError
            ) as raised:
                self.mapper.map_proposal(proposal(**{field: value}))
            self.assertEqual(raised.exception.code, "INVALID_ACTION_PROPOSAL")
            self.assertFalse(raised.exception.execution_allowed)

    def test_startup_validator_rejects_duplicate_rules(self) -> None:
        # Same key, same intent -- a redundant/copy-pasted row. Harmless in
        # effect but still an authoring mistake, so it still fails closed;
        # distinguished from a genuine conflict (below) to match
        # build_coverage_report's duplicate/ambiguous taxonomy.
        valid = MappingRule("control_access", "open", "driver_door", "open_door")
        with self.assertRaises(MappingReadinessError) as duplicate:
            ToolMapper(self.registry, self.manifest, (valid, valid))
        self.assertEqual(duplicate.exception.code, "DUPLICATE_MAPPING")

    def test_startup_validator_rejects_ambiguous_rules(self) -> None:
        # Same key, two different intents -- a genuine conflict: the same
        # tool call would resolve to two different policy intents.
        first = MappingRule("control_access", "open", "driver_door", "open_door")
        conflicting = MappingRule("control_access", "open", "driver_door", "open_trunk")
        with self.assertRaises(MappingReadinessError) as ambiguous:
            ToolMapper(self.registry, self.manifest, (first, conflicting))
        self.assertEqual(ambiguous.exception.code, "AMBIGUOUS_MAPPING")

    def test_startup_validator_rejects_inconsistent_rules(self) -> None:
        wrong_domain = MappingRule(
            "control_access", "open", "driver_door", "turnon_highbeam"
        )
        with self.assertRaises(MappingReadinessError) as mismatch:
            ToolMapper(self.registry, self.manifest, (wrong_domain,))
        self.assertEqual(mismatch.exception.code, "MAPPING_DOMAIN_MISMATCH")

    def test_startup_validator_rejects_incomplete_intent_coverage(self) -> None:
        scoped_manifest = minimal_manifest(
            ("open_door", "control_access", "access_mutation"),
            ("open_trunk", "control_access", "access_mutation"),
        )
        with self.assertRaises(MappingReadinessError) as incomplete:
            ToolMapper(
                self.registry,
                scoped_manifest,
                (MappingRule("control_access", "open", "driver_door", "open_door"),),
            )
        self.assertEqual(incomplete.exception.code, "INCOMPLETE_MAPPING_COVERAGE")
        self.assertIn("open_trunk", incomplete.exception.detail)


class MappingCoverageReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_manifest()

    def test_default_mapping_rules_are_fully_covered(self) -> None:
        report = build_coverage_report(DEFAULT_MAPPING_RULES, self.manifest)
        self.assertTrue(report.is_complete)
        self.assertEqual(report.missing_intents, ())
        self.assertEqual(report.duplicate_keys, ())
        self.assertEqual(report.ambiguous_keys, ())

    def test_report_does_not_crash_sorting_keys_with_mixed_none_and_string_values(self) -> None:
        # Regression test: build_coverage_report used to sort MappingKeys
        # (str | None trailing `value`) with a plain sorted(), which raised
        # `TypeError: '<' not supported between instances of 'NoneType' and
        # 'str'` whenever two flagged keys shared the same (tool, action,
        # target) prefix but differed in whether `value` was set. Two
        # duplicate-key groups sharing a prefix, one with value="forward" and
        # one with value=None, reproduce it: sorting duplicate_keys (which
        # then holds both) compares them and used to crash.
        scoped_manifest = minimal_manifest(("a", "control_cabin", "toggle"))
        rules = (
            MappingRule("control_cabin", "adjust", "steering_wheel", "a", value="forward"),
            MappingRule("control_cabin", "adjust", "steering_wheel", "a", value="forward"),
            MappingRule("control_cabin", "adjust", "steering_wheel", "a"),
            MappingRule("control_cabin", "adjust", "steering_wheel", "a"),
        )

        report = build_coverage_report(rules, scoped_manifest)  # must not raise TypeError

        self.assertEqual(
            report.duplicate_keys,
            (
                ("control_cabin", "adjust", "steering_wheel", None),
                ("control_cabin", "adjust", "steering_wheel", "forward"),
            ),
        )
        self.assertEqual(report.ambiguous_keys, ())

    def test_report_detects_missing_duplicate_and_ambiguous_entries(self) -> None:
        scoped_manifest = minimal_manifest(
            ("open_door", "control_access", "access_mutation"),
            # Never referenced by any rule below -> "missing".
            ("open_trunk", "control_access", "access_mutation"),
            ("unlock_doors", "control_access", "access_mutation"),
        )
        duplicate_key = ("control_access", "open", "driver_door", None)
        ambiguous_key = ("control_access", "lock", "all_doors", None)
        rules = (
            # Repeated identical key+intent -> "duplicate" (redundant, harmless).
            MappingRule("control_access", "open", "driver_door", "open_door"),
            MappingRule("control_access", "open", "driver_door", "open_door"),
            # Same key, two different intents -> "ambiguous" (real conflict).
            MappingRule("control_access", "lock", "all_doors", "open_door"),
            MappingRule("control_access", "lock", "all_doors", "unlock_doors"),
        )

        report = build_coverage_report(rules, scoped_manifest)

        self.assertFalse(report.is_complete)
        self.assertEqual(report.missing_intents, ("open_trunk",))
        self.assertEqual(report.duplicate_keys, (duplicate_key,))
        self.assertEqual(report.ambiguous_keys, (ambiguous_key,))


class ToolMapperFullCatalogEndToEndTests(unittest.TestCase):
    """Spot-checks across domain tools/multi-combination intents added by MAP-02."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mapper = ToolMapper(load_registry(), load_manifest())

    def test_open_trunk(self) -> None:
        result = self.mapper.map_proposal(proposal({"action": "open", "target": "trunk"}))
        self.assertEqual(result.canonical_action.intent, "open_trunk")

    def test_open_bonnet_preserves_uppercase_intent_casing(self) -> None:
        result = self.mapper.map_proposal(proposal({"action": "open", "target": "bonnet"}))
        self.assertEqual(result.canonical_action.intent, "OPEN_BONNET")

    def test_switch_drivemode_sport(self) -> None:
        result = self.mapper.map_proposal(
            proposal(
                {"action": "set", "target": "drive_mode", "value": "sport"},
                tool="set_drive_mode",
            )
        )
        self.assertEqual(result.canonical_action.intent, "switch_drivemode_sport")

    def test_shift_gear_reverse_preserves_uppercase_intent_casing(self) -> None:
        result = self.mapper.map_proposal(
            proposal(
                {"action": "shift", "target": "gear", "value": "reverse"},
                tool="control_transmission",
            )
        )
        self.assertEqual(result.canonical_action.intent, "SHIFT_GEAR_REVERSE")

    def test_get_current_speed_query(self) -> None:
        result = self.mapper.map_proposal(
            proposal({"action": "get", "target": "current_speed"}, tool="query_vehicle_state")
        )
        self.assertEqual(result.canonical_action.intent, "get_current_speed")

    def test_ad_steeringwheel_multiple_directions_share_one_intent(self) -> None:
        for direction in ("forward", "down"):
            with self.subTest(direction=direction):
                result = self.mapper.map_proposal(
                    proposal(
                        {"action": "adjust", "target": "steering_wheel", "value": direction},
                        tool="control_cabin",
                    )
                )
                self.assertEqual(result.canonical_action.intent, "ad_steeringwheel")
                self.assertEqual(result.canonical_action.normalized_arguments["value"], direction)

    def test_open_window_multiple_windows_share_one_intent(self) -> None:
        for window in ("driver_window", "rear_right_window"):
            with self.subTest(window=window):
                result = self.mapper.map_proposal(
                    proposal({"action": "open", "target": window}, tool="control_cabin")
                )
                self.assertEqual(result.canonical_action.intent, "open_window")
                self.assertEqual(result.canonical_action.normalized_arguments["target"], window)

    def test_explain_feature_multiple_features_share_one_intent(self) -> None:
        for feature in ("auto_park", "valet_mode"):
            with self.subTest(feature=feature):
                result = self.mapper.map_proposal(
                    proposal(
                        {"action": "explain", "target": feature},
                        tool="explain_vehicle_feature",
                    )
                )
                self.assertEqual(result.canonical_action.intent, "explain_feature")
                self.assertEqual(result.canonical_action.normalized_arguments["target"], feature)

    def test_deactivate_esc_refusal_intent_still_mapped(self) -> None:
        result = self.mapper.map_proposal(
            proposal(
                {"action": "deactivate", "target": "electronic_stability_control"},
                tool="control_driver_assistance",
            )
        )
        self.assertEqual(result.canonical_action.intent, "deactivate_esc")


if __name__ == "__main__":
    unittest.main()
