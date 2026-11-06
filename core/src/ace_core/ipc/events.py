"""Which in-process events IPC clients may see, and their payloads. An explicit allowlist:
internal events never leak to clients unless they are mapped here."""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel

from ace_core.app.events import AppStopping, Event
from ace_core.app.health import HealthChanged
from ace_core.app.state import StateChanged
from ace_core.db.events import DatabaseRecovered
from ace_core.ipc.methods import core_state_info
from ace_core.ipc.schemas import (
    DatabaseRecoveredPayload,
    HealthChangedPayload,
    SessionReadyPayload,
    StateChangedPayload,
    SystemStoppingPayload,
)

EVENT_PAYLOADS: Final[dict[str, type[BaseModel]]] = {
    "session.ready": SessionReadyPayload,  # sent once, right after a client authenticates
    "state.changed": StateChangedPayload,
    "health.changed": HealthChangedPayload,
    "system.stopping": SystemStoppingPayload,
    "db.recovered": DatabaseRecoveredPayload,
}


def to_ipc_event(event: Event) -> tuple[str, BaseModel] | None:
    """The IPC event name and payload for ``event``, or None if clients must not see it."""
    if isinstance(event, StateChanged):
        return "state.changed", StateChangedPayload(
            state=core_state_info(event.state), previous=core_state_info(event.previous)
        )
    if isinstance(event, HealthChanged):
        return "health.changed", HealthChangedPayload(
            subsystem=event.subsystem,
            status=event.status,
            previous=event.previous,
            detail=event.detail,
        )
    if isinstance(event, AppStopping):
        return "system.stopping", SystemStoppingPayload(reason=event.reason)
    if isinstance(event, DatabaseRecovered):
        return "db.recovered", DatabaseRecoveredPayload(
            corrupt_copy=event.corrupt_copy, restored_from=event.restored_from
        )
    return None
