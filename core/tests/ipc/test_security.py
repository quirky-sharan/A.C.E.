"""IPC security helpers: tokens, Origin rules, rate limiter, private file permissions."""

import sys
from pathlib import Path

import pytest

from ace_core.ipc.security import (
    TokenBucket,
    new_token,
    origin_allowed,
    restrict_to_current_user,
    tokens_match,
)


def test_new_tokens_are_long_and_unique() -> None:
    tokens = {new_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(token) >= 43 for token in tokens)


def test_tokens_match_only_exactly() -> None:
    token = new_token()
    assert tokens_match(token, token)
    assert not tokens_match(token, token[:-1])
    assert not tokens_match(token, "")


@pytest.mark.parametrize(
    ("origin", "dev", "allowed"),
    [
        (None, False, True),  # local non-browser client: still needs the token
        ("http://tauri.localhost", False, True),
        ("https://tauri.localhost", False, True),
        ("http://localhost:1420", False, False),
        ("http://localhost:1420", True, True),
        ("https://evil.example", True, False),
        ("null", True, False),
        ("", False, False),
    ],
)
def test_origin_rules(origin: str | None, dev: bool, allowed: bool) -> None:
    assert origin_allowed(origin, dev=dev) is allowed


def test_token_bucket_allows_a_burst_then_refills() -> None:
    now = [0.0]
    bucket = TokenBucket(2.0, 3, clock=lambda: now[0])
    assert [bucket.allow() for _ in range(4)] == [True, True, True, False]
    now[0] = 0.5  # one token refilled at 2 per second
    assert bucket.allow() is True
    assert bucket.allow() is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACLs")
def test_private_file_is_readable_by_the_current_user_only(tmp_path: Path) -> None:
    import ntsecuritycon
    import win32api
    import win32security

    path = tmp_path / "secret.json"
    path.write_text("{}", encoding="utf-8")
    restrict_to_current_user(path)

    descriptor = win32security.GetFileSecurity(str(path), win32security.DACL_SECURITY_INFORMATION)
    dacl = descriptor.GetSecurityDescriptorDacl()
    assert dacl is not None
    assert dacl.GetAceCount() == 1
    _, mask, sid = dacl.GetAce(0)
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)
    try:
        me = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        win32api.CloseHandle(token)
    assert sid == me
    assert mask == ntsecuritycon.FILE_ALL_ACCESS
    control, _ = descriptor.GetSecurityDescriptorControl()
    assert control & win32security.SE_DACL_PROTECTED
    assert path.read_text(encoding="utf-8") == "{}"  # still readable by us
