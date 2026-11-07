"""ace-cli against a real IPC server: health, call, errors, watch, send, not-running."""

import asyncio
import json
import os
import socket
from pathlib import Path

import pytest
from ipc_harness import start_harness, stop_harness

from ace_core.app.events import AppStopping
from ace_core.app.state import ConversationState
from ace_core.brain.records import ConfirmationAnswer
from ace_core.ipc.cli import EXIT_ERROR, EXIT_NOT_RUNNING, EXIT_OK, build_parser, run
from ace_core.ipc.runtime_file import IpcEndpoint, write_runtime_file


async def test_cli_health_call_errors_and_watch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    harness = await start_harness(tmp_path)
    runtime = harness.container.paths.runtime
    endpoint = IpcEndpoint(harness.server.port, harness.server.token, os.getpid(), "test")
    write_runtime_file(runtime, endpoint)
    parser = build_parser()
    capsys.readouterr()  # drop start-up log lines (structlog prints to stdout in tests)
    try:
        assert await run(parser.parse_args(["health"]), runtime) == EXIT_OK
        assert json.loads(capsys.readouterr().out)["overall"] == "ok"

        args = parser.parse_args(["call", "settings.set", '{"key": "theme", "value": "dark"}'])
        assert await run(args, runtime) == EXIT_OK
        capsys.readouterr()
        args = parser.parse_args(["call", "settings.get", '{"key": "theme"}'])
        assert await run(args, runtime) == EXIT_OK
        assert json.loads(capsys.readouterr().out)["value"] == "dark"

        assert await run(parser.parse_args(["call", "nope.method"]), runtime) == EXIT_ERROR
        assert "E_IPC_UNKNOWN_METHOD" in capsys.readouterr().err

        watcher = asyncio.create_task(run(parser.parse_args(["watch", "--count", "1"]), runtime))
        async with asyncio.timeout(5):
            while harness.server.client_count == 0:
                await asyncio.sleep(0.01)
        await harness.container.state.update(conversation=ConversationState.THINKING)
        assert await asyncio.wait_for(watcher, 5) == EXIT_OK
        assert "state.changed" in capsys.readouterr().out
    finally:
        await stop_harness(harness)


async def test_cli_reports_a_core_that_is_not_running(tmp_path: Path) -> None:
    assert await run(build_parser().parse_args(["health"]), tmp_path) == EXIT_NOT_RUNNING


async def test_cli_rejects_params_that_are_not_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_runtime_file(tmp_path, IpcEndpoint(1, "t" * 43, os.getpid(), "test"))
    args = build_parser().parse_args(["call", "settings.get", "{not json"])
    assert await run(args, tmp_path) == EXIT_ERROR
    assert "JSON" in capsys.readouterr().err


async def test_cli_reports_a_stale_runtime_file(tmp_path: Path) -> None:
    with socket.socket() as probe:  # a free port that nothing listens on
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    write_runtime_file(tmp_path, IpcEndpoint(port, "t" * 43, os.getpid(), "test"))
    assert await run(build_parser().parse_args(["health"]), tmp_path) == EXIT_NOT_RUNNING


async def test_cli_watch_reports_when_the_core_goes_away(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    harness = await start_harness(tmp_path)
    runtime = harness.container.paths.runtime
    endpoint = IpcEndpoint(harness.server.port, harness.server.token, os.getpid(), "test")
    write_runtime_file(runtime, endpoint)
    try:
        watcher = asyncio.create_task(run(build_parser().parse_args(["watch"]), runtime))
        async with asyncio.timeout(5):
            while harness.server.client_count == 0:
                await asyncio.sleep(0.01)
        await harness.container.bus.publish(AppStopping(reason="test"))
        await harness.server.stop()
        assert await asyncio.wait_for(watcher, 5) == EXIT_OK
        captured = capsys.readouterr()
        assert '"system.stopping"' in captured.out
        assert "closed the connection (1001" in captured.err
    finally:
        await stop_harness(harness)


async def test_cli_send_follows_a_command_to_the_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    harness = await start_harness(tmp_path)
    runtime = harness.container.paths.runtime
    endpoint = IpcEndpoint(harness.server.port, harness.server.token, os.getpid(), "test")
    write_runtime_file(runtime, endpoint)
    parser = build_parser()
    capsys.readouterr()
    try:
        assert await run(parser.parse_args(["send", "echo", "hello"]), runtime) == EXIT_OK
        out = capsys.readouterr().out
        assert "task succeeded: echo hello" in out
        assert "ace: hello" in out

        assert await run(parser.parse_args(["send", "help"]), runtime) == EXIT_OK
        assert '"open spotify"' in capsys.readouterr().out  # the detail lines are printed

        assert await run(parser.parse_args(["send", "demo", "forbidden"]), runtime) == EXIT_ERROR
        assert "forbidden list" in capsys.readouterr().out

        assert await run(parser.parse_args(["send", "what", "is", "this"]), runtime) == EXIT_OK
        assert "I don't know that one yet" in capsys.readouterr().out

        sender = asyncio.create_task(run(parser.parse_args(["send", "demo dangerous"]), runtime))
        async with asyncio.timeout(5):
            while not harness.container.supervisor.pending():
                await asyncio.sleep(0.01)
        [pending] = harness.container.supervisor.pending()
        harness.container.pipeline.respond(pending.id, ConfirmationAnswer.YES)
        assert await asyncio.wait_for(sender, 5) == EXIT_OK
        out = capsys.readouterr().out
        assert "confirm: Run the demo dangerous action" in out
        assert "ace-cli call confirm.respond" in out
        assert "task succeeded" in out
    finally:
        await stop_harness(harness)
