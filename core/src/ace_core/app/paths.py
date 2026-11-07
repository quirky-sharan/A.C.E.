r"""Where ACE keeps its files (ACE_MASTER_PLAN.md §5.8).

Normal mode:   %LOCALAPPDATA%\ACE\{data, logs, runtime, cache, config.toml}
Portable mode: <app folder>\data\{...}  - chosen by ``--portable`` or an ``ace-portable.flag`` file
               next to the executable.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

APP_DIR_NAME: Final = "ACE"
PORTABLE_FLAG_FILE: Final = "ace-portable.flag"
CONFIG_FILE_NAME: Final = "config.toml"
HOME_ENV: Final = "ACE_HOME"  # dev / test override of the normal-mode folder


@dataclass(frozen=True, slots=True)
class AppPaths:
    """All directories and files ACE owns. Build with :func:`resolve_paths` or :meth:`under`."""

    root: Path
    data: Path
    logs: Path
    runtime: Path
    cache: Path
    config_file: Path
    portable: bool

    @classmethod
    def under(cls, root: Path, *, portable: bool) -> AppPaths:
        return cls(
            root=root,
            data=root / "data",
            logs=root / "logs",
            runtime=root / "runtime",
            cache=root / "cache",
            config_file=root / CONFIG_FILE_NAME,
            portable=portable,
        )

    def ensure(self) -> None:
        """Create every directory (idempotent)."""
        for directory in (self.root, self.data, self.logs, self.runtime, self.cache):
            directory.mkdir(parents=True, exist_ok=True)


def executable_dir() -> Path:
    """Folder of the running executable (the venv's Scripts folder during development)."""
    return Path(sys.executable).resolve().parent


def resolve_paths(
    *,
    portable: bool = False,
    exe_dir: Path | None = None,
    local_app_data: Path | None = None,
) -> AppPaths:
    """Pick portable or normal mode and return the paths. Nothing is created here."""
    exe = exe_dir if exe_dir is not None else executable_dir()
    if portable or (exe / PORTABLE_FLAG_FILE).is_file():
        return AppPaths.under(exe / "data", portable=True)
    home = os.environ.get(HOME_ENV)
    if home and local_app_data is None:
        # Development / testing only (§17.4): keep ACE's files elsewhere without changing
        # LOCALAPPDATA, which Windows' own Start-menu list depends on (S08, PL-0010).
        return AppPaths.under(Path(home), portable=False)
    base = local_app_data if local_app_data is not None else _local_app_data()
    return AppPaths.under(base / APP_DIR_NAME, portable=False)


def _local_app_data() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    return Path(value) if value else Path.home() / "AppData" / "Local"
