"""Entry point for ``ace-core`` / ``python -m ace_core``."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from typing import Any, Final

from pydantic import ValidationError

from ace_core.app.bootstrap import create_app
from ace_core.app.cli import CliOptions, parse_args
from ace_core.app.config import load_settings
from ace_core.app.lifecycle import EXIT_FORCED, EXIT_STARTUP_FAILED
from ace_core.app.logging_setup import configure_logging
from ace_core.app.paths import AppPaths, resolve_paths

EXIT_NOT_IMPLEMENTED: Final = 3


def main(argv: Sequence[str] | None = None, *, paths: AppPaths | None = None) -> int:
    """Run the core service and return its exit code. ``paths`` is injectable for tests."""
    options = parse_args(sys.argv[1:] if argv is None else argv)
    if options.native_host:
        sys.stderr.write("ace-core: native-messaging host mode arrives in stage S24.\n")
        return EXIT_NOT_IMPLEMENTED

    resolved = paths if paths is not None else resolve_paths(portable=options.portable)
    try:
        resolved.ensure()
        settings = load_settings(config_file=resolved.config_file, overrides=_overrides(options))
    except (OSError, ValidationError) as exc:
        sys.stderr.write(f"ace-core: cannot start: {exc}\n")
        return EXIT_STARTUP_FAILED

    teardown = configure_logging(
        logs_dir=resolved.logs,
        level=settings.log_level,
        dev=settings.dev,
        retention_days=settings.log_retention_days,
    )
    try:
        app = create_app(settings, resolved, supervised=options.supervised)
        return asyncio.run(app.run())
    except KeyboardInterrupt:  # Ctrl+C before the signal handlers were installed
        return EXIT_FORCED
    finally:
        teardown()


def _overrides(options: CliOptions) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if options.dev:
        overrides["dev"] = True
    if options.log_level is not None:
        overrides["log_level"] = options.log_level
    if options.safe_mode:
        overrides["safe_mode"] = True
    return overrides
