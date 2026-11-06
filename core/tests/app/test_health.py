"""Health registry: worst-status aggregation and change events."""

from ace_core.app.events import EventBus
from ace_core.app.health import HealthChanged, HealthRegistry, HealthStatus


def test_empty_registry_is_ok() -> None:
    assert HealthRegistry(EventBus()).snapshot().overall is HealthStatus.OK


async def test_overall_status_is_the_worst_subsystem() -> None:
    health = HealthRegistry(EventBus())
    await health.set("core", HealthStatus.OK)
    await health.set("voice", HealthStatus.DEGRADED, "mic unplugged")
    assert health.snapshot().overall is HealthStatus.DEGRADED
    await health.set("ipc", HealthStatus.DOWN)
    snapshot = health.snapshot()
    assert snapshot.overall is HealthStatus.DOWN
    assert [s.name for s in snapshot.subsystems] == ["core", "ipc", "voice"]


async def test_only_status_changes_publish_events() -> None:
    bus = EventBus()
    changes: list[HealthChanged] = []

    async def record(event: HealthChanged) -> None:
        changes.append(event)

    bus.subscribe(HealthChanged, record)
    health = HealthRegistry(bus)
    await health.set("core", HealthStatus.OK)
    await health.set("core", HealthStatus.OK)  # no change
    await health.set("core", HealthStatus.OK, "still fine")  # detail only: no event
    await health.set("core", HealthStatus.DEGRADED)
    assert [(c.previous, c.status) for c in changes] == [
        (None, HealthStatus.OK),
        (HealthStatus.OK, HealthStatus.DEGRADED),
    ]
