"""The COM / shell thread (ACE_MASTER_PLAN.md §5.7): one single-threaded-apartment worker that runs
every shell and window call in order, per-monitor DPI aware, so coordinates are real pixels."""

from __future__ import annotations

import asyncio
import ctypes
import functools
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Final, TypeVar

T = TypeVar("T")

THREAD_NAME: Final = "ace-com"
# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 ((DPI_AWARENESS_CONTEXT)-4), Windows 10 1703+.
_PER_MONITOR_AWARE_V2: Final = -4


def _init_thread() -> None:
    import pythoncom

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(_PER_MONITOR_AWARE_V2))


class ComThread:
    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None

    async def run(self, fn: Callable[..., T], *args: Any) -> T:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=THREAD_NAME, initializer=_init_thread
            )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, functools.partial(fn, *args))

    async def close(self) -> None:
        executor, self._executor = self._executor, None
        if executor is not None:
            await asyncio.to_thread(executor.shutdown, True)
