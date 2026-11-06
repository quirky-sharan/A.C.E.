"""Command-line interface of ``ace-core``."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from ace_core.app.version import __version__

CHROME_EXTENSION_ORIGIN_PREFIX: Final = "chrome-extension://"
LOG_LEVELS: Final = ("DEBUG", "INFO", "WARNING", "ERROR")


@dataclass(frozen=True, slots=True)
class CliOptions:
    dev: bool = False
    portable: bool = False
    log_level: str | None = None
    native_host: bool = False


def parse_args(argv: Sequence[str]) -> CliOptions:
    """Parse arguments. Chrome starts a native-messaging host with its origin first (§11.2)."""
    if argv and argv[0].startswith(CHROME_EXTENSION_ORIGIN_PREFIX):
        return CliOptions(native_host=True)
    parser = argparse.ArgumentParser(
        prog="ace-core", description="ACE core service (see ACE_MASTER_PLAN.md)."
    )
    parser.add_argument("--dev", action="store_true", help="also print readable logs to stderr")
    parser.add_argument(
        "--portable", action="store_true", help="keep all data next to the executable"
    )
    parser.add_argument(
        "--log-level", choices=LOG_LEVELS, type=str.upper, help="override the configured log level"
    )
    parser.add_argument(
        "--native-host",
        action="store_true",
        help="run as the Chrome native-messaging host (manual testing; arrives in S24)",
    )
    parser.add_argument("--version", action="version", version=f"ace-core {__version__}")
    namespace = parser.parse_args(list(argv))
    return CliOptions(
        dev=namespace.dev,
        portable=namespace.portable,
        log_level=namespace.log_level,
        native_host=namespace.native_host,
    )
