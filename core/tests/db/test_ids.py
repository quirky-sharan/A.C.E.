"""UUIDv7 ids: RFC 9562 layout, ordering within a millisecond, rollover, clock steps, threads."""

import threading
import uuid

from ace_core.db.ids import UuidV7Generator, new_id

FROZEN_NS = 1_000_000_000_000_000  # 1_000_000_000_000 ms


def test_new_id_is_an_rfc_9562_version_7_uuid() -> None:
    text = new_id()
    value = uuid.UUID(text)
    assert value.version == 7
    assert value.variant == uuid.RFC_4122
    assert text == str(value)
    assert len(text) == 36


def test_timestamp_field_holds_unix_milliseconds() -> None:
    generator = UuidV7Generator(time_ns=lambda: 1_762_444_559_639_107_000)
    assert uuid.UUID(generator.new()).int >> 80 == 1_762_444_559_639


def test_ids_made_in_the_same_millisecond_stay_in_order() -> None:
    generator = UuidV7Generator(time_ns=lambda: FROZEN_NS)
    ids = [generator.new() for _ in range(1000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == 1000


def test_counter_rollover_steps_the_timestamp_forward() -> None:
    generator = UuidV7Generator(time_ns=lambda: FROZEN_NS)
    ids = [generator.new() for _ in range(5000)]
    assert ids == sorted(ids)
    assert uuid.UUID(ids[-1]).int >> 80 > FROZEN_NS // 1_000_000


def test_clock_going_backwards_keeps_order() -> None:
    times = iter([2 * FROZEN_NS, FROZEN_NS, FROZEN_NS + 5])
    generator = UuidV7Generator(time_ns=lambda: next(times))
    ids = [generator.new() for _ in range(3)]
    assert ids == sorted(ids)


def test_ids_are_unique_across_threads() -> None:
    generator = UuidV7Generator()
    results: list[str] = []
    lock = threading.Lock()

    def work() -> None:
        local = [generator.new() for _ in range(500)]
        with lock:
            results.extend(local)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == len(set(results)) == 4000
