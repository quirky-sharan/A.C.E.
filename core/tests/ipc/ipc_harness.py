"""Shared by the IPC tests: a container with a started database and an IpcServer on a free port."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ace_core.app.config import load_settings
from ace_core.app.container import Container, build_container
from ace_core.app.paths import AppPaths
from ace_core.ipc.server import IpcLimits, IpcServer


@dataclass
class Harness:
    container: Container
    server: IpcServer

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.server.port}/ws"


async def start_harness(
    tmp_path: Path, *, dev: bool = True, limits: IpcLimits | None = None
) -> Harness:
    paths = AppPaths.under(tmp_path, portable=False)
    paths.ensure()
    container = build_container(load_settings(config_file=None, overrides={"dev": dev}), paths)
    await container.db.start()
    server = IpcServer(container, limits=limits)
    await server.start()
    return Harness(container, server)


async def stop_harness(harness: Harness) -> None:
    await harness.server.stop()
    await harness.container.pipeline.close()
    await harness.container.db.close()
