"""Explicit refusal registry for safety-critical intents.

Some intents are known to the agent but must *never* be executed regardless of
any permit or user instruction.  They are not "unknown" — they are *explicit
refusals*.  This module declares those entries and provides a lookup helper
used by the orchestrator and response composer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RefusalEntry:
    """Declarative record of an intent that must always be refused."""

    intent_id: str
    reason: str
    response_template: str  # Vietnamese natural-language response for the UI


# ---------------------------------------------------------------------------
# Refusal catalog
# ---------------------------------------------------------------------------

REFUSAL_CATALOG: tuple[RefusalEntry, ...] = (
    RefusalEntry(
        intent_id="deactivate_esc",
        reason=(
            "ESC (Electronic Stability Control) is a mandatory safety system "
            "required by VinFast policy and cannot be disabled by any agent "
            "command, regardless of user consent or permit."
        ),
        response_template=(
            "Tôi không thể tắt hệ thống cân bằng điện tử (ESC). "
            "Đây là hệ thống an toàn bắt buộc theo quy định của VinFast "
            "và không thể vô hiệu hóa bằng lệnh thoại."
        ),
    ),
)

# Frozen set of all refused intent IDs for O(1) lookup
REFUSAL_INTENT_IDS: frozenset[str] = frozenset(e.intent_id for e in REFUSAL_CATALOG)

# Index: intent_id → RefusalEntry
_REFUSAL_INDEX: dict[str, RefusalEntry] = {e.intent_id: e for e in REFUSAL_CATALOG}


def get_refusal(intent_id: str) -> RefusalEntry | None:
    """Return the RefusalEntry for *intent_id*, or ``None`` if not a refusal intent."""
    return _REFUSAL_INDEX.get(intent_id)


def is_refusal(intent_id: str) -> bool:
    """Return ``True`` if *intent_id* is registered as an explicit refusal."""
    return intent_id in REFUSAL_INTENT_IDS
