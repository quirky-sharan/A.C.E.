"""Entry point: early exits in-process; real process end to end (READY, Ctrl+Break, exit)."""

from __future__ import annotations

import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO

import pytest

from ace_core.app.lifecycle import EXIT_STARTUP_FAILED
from ace_core.app.main import EXIT_NOT_IMPLEMENTED, main
from ace_core.app.paths import AppPaths


def test_native_host_mode_is_not_implemented_yet(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["chrome-extension://abcdef/"]) == EXIT_NOT_IMPLEMENTED
    assert "S24" in capsys.readouterr().err


def test_invalid_config_file_stops_startup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = AppPaths.under(tmp_path, portable=False)
    paths.ensure()
    paths.config_file.write_text('log_level = "LOUD"\n', encoding="utf-8")
    assert main([], paths=paths) == EXIT_STARTUP_FAILED
    assert "cannot start" in capsys.readouterr().err


def _pump(stream: IO[str], lines: queue.Queue[str]) -> None:
    for line in stream:
        lines.put(line)


@pytest.mark.skipif(sys.platform != "win32", reason="uses Windows console control events")
def test_process_prints_ready_and_exits_cleanly_on_ctrl_break(tmp_path: Path) -> None:
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "ace_core"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    stdout: queue.Queue[str] = queue.Queue()
    stderr: queue.Queue[str] = queue.Queue()
    assert proc.stdout is not None
    assert proc.stderr is not None
    threading.Thread(target=_pump, args=(proc.stdout, stdout), daemon=True).start()
    threading.Thread(target=_pump, args=(proc.stderr, stderr), daemon=True).start()
    try:
        ready = stdout.get(timeout=30)
        assert re.fullmatch(r"ACE_READY port=[1-9]\d*", ready.strip()), ready
        runtime_file = tmp_path / "ACE" / "runtime" / "ipc.json"
        assert runtime_file.is_file()
        try:
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
        except OSError as exc:  # no shared console to deliver the event (some CI runners)
            pytest.skip(f"cannot deliver CTRL_BREAK_EVENT here: {exc}")
        started = time.monotonic()
        exit_code = proc.wait(timeout=10)
        elapsed = time.monotonic() - started
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    errors = "".join(stderr.queue)
    assert exit_code == 0, errors
    assert elapsed < 2.0
    (log_file,) = (tmp_path / "ACE" / "logs").glob("core-*.jsonl")
    events = [json.loads(line)["event"] for line in log_file.read_text("utf-8").splitlines()]
    assert "ready" in events
    assert "ipc listening" in events
    assert "shutdown complete" in events
    assert not runtime_file.exists()  # removed on a clean shutdown


def test_supervised_process_talks_over_stdio_and_stops_at_end_of_input(tmp_path: Path) -> None:
    """What ace-desktop does (D-52): token in the environment, READY, snapshot, input, close."""
    token = "ab" * 32
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path), "ACE_IPC_TOKEN": token}
    proc = subprocess.Popen(
        [sys.executable, "-m", "ace_core", "--supervised", "--safe-mode"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    stdout: queue.Queue[str] = queue.Queue()
    stderr: queue.Queue[str] = queue.Queue()
    assert proc.stdin is not None
    assert proc.stdout is not None
    assert proc.stderr is not None
    threading.Thread(target=_pump, args=(proc.stdout, stdout), daemon=True).start()
    threading.Thread(target=_pump, args=(proc.stderr, stderr), daemon=True).start()
    try:
        assert re.fullmatch(r"ACE_READY port=[1-9]\d*", stdout.get(timeout=30).strip())
        prefix, _, payload = stdout.get(timeout=10).strip().partition(" ")
        assert prefix == "ACE_DESKTOP"
        snapshot = json.loads(payload)
        assert snapshot["hotkeys"]["emergency_stop"] == "Ctrl+Alt+Escape"
        assert snapshot["state"]["conversation"] == "asleep"
        endpoint = json.loads((tmp_path / "ACE" / "runtime" / "ipc.json").read_text("utf-8"))
        assert endpoint["token"] == token  # the shell's token, not a generated one

        proc.stdin.write('{"type": "input", "action": "emergency_stop", "source": "hotkey"}\n')
        proc.stdin.flush()
        proc.stdin.close()  # what the shell does to quit
        started = time.monotonic()
        exit_code = proc.wait(timeout=10)
        elapsed = time.monotonic() - started
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    assert exit_code == 0, "".join(stderr.queue)
    assert elapsed < 5.0
    (log_file,) = (tmp_path / "ACE" / "logs").glob("core-*.jsonl")
    records = [json.loads(line) for line in log_file.read_text("utf-8").splitlines()]
    events = [record["event"] for record in records]
    assert "running in safe mode" in events
    assert "desktop link enabled" in events
    (desktop_input,) = [r for r in records if r["event"] == "desktop input"]
    assert desktop_input["action"] == "emergency_stop"
    (requested,) = [r for r in records if r["event"] == "shutdown requested"]
    assert requested["reason"] == "the desktop shell closed the control channel"
    assert "shutdown complete" in events
