"""Configuration precedence: CLI overrides > ACE_* env > config.toml > defaults."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from ace_core.app.config import load_settings


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_when_no_file_env_or_overrides(tmp_path: Path) -> None:
    settings = load_settings(config_file=tmp_path / "missing.toml")
    assert settings.log_level == "INFO"
    assert settings.log_retention_days == 14
    assert settings.shutdown_timeout_s == 5.0
    assert settings.dev is False


def test_file_overrides_defaults(tmp_path: Path) -> None:
    config = write(tmp_path / "config.toml", 'log_level = "WARNING"\nlog_retention_days = 7\n')
    settings = load_settings(config_file=config)
    assert settings.log_level == "WARNING"
    assert settings.log_retention_days == 7


def test_environment_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = write(tmp_path / "config.toml", 'log_level = "WARNING"\n')
    monkeypatch.setenv("ACE_LOG_LEVEL", "ERROR")
    assert load_settings(config_file=config).log_level == "ERROR"


def test_overrides_beat_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACE_LOG_LEVEL", "ERROR")
    settings = load_settings(config_file=None, overrides={"log_level": "DEBUG", "dev": True})
    assert settings.log_level == "DEBUG"
    assert settings.dev is True


def test_unknown_key_in_file_is_rejected(tmp_path: Path) -> None:
    config = write(tmp_path / "config.toml", 'log_levle = "DEBUG"\n')
    with pytest.raises(ValidationError):
        load_settings(config_file=config)


@pytest.mark.parametrize(
    "line", ['log_level = "LOUD"', "shutdown_timeout_s = 30", "log_retention_days = 0"]
)
def test_invalid_values_are_rejected(tmp_path: Path, line: str) -> None:
    config = write(tmp_path / "config.toml", line + "\n")
    with pytest.raises(ValidationError):
        load_settings(config_file=config)


def test_unrelated_ace_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACE_MODELS_DIR", r"E:\ACE-Models")
    assert load_settings(config_file=None).log_level == "INFO"


def test_settings_are_immutable() -> None:
    settings = load_settings(config_file=None)
    with pytest.raises(ValidationError):
        settings.log_level = "DEBUG"  # type: ignore[misc]
