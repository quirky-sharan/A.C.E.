"""Logging: redacted JSON lines, level filter, dev console, daily rotation, retention."""

import io
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import structlog

from ace_core.app.logging_setup import DailyJsonlFileHandler, configure_logging, prune_old_logs

FAKE_GROQ = "gsk_" + "x" * 30


def read_json_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_structlog_and_stdlib_records_become_redacted_json(tmp_path: Path) -> None:
    teardown = configure_logging(logs_dir=tmp_path, level="INFO", dev=False, retention_days=14)
    try:
        structlog.stdlib.get_logger("ace.test").info(
            "provider configured", api_key=FAKE_GROQ, note=f"key {FAKE_GROQ}", retries=3
        )
        logging.getLogger("thirdparty").warning("token=%s", "abc123secret")
    finally:
        teardown()

    files = list(tmp_path.glob("core-*.jsonl"))
    assert [f.name for f in files] == [f"core-{date.today():%Y%m%d}.jsonl"]
    ours, foreign = read_json_lines(files[0])
    assert ours["event"] == "provider configured"
    assert ours["level"] == "info"
    assert ours["logger"] == "ace.test"
    assert ours["api_key"] == "[REDACTED]"
    assert FAKE_GROQ not in ours["note"]
    assert ours["retries"] == 3
    assert ours["ts"].endswith("Z")
    assert foreign["logger"] == "thirdparty"
    assert foreign["level"] == "warning"
    assert "abc123secret" not in foreign["event"]


def test_records_below_the_level_are_dropped(tmp_path: Path) -> None:
    teardown = configure_logging(logs_dir=tmp_path, level="INFO", dev=False, retention_days=14)
    try:
        log = structlog.stdlib.get_logger("ace.test")
        log.debug("too chatty")
        log.info("kept")
    finally:
        teardown()
    (file,) = tmp_path.glob("core-*.jsonl")
    assert [entry["event"] for entry in read_json_lines(file)] == ["kept"]


def test_dev_mode_also_prints_readable_lines(tmp_path: Path) -> None:
    console = io.StringIO()
    teardown = configure_logging(
        logs_dir=tmp_path, level="DEBUG", dev=True, retention_days=14, console=console
    )
    try:
        structlog.stdlib.get_logger("ace.test").info("hello dev", api_key=FAKE_GROQ)
    finally:
        teardown()
    output = console.getvalue()
    assert "hello dev" in output
    assert FAKE_GROQ not in output


def test_handler_switches_file_when_the_day_changes(tmp_path: Path) -> None:
    days = iter([date(2026, 11, 6), date(2026, 11, 6), date(2026, 11, 7)])
    handler = DailyJsonlFileHandler(tmp_path, retention_days=14, today=lambda: next(days))
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("ace.rollover-test")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        for message in ("one", "two", "three"):
            logger.info(message)
    finally:
        logger.removeHandler(handler)
        handler.close()
    assert (tmp_path / "core-20261106.jsonl").read_text(encoding="utf-8").splitlines() == [
        "one",
        "two",
    ]
    assert (tmp_path / "core-20261107.jsonl").read_text(encoding="utf-8").splitlines() == ["three"]


def test_prune_keeps_only_the_retention_window(tmp_path: Path) -> None:
    for day in ("20261001", "20261023", "20261024", "20261106"):
        (tmp_path / f"core-{day}.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a log", encoding="utf-8")
    (tmp_path / "core-garbage.jsonl").write_text("{}\n", encoding="utf-8")

    deleted = prune_old_logs(tmp_path, keep_days=14, today=date(2026, 11, 6))

    assert sorted(p.name for p in deleted) == ["core-20261001.jsonl", "core-20261023.jsonl"]
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == [
        "core-20261024.jsonl",
        "core-20261106.jsonl",
        "core-garbage.jsonl",
        "notes.txt",
    ]
