"""``ace-cli``: developer client for the core's IPC (stages S03, S07).

    ace-cli health                       subsystem health
    ace-cli call settings.get '{"key": "theme"}'
    ace-cli watch [--count N]            print events as they arrive (Ctrl+C to stop)
    ace-cli send echo hello              send a typed command and follow it to the end

It reads the port and token of the running core from ``runtime/ipc.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from websockets.asyncio.client import ClientConnection, connect

from ace_core.app.paths import resolve_paths
from ace_core.ipc.runtime_file import read_runtime_file
from ace_core.ipc.schemas import MAX_MESSAGE_BYTES

EXIT_OK: Final = 0
EXIT_ERROR: Final = 1
EXIT_NOT_RUNNING: Final = 2
SEND_TIMEOUT_S: Final = 60.0  # longer than a confirmation's 30 s
REPLY_GRACE_S: Final = 1.0  # after task.finished, how long to wait for ACE's reply


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
    send = commands.add_parser("send", help="send a typed command and follow it to the end")
    send.add_argument("text", nargs="+", help="the command, e.g. echo hello")
    send.add_argument("--timeout", type=float, default=SEND_TIMEOUT_S, help="seconds to wait")
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
            if args.command == "send":
                return await _send(ws, " ".join(args.text), args.timeout)
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


@dataclass
class _Follower:
    """Prints what happens to one submitted command and says when it is over."""

    message_id: str
    task_id: str | None
    finished_status: str | None = None
    exit_code: int = EXIT_OK
    seen: set[str] = field(default_factory=set)

    def feed(self, method: str, params: dict[str, Any]) -> bool:
        """Handle one event; True when the command is over."""
        if method == "message.created":
            message = params["message"]
            ours = message.get("reply_to") == self.message_id or (
                self.task_id is not None and message.get("task_id") == self.task_id
            )
            if message.get("role") != "ace" or not ours or message["id"] in self.seen:
                return False
            self.seen.add(message["id"])
            print(f"ace: {message['text']}")
            for line in (message.get("detail") or "").splitlines():
                print(f"     {line}")
            return self.task_id is None or self.finished_status is not None
        if method == "confirm.requested":
            confirmation = params["confirmation"]
            if confirmation["task_id"] != self.task_id:
                return False
            answer = json.dumps({"confirmation_id": confirmation["id"], "answer": "yes"})
            print(f"confirm: {confirmation['prompt']}")
            print(f"         answer in the sidebar, or: ace-cli call confirm.respond '{answer}'")
            return False
        if method.startswith("task.") and params["task"]["id"] == self.task_id:
            task = params["task"]
            print(f"task {task['status']}: {task['utterance']}")
            if method == "task.finished":
                self.finished_status = task["status"]
                self.exit_code = EXIT_OK if task["status"] == "succeeded" else EXIT_ERROR
        return False


async def _send(ws: ClientConnection, text: str, timeout: float) -> int:
    request_id = "cli-send"
    request = {
        "v": 1,
        "type": "request",
        "id": request_id,
        "method": "command.submit",
        "params": {"text": text},
    }
    await ws.send(json.dumps(request))
    early: list[dict[str, Any]] = []  # events that arrive before the response
    try:
        async with asyncio.timeout(timeout):
            while True:
                message = json.loads(await ws.recv())
                if message.get("id") == request_id:
                    break
                if message.get("type") == "event":
                    early.append(message)
            if message.get("type") != "response":
                print(json.dumps(message.get("error"), indent=2), file=sys.stderr)
                return EXIT_ERROR
            result = message["result"]
            follower = _Follower(message_id=result["message_id"], task_id=result["task_id"])
            for event in early:
                if follower.feed(event["method"], event["params"]):
                    return follower.exit_code
            while follower.finished_status is None:
                message = json.loads(await ws.recv())
                if message.get("type") == "event" and follower.feed(
                    message["method"], message["params"]
                ):
                    return follower.exit_code
    except TimeoutError:
        print(f"no result within {timeout:g} s", file=sys.stderr)
        return EXIT_ERROR
    # The task finished; ACE's reply (if any) follows right after.
    try:
        async with asyncio.timeout(REPLY_GRACE_S):
            while True:
                message = json.loads(await ws.recv())
                if message.get("type") == "event" and follower.feed(
                    message["method"], message["params"]
                ):
                    break
    except TimeoutError:
        pass
    return follower.exit_code
