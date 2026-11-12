"""Which in-process events IPC clients may see, and their payloads. An explicit allowlist:
internal events never leak to clients unless they are mapped here."""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel

from ace_core.app.events import AppStopping, Event
from ace_core.app.health import HealthChanged
from ace_core.app.state import StateChanged
from ace_core.brain.records import (
    ClarificationRequested,
    ConfirmationRequested,
    MessageCreated,
    TaskChanged,
)
from ace_core.db.events import DatabaseRecovered, SettingChanged
from ace_core.ipc.methods import (
    clarification_info,
    confirmation_info,
    core_state_info,
    message_info,
    task_info,
)
from ace_core.ipc.schemas import (
    AudioLevelPayload,
    ClarifyRequestedPayload,
    ConfirmRequestedPayload,
    DatabaseRecoveredPayload,
    HealthChangedPayload,
    MessageCreatedPayload,
    SessionReadyPayload,
    SettingsChangedPayload,
    StateChangedPayload,
    SystemStoppingPayload,
    TaskEventPayload,
    TranscriptFinalPayload,
)
from ace_core.voice.audio import AudioLevel
from ace_core.voice.listen import TranscriptFinal

EVENT_PAYLOADS: Final[dict[str, type[BaseModel]]] = {
    "session.ready": SessionReadyPayload,  # sent once, right after a client authenticates
    "state.changed": StateChangedPayload,
    "health.changed": HealthChangedPayload,
    "system.stopping": SystemStoppingPayload,
    "db.recovered": DatabaseRecoveredPayload,
    "task.created": TaskEventPayload,
    "task.updated": TaskEventPayload,
    "task.finished": TaskEventPayload,
    "confirm.requested": ConfirmRequestedPayload,
    "clarify.requested": ClarifyRequestedPayload,
    "message.created": MessageCreatedPayload,
    "audio.level": AudioLevelPayload,
    "transcript.final": TranscriptFinalPayload,
    "settings.changed": SettingsChangedPayload,  # the key only: clients re-read the value
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
    if isinstance(event, TaskChanged):
        return f"task.{event.change.value}", TaskEventPayload(task=task_info(event.task))
    if isinstance(event, ConfirmationRequested):
        return "confirm.requested", ConfirmRequestedPayload(
            confirmation=confirmation_info(event.confirmation)
        )
    if isinstance(event, ClarificationRequested):
        return "clarify.requested", ClarifyRequestedPayload(
            clarification=clarification_info(event.clarification)
        )
    if isinstance(event, MessageCreated):
        return "message.created", MessageCreatedPayload(message=message_info(event.message))
    if isinstance(event, TranscriptFinal):
        return "transcript.final", TranscriptFinalPayload(
            text=event.text,
            confidence=event.confidence,
            language=event.language,
            verdict=event.verdict,
            elapsed_ms=event.elapsed_ms,
        )
    if isinstance(event, AudioLevel):
        return "audio.level", AudioLevelPayload(level=event.level)
    if isinstance(event, SettingChanged):
        return "settings.changed", SettingsChangedPayload(key=event.key, deleted=event.deleted)
    return None
