"""Unit tests for HERO-04 — confirmation hero behavior (open_window)."""

from __future__ import annotations

from vivi_agent.behaviors.hero.confirmation import (
    CONFIRMATION_HERO_INTENT,
    ConfirmationHeroBehavior,
)
from vivi_agent.confirmation.models import ConfirmationState, PendingConfirmation


def _pending(**overrides) -> PendingConfirmation:
    base = dict(
        confirmation_id="confirm-1",
        proposal_id="prop-1",
        session_id="sess-1",
        turn_id="turn-1",
        request_id="req-1",
        prompt="Bạn có chắc chắn muốn mở cửa sổ không?",
        expires_at="2099-01-01T00:00:00Z",
    )
    base.update(overrides)
    return PendingConfirmation(**base)


class TestConfirmationHeroIntent:
    def test_intent_constant_matches_class_attribute(self):
        assert ConfirmationHeroBehavior.INTENT_ID == CONFIRMATION_HERO_INTENT
        assert CONFIRMATION_HERO_INTENT == "open_window"


class TestBuildPendingFacts:
    def test_includes_intent_alongside_pending_fields(self):
        pending = _pending()

        facts = ConfirmationHeroBehavior.build_pending_facts(pending)

        assert facts["intent"] == "open_window"
        assert facts["confirmation_id"] == "confirm-1"
        assert facts["proposal_id"] == "prop-1"
        assert facts["prompt"] == pending.prompt
        assert facts["expires_at"] == "2099-01-01T00:00:00Z"
        assert facts["state"] == ConfirmationState.PENDING.value

    def test_accepts_an_explicit_intent_override(self):
        pending = _pending()

        facts = ConfirmationHeroBehavior.build_pending_facts(pending, intent="open_sunroof")

        assert facts["intent"] == "open_sunroof"

    def test_reflects_current_pending_state_not_only_pending(self):
        pending = _pending()
        pending.state = ConfirmationState.CONSUMED

        facts = ConfirmationHeroBehavior.build_pending_facts(pending)

        assert facts["state"] == ConfirmationState.CONSUMED.value

    def test_does_not_mutate_the_source_record(self):
        pending = _pending()
        original_dict = pending.to_dict()

        ConfirmationHeroBehavior.build_pending_facts(pending)

        assert pending.to_dict() == original_dict
