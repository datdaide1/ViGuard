"""Hero Behaviors Package.

Contains reference implementations for high-priority hero user interaction flows:
- HERO-01: open_door
- HERO-02: activate_hda, activate_aac
- HERO-03: activate_autopark, activate_campmode
- HERO-04: confirmation flow

Note: HERO-02 and HERO-03 both expose a ``make_monitored_active_action_handler``
— import each from its own submodule (``active_driving_assist`` /
``autopark_campmode``) when wiring more than one, since this package's
top-level re-export can only bind one name to it.
"""

from vivi_agent.behaviors.hero._active_action_common import MonitorOutcome
from vivi_agent.behaviors.hero.active_driving_assist import (
    HDA_AAC_INTENTS,
    AdasMonitorHeroBehavior,
    register_hda_aac_stop_handlers,
)
from vivi_agent.behaviors.hero.active_driving_assist import (
    make_monitored_active_action_handler as make_monitored_hda_aac_handler,
)
from vivi_agent.behaviors.hero.autopark_campmode import (
    AUTOPARK_CAMPMODE_INTENTS,
    AutoparkCampmodeMonitorHeroBehavior,
    register_autopark_campmode_stop_handlers,
)
from vivi_agent.behaviors.hero.autopark_campmode import (
    make_monitored_active_action_handler as make_monitored_autopark_campmode_handler,
)
from vivi_agent.behaviors.hero.open_door import (
    FakeStateCheckResult,
    OpenDoorHeroBehavior,
    OpenDoorStateGuardResult,
    reset_open_door_state,
)

# Backward-compatible alias: pre-HERO-03 call sites imported the HDA/AAC
# handler factory under this unqualified name. New call sites that need both
# factories should use the disambiguated names above instead.
make_monitored_active_action_handler = make_monitored_hda_aac_handler

__all__ = [
    "OpenDoorHeroBehavior",
    "OpenDoorStateGuardResult",
    "FakeStateCheckResult",
    "reset_open_door_state",
    "HDA_AAC_INTENTS",
    "AdasMonitorHeroBehavior",
    "MonitorOutcome",
    "make_monitored_active_action_handler",
    "make_monitored_hda_aac_handler",
    "register_hda_aac_stop_handlers",
    "AUTOPARK_CAMPMODE_INTENTS",
    "AutoparkCampmodeMonitorHeroBehavior",
    "make_monitored_autopark_campmode_handler",
    "register_autopark_campmode_stop_handlers",
]
