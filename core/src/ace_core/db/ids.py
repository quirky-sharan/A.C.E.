"""Record IDs: UUIDv7 strings (RFC 9562 §5.7, D-48).

Layout: 48-bit Unix time in ms | version 7 | 12-bit counter | variant 0b10 | 62 random bits.
The 12-bit field is a counter (RFC 9562 §6.2, method 1), randomly seeded every millisecond, so IDs
made by this process always sort in creation order - even within one millisecond or if the clock
steps backwards. Switch to ``uuid.uuid7()`` once ACE moves to Python 3.14+.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from collections.abc import Callable
from typing import Final

_COUNTER_MAX: Final = 0xFFF
_TIMESTAMP_MASK: Final = (1 << 48) - 1
_RAND_B_MASK: Final = (1 << 62) - 1


def _random_counter_seed() -> int:
    # 11 random bits: the top counter bit starts at 0, a guard against early rollover (RFC 9562).
    return int.from_bytes(os.urandom(2)) & 0x7FF


class UuidV7Generator:
    """Thread-safe, monotonic UUIDv7 generator. ``time_ns`` is injectable for tests."""

    def __init__(self, time_ns: Callable[[], int] = time.time_ns) -> None:
        self._time_ns = time_ns
        self._lock = threading.Lock()
        self._last_ms = -1
        self._counter = 0

    def new(self) -> str:
        with self._lock:
            now_ms = self._time_ns() // 1_000_000
            if now_ms > self._last_ms:
                self._last_ms = now_ms
                self._counter = _random_counter_seed()
            else:  # same millisecond, or the clock went backwards: keep order via the counter
                self._counter += 1
                if self._counter > _COUNTER_MAX:  # rollover: step the timestamp forward
                    self._last_ms += 1
                    self._counter = _random_counter_seed()
            timestamp, counter = self._last_ms, self._counter
        rand_b = int.from_bytes(os.urandom(8)) & _RAND_B_MASK
        value = (
            (timestamp & _TIMESTAMP_MASK) << 80 | 0x7 << 76 | counter << 64 | 0b10 << 62 | rand_b
        )
        return str(uuid.UUID(int=value))


_default_generator = UuidV7Generator()


def new_id() -> str:
    """A new UUIDv7 string such as ``019a5a3c-9e2f-7c01-8f3a-2b9d4e6f1a7c``."""
    return _default_generator.new()
