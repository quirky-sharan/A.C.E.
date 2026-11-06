"""Redaction: secrets and personal data never reach logs; harmless text is untouched."""

from typing import Any

import pytest

from ace_core.security.redaction import REDACTED, is_sensitive_key, redact_event, redact_text

FAKE_OPENAI = "sk-proj-" + "a1B2c3D4e5F6g7H8i9J0"
FAKE_GROQ = "gsk_" + "Q" * 40
FAKE_GOOGLE = "AIza" + "B" * 35
FAKE_GITHUB = "ghp_" + "c" * 36


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        (f"using key {FAKE_OPENAI}", FAKE_OPENAI),
        (f"groq {FAKE_GROQ}", FAKE_GROQ),
        (f"google {FAKE_GOOGLE}", FAKE_GOOGLE),
        (f"github {FAKE_GITHUB}", FAKE_GITHUB),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig", "eyJhbGciOiJIUzI1NiJ9"),
        ("api_key=supersecretvalue123", "supersecretvalue123"),
        ("ipc_token: 3f9a8b7c6d5e4f30", "3f9a8b7c6d5e4f30"),  # pragma: allowlist secret
        ("password='hunter2'", "hunter2"),  # pragma: allowlist secret
        ("mail sharan@example.com about it", "sharan@example.com"),
        ("call +91 98765 43210 now", "98765 43210"),
        ("call 9876543210 now", "9876543210"),
    ],
)
def test_secrets_and_personal_data_are_masked(text: str, secret: str) -> None:
    redacted = redact_text(text)
    assert secret not in redacted
    assert "[REDACTED" in redacted


@pytest.mark.parametrize(
    "text",
    [
        "max_tokens=1024 input_tokens: 42",
        "2026-11-06T10:00:00+05:30 took 1500 ms",
        "sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "unix time 1762425600",
        "listening on 127.0.0.1:52144",
        "task-runner finished risk-assessment",
    ],
)
def test_harmless_text_is_untouched(text: str) -> None:
    assert redact_text(text) == text


@pytest.mark.parametrize(
    "key",
    ["api_key", "API_KEY", "accessToken", "x-api-key", "ipc_token", "client_secret", "password"],
)
def test_sensitive_keys(key: str) -> None:
    assert is_sensitive_key(key)


@pytest.mark.parametrize("key", ["input_tokens", "max_tokens", "author", "token_count", "event"])
def test_ordinary_keys(key: str) -> None:
    assert not is_sensitive_key(key)


def test_redact_event_masks_keys_and_nested_values() -> None:
    record = object()
    event: dict[str, Any] = {
        "event": "login with password=abc123",
        "token": "abc",
        "nested": {"client_secret": "x", "note": "write to a@b.co"},
        "items": [FAKE_GROQ, 5],
        "count": 5,
        "_record": record,
    }
    out = redact_event(None, "info", event)
    assert "abc123" not in out["event"]
    assert out["token"] == REDACTED
    assert out["nested"]["client_secret"] == REDACTED
    assert "a@b.co" not in out["nested"]["note"]
    assert FAKE_GROQ not in out["items"][0]
    assert out["items"][1] == 5
    assert out["count"] == 5
    assert out["_record"] is record
