"""Permission tiers (ACE_MASTER_PLAN.md §15.3, D-10). Enforced in code by the Supervisor, never
left to a model's judgment (§15.1 item 4)."""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Tier(StrEnum):
    T0 = "T0"  # read-only, no side effects
    T1 = "T1"  # reversible side effects
    T2 = "T2"  # irreversible or external effects: confirm every time
    T3 = "T3"  # forbidden: refuse


class TierPolicy(StrEnum):
    RUN = "run"
    RUN_AND_LOG = "run_and_log"
    CONFIRM = "confirm"
    REFUSE = "refuse"


POLICY: Final[dict[Tier, TierPolicy]] = {
    Tier.T0: TierPolicy.RUN,
    Tier.T1: TierPolicy.RUN_AND_LOG,
    Tier.T2: TierPolicy.CONFIRM,
    Tier.T3: TierPolicy.REFUSE,
}


def policy_for(tier: Tier) -> TierPolicy:
    return POLICY[tier]
