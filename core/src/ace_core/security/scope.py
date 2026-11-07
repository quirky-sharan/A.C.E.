"""Per-task capability scope (ACE_MASTER_PLAN.md §8.4, §15.1): a task may only call the skills it
was created for. S07 has the basic form (exact skill ids, or ``pack.*`` for a whole pack); S17
enforces it inside the multi-step agent loop."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilityScope:
    allowed: frozenset[str]

    @classmethod
    def of(cls, capabilities: Iterable[str]) -> CapabilityScope:
        return cls(frozenset(capabilities))

    def allows(self, skill_id: str) -> bool:
        if skill_id in self.allowed:
            return True
        return any(
            entry.endswith(".*") and skill_id.startswith(entry[:-1]) for entry in self.allowed
        )

    def as_list(self) -> list[str]:
        return sorted(self.allowed)
