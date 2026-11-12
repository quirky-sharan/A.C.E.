"""Typed configuration (ACE_MASTER_PLAN.md §5.6, D-45).

Priority, highest first: command-line overrides > ``ACE_*`` environment variables >
``config.toml`` > defaults. Unknown keys in ``config.toml`` are rejected so typos never pass
silently. (A DB-backed settings layer is added in a later stage.)
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    """Core settings. Every field can be set as ``ACE_<FIELD_NAME>`` or in ``config.toml``."""

    model_config = SettingsConfigDict(env_prefix="ACE_", extra="forbid", frozen=True)

    log_level: LogLevel = "INFO"
    log_retention_days: int = Field(default=14, ge=1, le=365)
    shutdown_timeout_s: float = Field(default=5.0, gt=0, le=5.0)
    dev: bool = False
    db_backups_keep: int = Field(default=7, ge=1, le=100)  # regular backups kept (§13.4)
    audit_retention_days: int = Field(default=90, ge=1, le=3650)  # D-26
    ipc_port: int = Field(default=0, ge=0, le=65535)  # 0 = a random free port (§5.6)
    safe_mode: bool = False  # set by ace-desktop after repeated crashes (§5.6, D-52)
    audio_enabled: bool = True  # false: no microphone or speaker use at all (tests, servers)
    models_dir: Path | None = None  # ACE_MODELS_DIR (E:\ACE-Models here); default <root>\models


def load_settings(
    *, config_file: Path | None, overrides: Mapping[str, Any] | None = None
) -> Settings:
    """Build :class:`Settings` from overrides, environment, ``config_file`` (optional), defaults."""
    toml_file = config_file

    class _LayeredSettings(Settings):
        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            # The first source wins: pydantic-settings merges later sources underneath.
            sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
            if toml_file is not None:
                sources.append(TomlConfigSettingsSource(settings_cls, toml_file=toml_file))
            return tuple(sources)

    return _LayeredSettings(**dict(overrides or {}))
