"""Explicit dependency container: everything the core needs, built once at startup."""

from __future__ import annotations

from dataclasses import dataclass

from ace_core.app.config import Settings
from ace_core.app.events import EventBus
from ace_core.app.health import HealthRegistry
from ace_core.app.paths import AppPaths


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    paths: AppPaths
    bus: EventBus
    health: HealthRegistry


def build_container(settings: Settings, paths: AppPaths) -> Container:
    bus = EventBus()
    return Container(settings=settings, paths=paths, bus=bus, health=HealthRegistry(bus))
