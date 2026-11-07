"""The verification mode (D-09, D-53): stored in the settings table, set from the tray, the
Control Center or by command; the verification council (S18) acts on it."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import JsonValue

MODE_SETTING: Final = "verification.mode"


class VerificationMode(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    PARANOID = "paranoid"


DEFAULT_MODE: Final = VerificationMode.BALANCED


def parse_mode(value: JsonValue) -> VerificationMode | None:
    """The mode for a stored value, or None if the value is not a valid mode."""
    if isinstance(value, str):
        try:
            return VerificationMode(value)
        except ValueError:
            return None
    return None
