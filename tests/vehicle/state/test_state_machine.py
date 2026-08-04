"""Tests for VEH-02 -- Vehicle State Machine and Event Store.

Acceptance criteria
-------------------
AC-1: Failed transition does not change state or version.
AC-2: Successful transition increments version exactly once.
AC-3: Guardrail/UI can retrieve snapshot/event via contract.
"""

from __future__ import annotations

import threading
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from src.vivi_agent.vehicle.state import (
    ActorKind,
    DEFAULT_VEHICLE_STATE,
    Gear,
    MotionPhase,
    MotionState,
    PowerState,
    StateChangedEvent,
    TransitionError,
    TransmissionState,
    VehicleEventStore,
    VehicleState,
    VehicleStateMachine,
    VehicleStateValidationError,
    VersionConflictError,
    get_preset,
    pip_provenance,
    StateSource,
)


_NOW = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
_ACTOR = dict(actor_kind=ActorKind.AGENT, actor_id="agent-001", correlation_id="req-001")


def _make_machine(preset: str | None = None) -> VehicleStateMachine:
    if preset:
        initial = get_preset(preset, state_version=0, timestamp=_NOW)
        return VehicleStateMachine(initial)
    return VehicleStateMachine()


class TestSuccessfulTransition(unittest.TestCase):
    """AC-2: Successful transition increments version exactly once."""

    def test_version_increments_by_one(self) -> None:
        machine = _make_machine()
        before = machine.snapshot().state_version
        event = machine.apply(
            lambda s: replace(s, power=PowerState(powered_on=True)),
            **_ACTOR,
        )
        after = machine.snapshot().state_version
        self.assertEqual(after, before + 1)
        self.assertEqual(event.next_version, before + 1)
        self.assertEqual(event.previous_version, before)

    def test_multiple_transitions_increment_monotonically(self) -> None:
        machine = _make_machine()
        for i in range(5):
            machine.apply(lambda s: s, **_ACTOR)
        self.assertEqual(machine.snapshot().state_version, 5)

    def test_event_snapshot_matches_current_state(self) -> None:
        machine = _make_machine()
        event = machine.apply(
            lambda s: replace(s, power=PowerState(powered_on=True)),
            **_ACTOR,
        )
        self.assertEqual(event.snapshot, machine.snapshot())


class TestFailedTransition(unittest.TestCase):
    """AC-1: Failed transition does not change state or version."""

    def test_invariant_violation_leaves_state_unchanged(self) -> None:
        """Patch produces an invalid VehicleState -- machine must rollback.

        VehicleStateValidationError raised inside patch_fn propagates directly
        (not wrapped in TransitionError) so callers can handle it precisely.
        """
        machine = _make_machine("parked_ready")
        before_version = machine.snapshot().state_version
        before_state = machine.snapshot()

        # Moving at speed with gear=PARK violates PARK_REQUIRES_STOPPED
        with self.assertRaises(VehicleStateValidationError) as ctx:
            machine.apply(
                lambda s: replace(
                    s,
                    motion=MotionState(speed_kph=30.0, phase=MotionPhase.MOVING),
                    # transmission stays PARK -- invalid cross-field combination
                ),
                **_ACTOR,
            )
        self.assertEqual(ctx.exception.code, "PARK_REQUIRES_STOPPED")
        self.assertEqual(machine.snapshot().state_version, before_version)
        self.assertEqual(machine.snapshot(), before_state)

    def test_patch_function_exception_raises_transition_error(self) -> None:
        machine = _make_machine()
        before = machine.snapshot().state_version

        def bad_patch(s: VehicleState) -> VehicleState:
            raise RuntimeError("something went wrong")

        with self.assertRaises(TransitionError) as ctx:
            machine.apply(bad_patch, **_ACTOR)
        self.assertIsInstance(ctx.exception.cause, RuntimeError)
        self.assertEqual(machine.snapshot().state_version, before)

    def test_failed_transition_emits_no_event(self) -> None:
        machine = _make_machine()
        store = machine.event_store
        before_len = len(store)

        with self.assertRaises((VehicleStateValidationError, TransitionError)):
            machine.apply(
                lambda s: replace(s, motion=MotionState(speed_kph=50.0, phase=MotionPhase.STOPPED)),
                **_ACTOR,
            )
        self.assertEqual(len(store), before_len)


class TestOptimisticLocking(unittest.TestCase):
    """AC-1 variant: optimistic expected-version conflict leaves state unchanged."""

    def test_matching_expected_version_succeeds(self) -> None:
        machine = _make_machine()
        current_version = machine.snapshot().state_version
        event = machine.apply(
            lambda s: replace(s, power=PowerState(powered_on=True)),
            expected_version=current_version,
            **_ACTOR,
        )
        self.assertEqual(event.next_version, current_version + 1)

    def test_stale_expected_version_raises_conflict(self) -> None:
        machine = _make_machine()
        # Advance the machine by one transition
        machine.apply(lambda s: s, **_ACTOR)

        with self.assertRaises(VersionConflictError) as ctx:
            machine.apply(
                lambda s: s,
                expected_version=0,  # stale -- machine is now at version 1
                **_ACTOR,
            )
        self.assertEqual(ctx.exception.expected, 0)
        self.assertEqual(ctx.exception.actual, 1)
        self.assertEqual(machine.snapshot().state_version, 1)


class TestEventStore(unittest.TestCase):
    """AC-3: Guardrail/UI can retrieve snapshot/event via contract."""

    def test_event_is_recorded_after_successful_transition(self) -> None:
        machine = _make_machine()
        self.assertEqual(len(machine.event_store), 0)
        event = machine.apply(lambda s: s, **_ACTOR)
        self.assertEqual(len(machine.event_store), 1)
        stored = machine.event_store.get_event(1)
        self.assertEqual(stored, event)

    def test_event_sequence_is_monotonic(self) -> None:
        machine = _make_machine()
        for i in range(3):
            machine.apply(lambda s: s, **_ACTOR)
        events = machine.event_store.list_all()
        sequences = [e.sequence for e in events]
        self.assertEqual(sequences, [1, 2, 3])

    def test_list_since_returns_correct_subset(self) -> None:
        machine = _make_machine()
        for _ in range(5):
            machine.apply(lambda s: s, **_ACTOR)
        since_3 = machine.event_store.list_since(3)
        self.assertEqual(len(since_3), 3)
        self.assertEqual(since_3[0].sequence, 3)
        self.assertEqual(since_3[-1].sequence, 5)

    def test_latest_returns_most_recent_event(self) -> None:
        machine = _make_machine()
        self.assertIsNone(machine.event_store.latest())
        machine.apply(lambda s: s, **_ACTOR)
        event = machine.apply(lambda s: s, **_ACTOR)
        self.assertEqual(machine.event_store.latest(), event)

    def test_event_to_dict_is_json_serialisable(self) -> None:
        machine = _make_machine("parked_ready")
        event = machine.apply(lambda s: s, **_ACTOR)
        d = event.to_dict()
        self.assertIn("event_id", d)
        self.assertIn("snapshot", d)
        self.assertIsInstance(d["snapshot"], dict)
        self.assertEqual(d["actor_kind"], "AGENT")

    def test_snapshot_in_event_matches_state_at_transition_time(self) -> None:
        machine = _make_machine()
        event = machine.apply(
            lambda s: replace(s, power=PowerState(powered_on=True)),
            **_ACTOR,
        )
        self.assertTrue(event.snapshot.power.powered_on)


class TestActorMetadata(unittest.TestCase):
    """Actor and correlation metadata is propagated correctly to the event."""

    def test_agent_actor_metadata_propagated(self) -> None:
        machine = _make_machine()
        event = machine.apply(
            lambda s: s,
            actor_kind=ActorKind.AGENT,
            actor_id="action-xyz",
            correlation_id="corr-abc",
        )
        self.assertEqual(event.actor_kind, ActorKind.AGENT)
        self.assertEqual(event.actor_id, "action-xyz")
        self.assertEqual(event.correlation_id, "corr-abc")

    def test_operator_actor_kind(self) -> None:
        machine = _make_machine()
        event = machine.apply(
            lambda s: s,
            actor_kind=ActorKind.OPERATOR,
            actor_id="op-user",
            correlation_id="ui-req-1",
        )
        self.assertEqual(event.actor_kind, ActorKind.OPERATOR)


class TestResetLifecycle(unittest.TestCase):
    """Reset replaces full state and emits a SYSTEM-actor event."""

    def test_reset_to_preset_changes_state(self) -> None:
        machine = _make_machine()
        # Advance to a non-zero version
        machine.apply(lambda s: s, **_ACTOR)
        before_version = machine.snapshot().state_version

        event = machine.reset("parked_ready")
        self.assertTrue(machine.snapshot().power.powered_on)
        self.assertEqual(machine.snapshot().state_version, before_version + 1)
        self.assertEqual(event.actor_kind, ActorKind.SYSTEM)

    def test_reset_emits_event_in_store(self) -> None:
        machine = _make_machine()
        before = len(machine.event_store)
        machine.reset("parked_ready")
        self.assertEqual(len(machine.event_store), before + 1)

    def test_reset_to_unknown_preset_raises_key_error(self) -> None:
        machine = _make_machine()
        before_version = machine.snapshot().state_version
        with self.assertRaises(KeyError):
            machine.reset("nonexistent_preset")
        self.assertEqual(machine.snapshot().state_version, before_version)


class TestImmutability(unittest.TestCase):
    """Snapshot must be independent of internal machine state."""

    def test_snapshot_is_frozen(self) -> None:
        from dataclasses import FrozenInstanceError
        machine = _make_machine()
        snap = machine.snapshot()
        with self.assertRaises(FrozenInstanceError):
            snap.state_version = 99  # type: ignore[misc]

    def test_snapshot_is_not_affected_by_subsequent_transition(self) -> None:
        machine = _make_machine()
        snap_before = machine.snapshot()
        machine.apply(lambda s: replace(s, power=PowerState(powered_on=True)), **_ACTOR)
        self.assertFalse(snap_before.power.powered_on)
        self.assertTrue(machine.snapshot().power.powered_on)


class TestConcurrency(unittest.TestCase):
    """Concurrent transitions must be serialised: no lost updates."""

    def test_concurrent_transitions_produce_contiguous_versions(self) -> None:
        machine = _make_machine()
        results: list[int] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker() -> None:
            try:
                event = machine.apply(lambda s: s, **_ACTOR)
                with lock:
                    results.append(event.next_version)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], msg=f"Unexpected errors: {errors}")
        self.assertEqual(sorted(results), list(range(1, 21)))
        self.assertEqual(machine.snapshot().state_version, 20)
        self.assertEqual(len(machine.event_store), 20)

    def test_concurrent_snapshot_version_matches_latest_event(self) -> None:
        """Issue 1 fix regression: every committed state_version must have a
        corresponding event persisted in the store under the correct sequence.

        Previous approach re-read snapshot() and latest() without a lock after
        apply() returned, so a concurrent thread could advance both between the
        two reads -- producing spurious failures with correct code.

        Correct approach: use the StateChangedEvent returned by apply() as the
        single source of truth, then verify the store has it at the claimed
        sequence with the matching next_version.
        """
        machine = _make_machine()
        errors: list[str] = []
        lock = threading.Lock()

        def worker() -> None:
            event = machine.apply(lambda s: s, **_ACTOR)
            # Verify the store contains this exact event at the claimed sequence.
            stored = machine.event_store.get_event(event.sequence)
            if stored is None:
                with lock:
                    errors.append(f"sequence={event.sequence} not found in store")
            elif stored.next_version != event.next_version:
                with lock:
                    errors.append(
                        f"sequence={event.sequence}: stored.next_version="
                        f"{stored.next_version} != event.next_version={event.next_version}"
                    )

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], msg=f"Consistency violations: {errors}")


class TestCodeReviewFixes(unittest.TestCase):
    """Regression tests for issues found during VEH-02 code review."""

    # Issue 2: empty actor_id / correlation_id rejected before lock
    def test_empty_actor_id_raises_before_state_change(self) -> None:
        machine = _make_machine()
        before = machine.snapshot().state_version
        with self.assertRaises(ValueError) as ctx:
            machine.apply(lambda s: s, actor_kind=ActorKind.AGENT,
                          actor_id="", correlation_id="x")
        self.assertIn("actor_id", str(ctx.exception))
        self.assertEqual(machine.snapshot().state_version, before)
        self.assertEqual(len(machine.event_store), 0)

    def test_empty_correlation_id_raises_before_state_change(self) -> None:
        machine = _make_machine()
        before = machine.snapshot().state_version
        with self.assertRaises(ValueError) as ctx:
            machine.apply(lambda s: s, actor_kind=ActorKind.AGENT,
                          actor_id="agent-1", correlation_id="")
        self.assertIn("correlation_id", str(ctx.exception))
        self.assertEqual(machine.snapshot().state_version, before)
        self.assertEqual(len(machine.event_store), 0)

    def test_reset_empty_actor_id_raises_before_state_change(self) -> None:
        machine = _make_machine()
        before = machine.snapshot().state_version
        with self.assertRaises(ValueError):
            machine.reset("parked_ready", actor_id="", correlation_id="reset")
        self.assertEqual(machine.snapshot().state_version, before)

    # Issue 3: patch_fn returning None raises TransitionError
    def test_patch_fn_returning_none_raises_transition_error(self) -> None:
        machine = _make_machine()
        before = machine.snapshot().state_version
        with self.assertRaises(TransitionError) as ctx:
            machine.apply(lambda s: None, **_ACTOR)  # type: ignore[return-value]
        self.assertIsInstance(ctx.exception.cause, TypeError)
        self.assertIn("VehicleState", str(ctx.exception.cause))
        self.assertEqual(machine.snapshot().state_version, before)
        self.assertEqual(len(machine.event_store), 0)

    # Issue 4: provenance source and available are preserved by apply()
    def test_apply_preserves_provenance_source_from_patch_fn(self) -> None:
        """apply() must not overwrite source/available in pip_field_provenance."""
        from dataclasses import replace as dc_replace
        from datetime import timezone
        from src.vivi_agent.vehicle.state import (
            pip_provenance, StateSource, VehicleStateValidationError,
        )
        # Use DEFAULT_VEHICLE_STATE (timestamp=epoch).  Provenance observed_at
        # must not exceed the *candidate* snapshot timestamp (still epoch here;
        # machine will stamp it to `now` later while preserving source/available).
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        machine = _make_machine()  # initial state_version=0, timestamp=epoch

        def patch_with_operator_provenance(s: VehicleState) -> VehicleState:
            # observed_at <= s.timestamp (both are epoch) to pass __post_init__
            op_provenance = pip_provenance(
                StateSource.OPERATOR, epoch,
                unavailable_fields=frozenset({"rain_sensor"}),
            )
            return dc_replace(s, pip_field_provenance=op_provenance)

        event = machine.apply(patch_with_operator_provenance, **_ACTOR)
        snap = event.snapshot

        rain_prov = next(
            p for p in snap.pip_field_provenance if p.field_name == "rain_sensor"
        )
        # source must be preserved by apply()
        self.assertEqual(rain_prov.source, StateSource.OPERATOR)
        # available=False must be preserved by apply()
        self.assertFalse(rain_prov.available)
        # observed_at must be refreshed to now (not epoch) by apply()
        self.assertGreater(rain_prov.observed_at, epoch)

        # to_guardrail_snapshot must raise because rain_sensor is unavailable
        with self.assertRaises(VehicleStateValidationError) as ctx:
            snap.to_guardrail_snapshot()
        self.assertEqual(ctx.exception.code, "INCOMPLETE_GUARDRAIL_SNAPSHOT")

    # Issue 5: to_dict() occurred_at is always UTC Z format
    def test_to_dict_occurred_at_is_utc_z_format(self) -> None:
        machine = _make_machine()
        event = machine.apply(lambda s: s, **_ACTOR)
        d = event.to_dict()
        self.assertTrue(
            d["occurred_at"].endswith("Z"),
            msg=f"occurred_at must end with Z, got: {d['occurred_at']!r}",
        )

    # Issue 6: sequence vs next_version when initial_state.state_version > 0
    def test_sequence_and_version_documented_not_always_equal(self) -> None:
        """sequence != next_version when initial state_version > 0."""
        initial = get_preset("parked_ready", state_version=5, timestamp=_NOW)
        machine = VehicleStateMachine(initial)
        event = machine.apply(lambda s: s, **_ACTOR)
        # sequence starts from 1 (first event in store)
        self.assertEqual(event.sequence, 1)
        # but version jumps from 5 to 6
        self.assertEqual(event.next_version, 6)
        self.assertNotEqual(event.sequence, event.next_version)

    def test_clock_alignment_across_snapshot_provenance_and_event(self) -> None:
        """Sourcery recommendation: clock injection aligns state timestamp,
        provenance observed_at, and event occurred_at to the exact same instant.
        """
        fixed_time = datetime(2026, 8, 4, 15, 0, 0, tzinfo=timezone.utc)
        machine = VehicleStateMachine(_clock=lambda: fixed_time)
        event = machine.apply(lambda s: s, **_ACTOR)

        self.assertEqual(event.occurred_at, fixed_time)
        self.assertEqual(event.snapshot.timestamp, fixed_time)
        for prov in event.snapshot.pip_field_provenance:
            self.assertEqual(prov.observed_at, fixed_time)


if __name__ == "__main__":
    unittest.main()

