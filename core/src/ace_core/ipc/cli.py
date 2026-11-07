"""``ace-cli``: developer client for the core's IPC (stage S03).

    ace-cli health                       subsystem health
    ace-cli call settings.get '{"key": "theme"}'
    ace-cli watch [--count N]            print events as they arrive (Ctrl+C to stop)

It reads the port and token of the running core from ``runtime/ipc.json``.
(``ace-cli send <text>`` arrives with ``command.submit`` in S07.)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from websockets.asyncio.client import ClientConnection, connect

from ace_core.app.paths import resolve_paths
from ace_core.ipc.runtime_file import read_runtime_file
from ace_core.ipc.schemas import MAX_MESSAGE_BYTES

EXIT_OK: Final = 0
EXIT_ERROR: Final = 1
EXIT_NOT_RUNNING: Final = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ace-cli", description="Talk to a running ace-core.")
    parser.add_argument("--portable", action="store_true", help="the core runs in portable mode")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("health", help="show subsystem health")
    call = commands.add_parser("call", help="call any IPC method")
    call.add_argument("method")
    call.add_argument("params", nargs="?", default="{}", help="JSON object with the params")
    watch = commands.add_parser("watch", help="print events as they arrive")
    watch.add_argument("--count", type=int, default=0, help="stop after N events (0 = forever)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime_dir = resolve_paths(portable=args.portable).runtime
    try:
        return asyncio.run(run(args, runtime_dir))
    except KeyboardInterrupt:
        return EXIT_OK


async def run(args: argparse.Namespace, runtime_dir: Path) -> int:
    endpoint = read_runtime_file(runtime_dir)
    if endpoint is None:
        print("ace-core is not running (no runtime/ipc.json found).", file=sys.stderr)
        return EXIT_NOT_RUNNING
    try:
        params = json.loads(args.params) if args.command == "call" else {}
    except ValueError:
        print("params must be a JSON object", file=sys.stderr)
        return EXIT_ERROR
    url = f"ws://127.0.0.1:{endpoint.port}/ws"
    try:
        async with connect(url, max_size=MAX_MESSAGE_BYTES, open_timeout=5) as ws:
            await ws.send(json.dumps({"v": 1, "type": "auth", "token": endpoint.token}))
            ready = json.loads(await ws.recv())
            if ready.get("method") != "session.ready":
                print(f"unexpected first message: {ready}", file=sys.stderr)
                return EXIT_ERROR
            if args.command == "health":
                return await _call(ws, "system.health", {})
            if args.command == "call":
                return await _call(ws, args.method, params)
            return await _watch(ws, args.count)
    except OSError as exc:
        print(f"cannot reach ace-core on port {endpoint.port}: {exc}", file=sys.stderr)
        return EXIT_NOT_RUNNING


async def _call(ws: ClientConnection, method: str, params: Any) -> int:
    request_id = "cli-1"
    request = {"v": 1, "type": "request", "id": request_id, "method": method, "params": params}
    await ws.send(json.dumps(request))
    while True:
        message = json.loads(await ws.recv())
        if message.get("id") != request_id:
            continue  # an event arrived first
        if message.get("type") == "response":
            print(json.dumps(message["result"], indent=2, ensure_ascii=False))
            return EXIT_OK
        print(json.dumps(message.get("error"), indent=2, ensure_ascii=False), file=sys.stderr)
        return EXIT_ERROR


async def _watch(ws: ClientConnection, count: int) -> int:
    seen = 0
    async for raw in ws:
        message = json.loads(raw)
        if message.get("type") != "event":
            continue
        print(json.dumps({"event": message["method"], "params": message["params"]}), flush=True)
        seen += 1
        if count and seen >= count:
            return EXIT_OK
    print(f"ace-core closed the connection ({ws.close_code} {ws.close_reason})", file=sys.stderr)
    return EXIT_OK
