"""Per-subsystem health (ok / degraded / down). Status changes are published as events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from ace_core.app.events import Event, EventBus


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


_SEVERITY: Final = {HealthStatus.OK: 0, HealthStatus.DEGRADED: 1, HealthStatus.DOWN: 2}


@dataclass(frozen=True, slots=True)
class SubsystemHealth:
    name: str
    status: HealthStatus
    detail: str | None
    since: datetime


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    overall: HealthStatus
    subsystems: tuple[SubsystemHealth, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class HealthChanged(Event):
    subsystem: str
    status: HealthStatus
    previous: HealthStatus | None
    detail: str | None = None


class HealthRegistry:
    """Tracks the health of each subsystem; the overall status is the worst one."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._items: dict[str, SubsystemHealth] = {}

    async def set(self, name: str, status: HealthStatus, detail: str | None = None) -> None:
        """Record a subsystem's status; publishes :class:`HealthChanged` when the status changes."""
        previous = self._items.get(name)
        if previous is not None and previous.status == status and previous.detail == detail:
            return
        self._items[name] = SubsystemHealth(name, status, detail, datetime.now(UTC))
        if previous is None or previous.status != status:
            await self._bus.publish(
                HealthChanged(
                    subsystem=name,
                    status=status,
                    previous=previous.status if previous is not None else None,
                    detail=detail,
                )
            )

    def snapshot(self) -> HealthSnapshot:
        items = tuple(sorted(self._items.values(), key=lambda h: h.name))
        overall = max((h.status for h in items), key=_SEVERITY.__getitem__, default=HealthStatus.OK)
        return HealthSnapshot(overall, items)
