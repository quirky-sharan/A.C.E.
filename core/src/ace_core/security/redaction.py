"""Hide secrets and personal data before anything reaches a log (ACE_MASTER_PLAN.md §15.1, rule R8).

Two layers:
- values under sensitive keys (``api_key``, ``accessToken``, ``client-secret``...) are replaced;
- every string is scanned for secret formats, bearer tokens, ``key=value`` secrets, emails, phones.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from typing import Any, Final

REDACTED: Final = "[REDACTED]"

# ProcessorFormatter bookkeeping keys that must pass through untouched.
_PASSTHROUGH_KEYS: Final = frozenset({"_record", "_from_structlog"})

# A key is sensitive when its snake_case form ENDS with one of these words: ``ipc_token`` and
# ``client_secret`` are hidden, while ``token_count`` / ``max_tokens`` stay visible.
_SENSITIVE_KEY: Final = re.compile(
    r"(?:^|_)(?:passwords?|passwd|pwd|secrets?|token|api_key|apikey|authorization|cookies?|"
    r"credentials?|private_key|otp)$"
)

_KEY_NAME_PATTERN = r"[A-Za-z0-9_-]*?(?:api[_-]?key|token|secret|passw(?:or)?d|pwd)"

_TEXT_RULES: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    # "Bearer <token>" (Authorization headers).
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + REDACTED),
    # key=value / key: value where the key name ends in a secret word (ipc_token=..., api-key: ...).
    (
        re.compile(rf"(?i)\b({_KEY_NAME_PATTERN})(\s*[=:]\s*)([\"']?)[^\s\"',;&]+"),
        r"\1\2\3" + REDACTED,
    ),
    # Provider key formats.
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "[REDACTED:api_key]"),  # OpenAI / OpenRouter style
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), "[REDACTED:api_key]"),  # Groq
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "[REDACTED:api_key]"),  # Google
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "[REDACTED:api_key]"),  # GitHub
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"), "[REDACTED:api_key]"),  # GitHub fine-grained
    # Personal data.
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED:email]"),
    (re.compile(r"(?<![\w+])\+\d[\d\s-]{6,16}\d\b"), "[REDACTED:phone]"),  # E.164-style
    (re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)"), "[REDACTED:phone]"),  # Indian mobile numbers
)


def _snake(key: str) -> str:
    """Normalize a key: ``accessToken`` -> ``access_token``, ``x-api-key`` -> ``x_api_key``."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key).replace("-", "_").lower()


def is_sensitive_key(key: str) -> bool:
    """True when values stored under ``key`` must never be logged."""
    return _SENSITIVE_KEY.search(_snake(key)) is not None


def redact_text(text: str) -> str:
    """Mask secrets and personal data inside free text."""
    for pattern, replacement in _TEXT_RULES:
        text = pattern.sub(replacement, text)
    return text


def redact_value(value: Any) -> Any:
    """Recursively redact strings, mappings, lists and tuples; other values pass through."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            k: REDACTED if isinstance(k, str) and is_sensitive_key(k) else redact_value(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_value(v) for v in value)
    return value


def redact_event(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: redact every field of a log event in place."""
    for key in list(event_dict):
        if key in _PASSTHROUGH_KEYS:
            continue
        event_dict[key] = REDACTED if is_sensitive_key(key) else redact_value(event_dict[key])
    return event_dict
