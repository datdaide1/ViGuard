"""Hero Behaviors Package.

Contains reference implementations for high-priority hero user interaction flows:
- HERO-01: open_door
- HERO-02: activate_hda, activate_aac
- HERO-03: activate_autopark, activate_campmode
- HERO-04: confirmation flow
"""

from vivi_agent.behaviors.hero.open_door import (
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
]
