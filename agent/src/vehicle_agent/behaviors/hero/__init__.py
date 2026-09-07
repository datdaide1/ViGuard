"""Hero Behaviors Package.

Contains reference implementations for high-priority hero user interaction flows:
- HERO-01: open_door
- HERO-02: activate_hda, activate_aac
- HERO-03: activate_autopark, activate_campmode
- HERO-04: confirmation flow

Note: HERO-02 and HERO-03 both define a module-local
``make_monitored_active_action_handler`` (in ``active_driving_assist`` /
``autopark_campmode`` respectively) — each is scoped to its own module's
intents and raises ``ValueError`` for anything outside it. This package
re-exports both under disambiguated names
(``make_monitored_hda_aac_handler`` / ``make_monitored_autopark_campmode_handler``)
rather than picking one to own the unqualified name, since that would let a
caller silently wire the wrong factory for an intent outside its scope.
"""

from vehicle_agent.behaviors.hero._active_action_common import MonitorOutcome
from vehicle_agent.behaviors.hero.active_driving_assist import (
    HDA_AAC_INTENTS,
    AdasMonitorHeroBehavior,
    register_hda_aac_stop_handlers,
)
from vehicle_agent.behaviors.hero.active_driving_assist import (
    make_monitored_active_action_handler as make_monitored_hda_aac_handler,
)
from vehicle_agent.behaviors.hero.autopark_campmode import (
    AUTOPARK_CAMPMODE_INTENTS,
    AutoparkCampmodeMonitorHeroBehavior,
    register_autopark_campmode_stop_handlers,
)
from vehicle_agent.behaviors.hero.autopark_campmode import (
    make_monitored_active_action_handler as make_monitored_autopark_campmode_handler,
)
from vehicle_agent.behaviors.hero.confirmation import (
    CONFIRMATION_HERO_INTENT,
    ConfirmationHeroBehavior,
)
from vehicle_agent.behaviors.hero.open_door import (
    FakeStateCheckResult,
    OpenDoorHeroBehavior,
    OpenDoorStateGuardResult,
    reset_open_door_state,
)

__all__ = [
    "OpenDoorHeroBehavior",
    "OpenDoorStateGuardResult",
    "FakeStateCheckResult",
    "reset_open_door_state",
    "HDA_AAC_INTENTS",
    "AdasMonitorHeroBehavior",
    "MonitorOutcome",
    "make_monitored_hda_aac_handler",
    "register_hda_aac_stop_handlers",
    "AUTOPARK_CAMPMODE_INTENTS",
    "AutoparkCampmodeMonitorHeroBehavior",
    "make_monitored_autopark_campmode_handler",
    "register_autopark_campmode_stop_handlers",
    "CONFIRMATION_HERO_INTENT",
    "ConfirmationHeroBehavior",
]
