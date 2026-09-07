"""Deterministic Vietnamese persona rendering for grounded responses.

Persona rendering is deliberately presentation-only: profiles are closed enums,
and the renderer may add a fixed courtesy lead-in but never rewrites facts,
policy reasons, or execution results.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vehicle_agent.responses.models import ResponseOutcome


class PersonaTone(str, Enum):
    """Supported, reviewed assistant speaking styles."""

    NEUTRAL = "neutral"
    WARM = "warm"
    FORMAL = "formal"


class UserAddress(str, Enum):
    """Closed Vietnamese forms of address; arbitrary prompt text is not allowed."""

    BAN = "bạn"
    ANH = "anh"
    CHI = "chị"


@dataclass(frozen=True)
class PersonaProfile:
    """Immutable persona selection for one composer instance."""

    tone: PersonaTone = PersonaTone.NEUTRAL
    user_address: UserAddress = UserAddress.BAN

    def __post_init__(self) -> None:
        """Reject unreviewed strings even when callers bypass static type checking."""
        if not isinstance(self.tone, PersonaTone):
            raise TypeError("tone must be a PersonaTone")
        if not isinstance(self.user_address, UserAddress):
            raise TypeError("user_address must be a UserAddress")


class PersonaVerbalizer:
    """Apply a reviewed courtesy lead-in without changing grounded content."""

    _WARM_PREFIXES = {
        ResponseOutcome.ALLOW_SUCCESS: "Dạ, ",
        ResponseOutcome.ALLOW_FAILED: "Dạ, rất tiếc, ",
        ResponseOutcome.BLOCK_UNAVAILABLE: "Dạ, rất tiếc, ",
        ResponseOutcome.CONFIRM: "Dạ, ",
        ResponseOutcome.NOT_VOICE_ACTIONABLE: "Dạ, ",
        ResponseOutcome.ANSWER: "Dạ, ",
        ResponseOutcome.UNKNOWN: "Dạ, rất tiếc, ",
        ResponseOutcome.EXECUTION_ERROR: "Dạ, rất tiếc, ",
    }

    def __init__(self, profile: PersonaProfile | None = None) -> None:
        if profile is not None and not isinstance(profile, PersonaProfile):
            raise TypeError("profile must be a PersonaProfile")
        self.profile = profile or PersonaProfile()

    def render(self, text: str, outcome: ResponseOutcome) -> str:
        """Return a deterministic persona variant while preserving ``text`` verbatim."""
        if self.profile.tone is PersonaTone.NEUTRAL or not text:
            return text
        if self.profile.tone is PersonaTone.FORMAL:
            return f"Xin thông báo tới {self.profile.user_address.value}: {text}"
        if outcome is ResponseOutcome.BLOCK_UNSAFE:
            return f"Dạ, vì an toàn của {self.profile.user_address.value}, {text}"
        return f"{self._WARM_PREFIXES[outcome]}{text}"
