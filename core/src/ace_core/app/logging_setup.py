"""Structured logging (ACE_MASTER_PLAN.md §5.8, §15.1, D-46).

- Every record (structlog or plain ``logging``) passes the redaction processor.
- File: one JSON object per line in ``logs/core-YYYYMMDD.jsonl`` (local date), ``ts`` in UTC,
  files older than the retention window are deleted.
- Dev mode also prints readable lines to stderr.
- stdout stays reserved for protocol lines such as ``ACE_READY``.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Final, TextIO

import structlog
from structlog.typing import Processor

from ace_core.security.redaction import redact_event

LOG_FILE_PREFIX: Final = "core-"
LOG_FILE_SUFFIX: Final = ".jsonl"
_LOG_FILE_NAME: Final = re.compile(r"^core-(\d{8})\.jsonl$")


class DailyJsonlFileHandler(logging.Handler):
    """Append records to ``<dir>/core-YYYYMMDD.jsonl``; switch files when the day changes."""

    def __init__(
        self,
        directory: Path,
        *,
        retention_days: int,
        today: Callable[[], date] = date.today,
    ) -> None:
        super().__init__()
        self._directory = directory
        self._retention_days = retention_days
        self._today = today
        self._day: date | None = None
        self._stream: TextIO | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            day = self._today()
            stream = self._stream
            if stream is None or day != self._day:
                stream = self._open_for(day)
            stream.write(line + "\n")
            stream.flush()
        except Exception:  # logging must never crash the app
            self.handleError(record)

    def _open_for(self, day: date) -> TextIO:
        self._close_stream()
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{LOG_FILE_PREFIX}{day:%Y%m%d}{LOG_FILE_SUFFIX}"
        self._stream = path.open("a", encoding="utf-8", newline="\n")
        self._day = day
        prune_old_logs(self._directory, keep_days=self._retention_days, today=day)
        return self._stream

    def _close_stream(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def close(self) -> None:
        self.acquire()
        try:
            self._close_stream()
        finally:
            self.release()
        super().close()


def prune_old_logs(directory: Path, *, keep_days: int, today: date) -> list[Path]:
    """Delete ``core-YYYYMMDD.jsonl`` files older than ``keep_days`` (today counts as day 1)."""
    cutoff = today - timedelta(days=keep_days - 1)
    deleted: list[Path] = []
    for path in directory.glob(f"{LOG_FILE_PREFIX}*{LOG_FILE_SUFFIX}"):
        match = _LOG_FILE_NAME.match(path.name)
        if match is None:
            continue
        try:
            file_day = datetime.strptime(match.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        if file_day < cutoff:
            path.unlink(missing_ok=True)
            deleted.append(path)
    return deleted


def configure_logging(
    *,
    logs_dir: Path,
    level: str,
    dev: bool,
    retention_days: int,
    console: TextIO | None = None,
) -> Callable[[], None]:
    """Route structlog and stdlib logging through redaction to the daily JSONL file.

    Returns a teardown function that restores the previous logging state.
    """
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_event,
    ]

    file_handler = DailyJsonlFileHandler(logs_dir, retention_days=retention_days)
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    handlers: list[logging.Handler] = [file_handler]
    if dev:
        stream = console if console is not None else sys.stderr
        console_handler = logging.StreamHandler(stream)
        console_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=shared,
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(colors=stream.isatty()),
                ],
            )
        )
        handlers.append(console_handler)

    root = logging.getLogger()
    previous_handlers, previous_level = root.handlers[:], root.level
    root.handlers = handlers
    root.setLevel(level)
    logging.captureWarnings(True)
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    def teardown() -> None:
        for handler in handlers:
            handler.close()
        root.handlers = previous_handlers
        root.setLevel(previous_level)
        logging.captureWarnings(False)
        structlog.reset_defaults()

    return teardown
