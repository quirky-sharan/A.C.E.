"""``runtime/ipc.json``: how local clients (ace-cli, the native host) find the running core.

The file holds the port and the per-run token, so only the current Windows user may read it
(§5.5). It is removed when the core stops.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from ace_core.ipc.security import restrict_to_current_user

RUNTIME_FILE_NAME: Final = "ipc.json"


@dataclass(frozen=True, slots=True)
class IpcEndpoint:
    port: int
    token: str
    pid: int
    version: str


def write_runtime_file(runtime_dir: Path, endpoint: IpcEndpoint) -> Path:
    """Create the file private first (empty, then locked down), then write and move it in place."""
    runtime_dir.mkdir(parents=True, exist_ok=True)
    final = runtime_dir / RUNTIME_FILE_NAME
    staging = runtime_dir / (RUNTIME_FILE_NAME + ".tmp")
    staging.unlink(missing_ok=True)
    staging.touch()
    restrict_to_current_user(staging)
    staging.write_text(json.dumps(asdict(endpoint)), encoding="utf-8")
    os.replace(staging, final)
    return final


def read_runtime_file(runtime_dir: Path) -> IpcEndpoint | None:
    path = runtime_dir / RUNTIME_FILE_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return IpcEndpoint(
            port=int(data["port"]),
            token=str(data["token"]),
            pid=int(data["pid"]),
            version=str(data["version"]),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def remove_runtime_file(runtime_dir: Path, *, pid: int) -> None:
    """Delete the file, but only if it still belongs to this process (never a newer core's file)."""
    endpoint = read_runtime_file(runtime_dir)
    if endpoint is not None and endpoint.pid == pid:
        (runtime_dir / RUNTIME_FILE_NAME).unlink(missing_ok=True)
