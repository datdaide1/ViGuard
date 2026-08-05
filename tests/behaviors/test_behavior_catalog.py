"""Tests for BEH-01 — Behavior Catalog 47 action/UI intents.

Acceptance criteria verified here:
    AC-1  47/47 action/UI intents have a behavior or refusal entry.
    AC-2  No query intent has an actuator behavior.
    AC-3  Every executable behavior produces observable state/event.
    AC-4  Startup coverage validator passes without raising.
    AC-5  Every BehaviorConfig passes structural validation.
    AC-6  ``deactivate_esc`` is an explicit refusal, not an action.
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from vivi_agent.behaviors.catalog import (
    ACTION_BEHAVIOR_CONFIGS,
    REFUSAL_INTENT_IDS,
    get_behavior_config,
)
from vivi_agent.behaviors.coverage import (
    CoverageReport,
    assert_full_coverage,
    validate_behavior_coverage,
)
from vivi_agent.behaviors.refusal import (
    REFUSAL_CATALOG,
    get_refusal,
    is_refusal,
)
from vivi_agent.vehicle.execution.errors import (
    BehaviorConfigValidationError,
    BehaviorReadinessError,
)
from vivi_agent.vehicle.execution.generic import (
    BehaviorConfig,
    BehaviorHandlerType,
    validate_behavior_config,
    validate_behavior_catalog_readiness,
)

# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------
_MANIFEST_PATH = (
    pathlib.Path(__file__).parents[2]
    / "src" / "vivi_agent" / "catalog" / "intent_manifest.v1.json"
)


def _load_manifest() -> dict:
    with _MANIFEST_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _intents_by_kind(kind: str) -> list[str]:
    return [e["intent"] for e in _load_manifest()["intents"] if e.get("kind", "action") == kind]


# ===========================================================================
# AC-1 — 47/47 coverage
# ===========================================================================

class TestBehaviorCoverage:
    def test_coverage_report_passes(self):
        """assert_full_coverage must not raise."""
        report = assert_full_coverage(ACTION_BEHAVIOR_CONFIGS, REFUSAL_INTENT_IDS)
        assert report.passed is True, report.summary()

    def test_all_action_intents_have_behavior(self):
        """Every manifest action intent has a BehaviorConfig."""
        report = validate_behavior_coverage(ACTION_BEHAVIOR_CONFIGS, REFUSAL_INTENT_IDS)
        assert report.missing_action == [], (
            f"Missing behaviors for: {report.missing_action}"
        )

    def test_covered_action_count(self):
        """Exactly 46 action intents have executable BehaviorConfigs."""
        action_ids = _intents_by_kind("action")
        assert len(action_ids) == 46, f"Expected 46 action intents, got {len(action_ids)}"
        report = validate_behavior_coverage(ACTION_BEHAVIOR_CONFIGS, REFUSAL_INTENT_IDS)
        assert report.covered_action == 46

    def test_refusal_covered(self):
        """deactivate_esc refusal is in the refusal catalog."""
        report = validate_behavior_coverage(ACTION_BEHAVIOR_CONFIGS, REFUSAL_INTENT_IDS)
        assert report.covered_refusal == 1

    def test_total_47_entries(self):
        """46 action configs + 1 refusal = 47 total."""
        total = len(ACTION_BEHAVIOR_CONFIGS) + len(REFUSAL_INTENT_IDS)
        assert total == 47, f"Expected 47, got {total}"

    def test_coverage_fails_on_missing_intent(self):
        """Validator raises when a required intent has no entry."""
        # Remove one config to simulate a missing entry
        trimmed = ACTION_BEHAVIOR_CONFIGS[1:]  # drop first
        with pytest.raises(BehaviorReadinessError, match="missing action behaviors"):
            assert_full_coverage(trimmed, REFUSAL_INTENT_IDS)


# ===========================================================================
# AC-2 — No query intent has actuator behavior
# ===========================================================================

class TestQueryIntentExclusion:
    def test_no_query_intent_in_action_catalog(self):
        """Query intents must not appear in ACTION_BEHAVIOR_CONFIGS."""
        query_ids = set(_intents_by_kind("query"))
        catalog_ids = {cfg.intent_id for cfg in ACTION_BEHAVIOR_CONFIGS}
        overlap = query_ids & catalog_ids
        assert overlap == set(), f"Query intents in action catalog: {overlap}"

    def test_coverage_validator_detects_query_in_catalog(self):
        """Validator flags when a query intent is accidentally in catalog."""
        # Inject a fake behavior for a known query intent
        fake_cfg = BehaviorConfig(
            intent_id="get_current_speed",
            handler_type=BehaviorHandlerType.ONE_SHOT,
            event_name="speed_query_event",
        )
        polluted = ACTION_BEHAVIOR_CONFIGS + (fake_cfg,)
        report = validate_behavior_coverage(polluted, REFUSAL_INTENT_IDS)
        assert "get_current_speed" in report.query_with_behavior
        assert report.passed is False


# ===========================================================================
# AC-3 — Every executable behavior produces observable state/event
# ===========================================================================

class TestBehaviorObservability:
    @pytest.mark.parametrize("cfg", ACTION_BEHAVIOR_CONFIGS, ids=lambda c: c.intent_id)
    def test_each_config_has_observable_mutation(self, cfg: BehaviorConfig):
        """Every BehaviorConfig must specify at least one observable output:
        target_substate, event_name, sub_configs, or active_action_name.
        """
        htype = (
            cfg.handler_type
            if isinstance(cfg.handler_type, BehaviorHandlerType)
            else BehaviorHandlerType(cfg.handler_type)
        )
        observable = (
            cfg.target_substate is not None
            or cfg.event_name is not None
            or len(cfg.sub_configs) > 0
            or cfg.active_action_name is not None
            or htype == BehaviorHandlerType.COMPOUND
        )
        assert observable, (
            f"BehaviorConfig for {cfg.intent_id!r} has no observable mutation specification"
        )


# ===========================================================================
# AC-4 — Startup gate
# ===========================================================================

class TestStartupGate:
    def test_behaviors_package_import_does_not_raise(self):
        """Importing vivi_agent.behaviors must succeed (startup gate passes)."""
        import vivi_agent.behaviors as beh  # noqa: F401
        assert beh.STARTUP_COVERAGE_REPORT.passed is True

    def test_startup_coverage_report_accessible(self):
        from vivi_agent.behaviors import STARTUP_COVERAGE_REPORT
        assert isinstance(STARTUP_COVERAGE_REPORT, CoverageReport)
        assert STARTUP_COVERAGE_REPORT.passed


# ===========================================================================
# AC-5 — Structural validation of every BehaviorConfig
# ===========================================================================

class TestBehaviorConfigValidation:
    @pytest.mark.parametrize("cfg", ACTION_BEHAVIOR_CONFIGS, ids=lambda c: c.intent_id)
    def test_each_config_passes_structural_validation(self, cfg: BehaviorConfig):
        """validate_behavior_config must not raise for any catalog entry."""
        validate_behavior_config(cfg)  # raises BehaviorConfigValidationError on failure

    def test_catalog_readiness_passes(self):
        """validate_behavior_catalog_readiness must not raise for full catalog."""
        validate_behavior_catalog_readiness(ACTION_BEHAVIOR_CONFIGS)

    def test_duplicate_intent_raises(self):
        """Duplicate intent IDs in catalog must be detected."""
        dup = ACTION_BEHAVIOR_CONFIGS + (ACTION_BEHAVIOR_CONFIGS[0],)
        with pytest.raises(BehaviorReadinessError, match="Duplicate"):
            validate_behavior_catalog_readiness(dup)


# ===========================================================================
# AC-6 — deactivate_esc is explicit refusal
# ===========================================================================

class TestEscRefusal:
    def test_deactivate_esc_is_refusal(self):
        assert is_refusal("deactivate_esc") is True

    def test_deactivate_esc_not_in_action_catalog(self):
        catalog_ids = {cfg.intent_id for cfg in ACTION_BEHAVIOR_CONFIGS}
        assert "deactivate_esc" not in catalog_ids

    def test_get_refusal_returns_entry(self):
        entry = get_refusal("deactivate_esc")
        assert entry is not None
        assert entry.intent_id == "deactivate_esc"
        assert "ESC" in entry.reason
        assert len(entry.response_template) > 0

    def test_get_refusal_returns_none_for_action(self):
        assert get_refusal("open_door") is None
        assert get_refusal("activate_campmode") is None

    def test_refusal_catalog_has_one_entry(self):
        assert len(REFUSAL_CATALOG) == 1
        assert REFUSAL_CATALOG[0].intent_id == "deactivate_esc"


# ===========================================================================
# Additional: get_behavior_config helper
# ===========================================================================

class TestGetBehaviorConfig:
    def test_known_intent_returns_config(self):
        cfg = get_behavior_config("open_door")
        assert cfg is not None
        assert cfg.intent_id == "open_door"

    def test_unknown_intent_returns_none(self):
        assert get_behavior_config("nonexistent_intent") is None

    def test_query_intent_returns_none(self):
        assert get_behavior_config("get_current_speed") is None

    def test_refusal_intent_returns_none(self):
        assert get_behavior_config("deactivate_esc") is None


# ===========================================================================
# Smoke: unique intent IDs in catalog
# ===========================================================================

class TestCatalogUniqueness:
    def test_all_intent_ids_unique(self):
        ids = [cfg.intent_id for cfg in ACTION_BEHAVIOR_CONFIGS]
        assert len(ids) == len(set(ids)), (
            f"Duplicate intent IDs: {[x for x in ids if ids.count(x) > 1]}"
        )
