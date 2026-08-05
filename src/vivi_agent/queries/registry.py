"""Query Responder Registry for ViVi Agent.

Maintains the central mapping of query intent_id -> Query Responder instance.
Guarantees zero actuator execution on query path.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from vivi_agent.queries.knowledge import ExplainFeatureResponder
from vivi_agent.queries.models import QueryResult, QueryResultSource, QueryStatus
from vivi_agent.queries.state_queries import (
    AvhQueryResponder,
    BatteryQueryResponder,
    DoorLockQueryResponder,
    GearQueryResponder,
    SpeedQueryResponder,
)
from vivi_agent.vehicle.execution.errors import HandlerNotFoundError

QueryResponderFn = Callable[[Mapping[str, Any], Any], QueryResult]


class QueryResponderRegistry:
    """Registry managing Query Responders for all 6 query intents."""

    def __init__(self) -> None:
        self._responders: dict[str, QueryResponderFn] = {}

    def register(self, intent_id: str, responder: QueryResponderFn) -> None:
        """Register a responder for a query intent_id."""
        if not intent_id or not isinstance(intent_id, str):
            raise ValueError("intent_id must be a non-empty string")
        self._responders[intent_id] = responder

    def get(self, intent_id: str) -> QueryResponderFn | None:
        """Look up a responder by intent_id."""
        return self._responders.get(intent_id)

    def is_registered(self, intent_id: str) -> bool:
        """Return True if a responder is registered for intent_id."""
        return intent_id in self._responders

    def registered_intents(self) -> set[str]:
        """Return a set of all registered query intent IDs."""
        return set(self._responders.keys())

    def execute(self, proposal: Mapping[str, Any], state: Any = None) -> QueryResult:
        """Execute the appropriate query responder for a proposal.

        Parameters
        ----------
        proposal:
            Dictionary containing `intent` (or `intent_id`).
        state:
            Optional VehicleState snapshot for state queries.

        Returns
        -------
        QueryResult
            Structured query response.

        Raises
        ------
        HandlerNotFoundError
            If no query responder is registered for the requested intent.
        """
        params = proposal.get("parameters") or proposal.get("arguments") or proposal
        intent_id = (
            proposal.get("intent")
            or proposal.get("intent_id")
            or (params.get("intent") if isinstance(params, Mapping) else None)
        )

        if not intent_id or not isinstance(intent_id, str):
            raise HandlerNotFoundError(str(intent_id or "unknown"))

        responder = self.get(intent_id)
        if responder is None:
            raise HandlerNotFoundError(intent_id)

        return responder(proposal, state)


def build_default_query_registry() -> QueryResponderRegistry:
    """Instantiate and populate QueryResponderRegistry with all 6 default query responders."""
    registry = QueryResponderRegistry()

    # 5 State Query Responders + 1 Knowledge Query Responder. Each responder's
    # own `intent_id` attribute is the single source of truth for its registry
    # key, so it can never drift from the intent_id embedded in its QueryResult.
    for responder in (
        SpeedQueryResponder(),
        BatteryQueryResponder(),
        GearQueryResponder(),
        DoorLockQueryResponder(),
        AvhQueryResponder(),
        ExplainFeatureResponder(),
    ):
        registry.register(responder.intent_id, responder)

    return registry


# Module-level singleton
QUERY_RESPONDER_REGISTRY: QueryResponderRegistry = build_default_query_registry()
