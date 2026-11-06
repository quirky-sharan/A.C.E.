"""Typed in-process event bus: async publish / subscribe with per-subscriber error isolation.

Delivery is sequential, in subscription order, to every subscriber whose event type matches
(``isinstance``, so subscribing to a base class receives its subclasses). A failing subscriber is
logged and skipped; the others still run.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

import structlog

log = structlog.stdlib.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    """Base class of every in-process event."""

    ts: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True, kw_only=True)
class AppStarted(Event):
    version: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AppStopping(Event):
    reason: str


E = TypeVar("E", bound=Event)


@dataclass(frozen=True, slots=True, eq=False)
class _Subscription:
    sub_id: int
    event_type: type[Event]
    handler: Callable[[Any], Awaitable[None]]


class EventBus:
    """In-process publish / subscribe. Not thread-safe: use it from the event-loop thread."""

    def __init__(self) -> None:
        self._subscriptions: list[_Subscription] = []
        self._ids = itertools.count(1)
        self._pending: set[asyncio.Task[int]] = set()

    def subscribe(
        self, event_type: type[E], handler: Callable[[E], Awaitable[None]]
    ) -> Callable[[], None]:
        """Register ``handler`` for ``event_type`` and its subclasses; returns an unsubscriber."""
        subscription = _Subscription(next(self._ids), event_type, handler)
        self._subscriptions.append(subscription)

        def unsubscribe() -> None:
            self._subscriptions = [s for s in self._subscriptions if s is not subscription]

        return unsubscribe

    async def publish(self, event: Event) -> int:
        """Deliver ``event`` and wait for all handlers. Returns how many handlers failed."""
        failures = 0
        for subscription in tuple(self._subscriptions):  # handlers may (un)subscribe meanwhile
            if not isinstance(event, subscription.event_type):
                continue
            try:
                await subscription.handler(event)
            except Exception:
                failures += 1
                log.exception(
                    "event handler failed",
                    event_type=type(event).__name__,
                    handler=getattr(
                        subscription.handler, "__qualname__", repr(subscription.handler)
                    ),
                )
        return failures

    def publish_nowait(self, event: Event) -> asyncio.Task[int]:
        """Publish in the background; :meth:`drain` waits for all such deliveries."""
        task = asyncio.get_running_loop().create_task(self.publish(event))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    async def drain(self) -> None:
        """Wait until every :meth:`publish_nowait` delivery has finished."""
        while self._pending:
            await asyncio.gather(*tuple(self._pending), return_exceptions=True)
