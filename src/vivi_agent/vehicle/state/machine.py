"""Vehicle State Machine -- atomic transitions with versioning and events.

:class:`VehicleStateMachine` is the single mutable authority for
:class:`~vivi_agent.vehicle.state.VehicleState` at runtime.  All actors
(Agent, Operator, Simulator, System) use the same :meth:`~VehicleStateMachine.apply`
API; they differ only in the ``actor_kind`` / ``actor_id`` metadata they supply.

Design
------
* **Immutable snapshots** -- the stored state is always a frozen
  :class:`VehicleState`; the machine never mutates it in place.
* **Atomic transitions** -- a ``threading.Lock`` serialises all writes.
  If the caller-supplied patch function raises, or if the resulting snapshot
  fails :class:`VehicleState` invariant validation, the transition is aborted
  and the current state/version is unchanged.
* **Monotonic versioning** -- ``state_version`` increments by exactly 1 on
  every successful transition.
* **Optimistic expected-version** -- callers can pass ``expected_version`` to
  detect concurrent modifications; a mismatch raises
  :class:`VersionConflictError` **before** the patch function is called.
* **Event emission** -- every commit produces exactly one
  :class:`~.events.StateChangedEvent` appended to :class:`~.events.VehicleEventStore`.
* **Reset/preset lifecycle** -- :meth:`reset` replaces the full state from a
  named preset and emits a SYSTEM-actor event.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from .events import ActorKind, StateChangedEvent, VehicleEventStore
from .model import VehicleState, VehicleStateValidationError, pip_provenance, StateSource
from .presets import get_preset


class TransitionError(Exception):
    """The patch function raised an exception during a transition attempt.

    The vehicle state and version are **unchanged**.
    """

    def __init__(self, cause: Exception) -> None:
        super().__init__(f"Transition failed: {cause}")
        self.cause = cause


class VersionConflictError(Exception):
    """Optimistic-locking conflict: expected version does not match current.

    The vehicle state and version are **unchanged**.

    Attributes
    ----------
    expected:
        The version the caller assumed was current.
    actual:
        The actual current version at the time of the check.
    """

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            f"Version conflict: expected={expected}, actual={actual}"
        )
        self.expected = expected
        self.actual = actual


PatchFn = Callable[[VehicleState], VehicleState]


class VehicleStateMachine:
    """In-memory Vehicle State Machine.

    Parameters
    ----------
    initial_state:
        The starting :class:`VehicleState`.  Defaults to
        :data:`~.model.DEFAULT_VEHICLE_STATE` (``state_version=0``).
    event_store:
        Shared :class:`~.events.VehicleEventStore`.  A new private store is
        created if not supplied.

    Examples
    --------
    >>> from dataclasses import replace
    >>> from vivi_agent.vehicle.state import VehicleStateMachine, PowerState, ActorKind
    >>> machine = VehicleStateMachine()
    >>> event = machine.apply(
    ...     lambda s: replace(s, power=PowerState(powered_on=True)),
    ...     actor_kind=ActorKind.AGENT,
    ...     actor_id="action-001",
    ...     correlation_id="req-abc",
    ... )
    >>> event.next_version
    1
    """

    def __init__(
        self,
        initial_state: VehicleState | None = None,
        *,
        event_store: VehicleEventStore | None = None,
    ) -> None:
        from .model import DEFAULT_VEHICLE_STATE

        self._state: VehicleState = (
            initial_state if initial_state is not None else DEFAULT_VEHICLE_STATE
        )
        self._lock = threading.Lock()
        self._event_store = event_store if event_store is not None else VehicleEventStore()

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    @property
    def event_store(self) -> VehicleEventStore:
        """The :class:`~.events.VehicleEventStore` used by this machine."""
        return self._event_store

    def snapshot(self) -> VehicleState:
        """Return the current state snapshot.

        The returned object is immutable (frozen dataclass) and safe to share
        across threads without copying.
        """
        with self._lock:
            return self._state

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def apply(
        self,
        patch_fn: PatchFn,
        *,
        actor_kind: ActorKind,
        actor_id: str,
        correlation_id: str,
        expected_version: int | None = None,
    ) -> StateChangedEvent:
        """Apply an atomic state transition.

        Parameters
        ----------
        patch_fn:
            Pure function ``VehicleState -> VehicleState``.  It receives the
            current snapshot and must return the desired next snapshot.  The
            machine will call it inside the write lock and assign the new
            ``state_version`` and ``timestamp`` automatically.  The function
            **must not** mutate the input (frozen dataclass prevents this).
        actor_kind:
            Category of the actor initiating the transition.
        actor_id:
            Opaque identifier for the specific actor.
        correlation_id:
            Opaque string linking this transition to a higher-level request.
        expected_version:
            If provided, the transition is rejected with
            :class:`VersionConflictError` if the current ``state_version``
            does not equal this value.

        Returns
        -------
        StateChangedEvent
            The committed event, including the new immutable snapshot.

        Raises
        ------
        VersionConflictError
            Optimistic-locking conflict (state unchanged).
        TransitionError
            The patch function raised an exception (state unchanged).
        VehicleStateValidationError
            The new snapshot violates invariants (state unchanged).
        """
        with self._lock:
            current = self._state

            # Optimistic locking check
            if expected_version is not None and current.state_version != expected_version:
                raise VersionConflictError(
                    expected=expected_version, actual=current.state_version
                )

            # Build next state
            previous_version = current.state_version
            next_version = previous_version + 1
            now = datetime.now(tz=timezone.utc)

            try:
                candidate = patch_fn(current)
            except VehicleStateValidationError:
                raise  # invariant violations propagate directly
            except Exception as exc:
                raise TransitionError(exc) from exc

            # Stamp version + timestamp; also refresh provenance so that
            # observed_at timestamps never exceed the new snapshot timestamp.
            # VehicleState.__post_init__ validates invariants -- if it raises,
            # the assignment below never happens (state unchanged).
            updated_provenance = pip_provenance(
                StateSource.VEHICLE_HANDLER, now
            )
            next_state = replace(
                candidate,
                state_version=next_version,
                timestamp=now,
                pip_field_provenance=updated_provenance,
            )

            # Commit
            self._state = next_state

        # Emit event outside the machine lock (store has its own lock)
        return self._event_store._build_and_append(
            correlation_id=correlation_id,
            previous_version=previous_version,
            next_version=next_version,
            actor_kind=actor_kind,
            actor_id=actor_id,
            snapshot=next_state,
        )

    def reset(
        self,
        preset_id: str,
        *,
        actor_id: str = "system",
        correlation_id: str = "reset",
    ) -> StateChangedEvent:
        """Replace the full state with a named preset and emit a SYSTEM event.

        Parameters
        ----------
        preset_id:
            ID of a preset defined in :mod:`.presets` (e.g. ``"parked_ready"``).
        actor_id:
            Identifier for the reset initiator; defaults to ``"system"``.
        correlation_id:
            Opaque correlation string; defaults to ``"reset"``.

        Returns
        -------
        StateChangedEvent
            The committed reset event.

        Raises
        ------
        KeyError
            Unknown ``preset_id``.
        """
        with self._lock:
            previous_version = self._state.state_version
            next_version = previous_version + 1
            now = datetime.now(tz=timezone.utc)
            next_state = get_preset(preset_id, state_version=next_version, timestamp=now)
            self._state = next_state

        return self._event_store._build_and_append(
            correlation_id=correlation_id,
            previous_version=previous_version,
            next_version=next_version,
            actor_kind=ActorKind.SYSTEM,
            actor_id=actor_id,
            snapshot=next_state,
        )
