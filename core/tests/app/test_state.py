"""State store: changes publish one event; no-op updates publish nothing."""

from ace_core.app.events import EventBus
from ace_core.app.state import ConversationState, CoreState, StateChanged, StateStore


async def test_starts_asleep_with_all_flags_off() -> None:
    assert StateStore(EventBus()).current == CoreState()


async def test_changes_publish_one_event_and_no_ops_publish_none() -> None:
    bus = EventBus()
    changes: list[StateChanged] = []

    async def record(event: StateChanged) -> None:
        changes.append(event)

    bus.subscribe(StateChanged, record)
    store = StateStore(bus)
    await store.update(conversation=ConversationState.LISTENING)
    await store.update(conversation=ConversationState.LISTENING)  # no change
    await store.update(offline=True)

    assert [c.state.conversation for c in changes] == [
        ConversationState.LISTENING,
        ConversationState.LISTENING,
    ]
    assert changes[0].previous == CoreState()
    assert changes[1].state.offline is True
    assert store.current == CoreState(conversation=ConversationState.LISTENING, offline=True)
