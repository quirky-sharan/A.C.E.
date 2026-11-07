"""What ACE is doing right now: conversation state + flags (ACE_MASTER_PLAN.md §5.4).

S03 adds the model and its change events so clients can follow along; the voice loop (S13) and
later stages drive the actual transitions.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ace_core.app.events import Event, EventBus


class ConversationState(StrEnum):
    ASLEEP = "asleep"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    ACTING = "acting"
    SPEAKING = "speaking"
    AWAITING_CONFIRM = "awaiting_confirm"
    AWAITING_ANSWER = "awaiting_answer"
    FOLLOW_UP = "follow_up"
    DICTATING = "dictating"
    MUTED = "muted"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class CoreState:
    conversation: ConversationState = ConversationState.ASLEEP
    game_mode: bool = False
    offline: bool = False
    dnd: bool = False
    paused_overlay: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class StateChanged(Event):
    state: CoreState
    previous: CoreState


class StateStore:
    """Holds the current :class:`CoreState`; publishes :class:`StateChanged` on every change."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._state = CoreState()

    @property
    def current(self) -> CoreState:
        return self._state

    async def update(
        self,
        *,
        conversation: ConversationState | None = None,
        game_mode: bool | None = None,
        offline: bool | None = None,
        dnd: bool | None = None,
        paused_overlay: bool | None = None,
    ) -> CoreState:
        requested: dict[str, Any] = {
            "conversation": conversation,
            "game_mode": game_mode,
            "offline": offline,
            "dnd": dnd,
            "paused_overlay": paused_overlay,
        }
        changes = {name: value for name, value in requested.items() if value is not None}
        updated = dataclasses.replace(self._state, **changes)
        if updated != self._state:
            previous, self._state = self._state, updated
            await self._bus.publish(StateChanged(state=updated, previous=previous))
        return self._state
