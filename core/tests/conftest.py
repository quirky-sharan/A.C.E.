"""Shared test fixtures."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
import structlog

ACE_SETTING_ENV_VARS = (
    "ACE_LOG_LEVEL",
    "ACE_LOG_RETENTION_DAYS",
    "ACE_SHUTDOWN_TIMEOUT_S",
    "ACE_DEV",
)


@pytest.fixture(autouse=True)
def _isolated_logging() -> Iterator[None]:
    """Every test starts and ends with the default logging and structlog state."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    structlog.reset_defaults()
    root.handlers = handlers
    root.setLevel(level)


@pytest.fixture(autouse=True)
def _no_ace_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings must come only from what each test provides, not from the developer's shell."""
    for name in ACE_SETTING_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
