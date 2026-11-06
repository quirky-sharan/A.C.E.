"""Command-line parsing."""

import pytest

from ace_core.app.cli import CliOptions, parse_args


def test_defaults() -> None:
    assert parse_args([]) == CliOptions()


def test_flags_and_case_insensitive_log_level() -> None:
    assert parse_args(["--dev", "--portable", "--log-level", "debug"]) == CliOptions(
        dev=True, portable=True, log_level="DEBUG"
    )


def test_chrome_origin_argument_selects_native_host_mode() -> None:
    assert parse_args(["chrome-extension://abcdef/", "--parent-window=0"]).native_host is True


def test_invalid_log_level_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--log-level", "LOUD"])
    assert excinfo.value.code == 2


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.startswith("ace-core ")
