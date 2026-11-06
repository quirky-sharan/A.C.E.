"""Event bus: ordering, type matching, error isolation, unsubscribe, background delivery."""

import asyncio
import dataclasses

import pytest
from structlog.testing import capture_logs

from ace_core.app.events import AppStarted, AppStopping, Event, EventBus


async def test_delivers_in_subscription_order_including_base_class_subscribers() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def first(_: AppStarted) -> None:
        seen.append("first")

    async def any_event(_: Event) -> None:
        seen.append("any")

    async def last(_: AppStarted) -> None:
        seen.append("last")

    bus.subscribe(AppStarted, first)
    bus.subscribe(Event, any_event)
    bus.subscribe(AppStarted, last)
    await bus.publish(AppStarted(version="1"))
    assert seen == ["first", "any", "last"]


async def test_other_event_types_are_not_delivered() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def on_started(_: AppStarted) -> None:
        seen.append("started")

    bus.subscribe(AppStarted, on_started)
    await bus.publish(AppStopping(reason="test"))
    assert seen == []


async def test_failing_handler_is_logged_and_others_still_run() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def broken(_: AppStarted) -> None:
        raise RuntimeError("boom")

    async def healthy(_: AppStarted) -> None:
        seen.append("ok")

    bus.subscribe(AppStarted, broken)
    bus.subscribe(AppStarted, healthy)
    with capture_logs() as logs:
        failures = await bus.publish(AppStarted(version="1"))
    assert failures == 1
    assert seen == ["ok"]
    assert any(
        entry["event"] == "event handler failed" and entry["log_level"] == "error" for entry in logs
    )


async def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def handler(event: AppStarted) -> None:
        seen.append(event.version)

    unsubscribe = bus.subscribe(AppStarted, handler)
    await bus.publish(AppStarted(version="1"))
    unsubscribe()
    await bus.publish(AppStarted(version="2"))
    assert seen == ["1"]


async def test_publish_nowait_then_drain() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def slow(event: AppStarted) -> None:
        await asyncio.sleep(0.01)
        seen.append(event.version)

    bus.subscribe(AppStarted, slow)
    bus.publish_nowait(AppStarted(version="x"))
    assert seen == []
    await bus.drain()
    assert seen == ["x"]


def test_events_are_immutable_and_timestamped() -> None:
    event = AppStarted(version="1")
    assert event.ts.tzinfo is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.version = "2"  # type: ignore[misc]
