"""IPC security helpers (§15.1): token, Origin allowlist, rate limit, private files."""

from __future__ import annotations

import hmac
import secrets
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

TOKEN_BYTES: Final = 32  # 256-bit per-run token
MIN_TOKEN_LENGTH: Final = 32

# Tauri 2 serves the app from http://tauri.localhost on Windows (https:// with useHttpsScheme).
TAURI_ORIGINS: Final = frozenset({"http://tauri.localhost", "https://tauri.localhost"})
# The Vite dev server the Tauri webview loads in development (apps/desktop/vite.config.ts).
DEV_ORIGINS: Final = frozenset({"http://localhost:1420"})


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def tokens_match(expected: str, provided: str) -> bool:
    """Constant-time comparison."""
    return hmac.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))


def origin_allowed(origin: str | None, *, dev: bool) -> bool:
    """Browsers always send Origin: only ACE's own webview may connect. No Origin = a local
    non-browser client (ace-cli, native host), which still has to present the token."""
    if origin is None:
        return True
    allowed = TAURI_ORIGINS | DEV_ORIGINS if dev else TAURI_ORIGINS
    return origin in allowed


class TokenBucket:
    """Simple rate limiter: ``burst`` messages at once, refilled at ``rate_per_s``."""

    def __init__(
        self, rate_per_s: float, burst: int, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._rate = rate_per_s
        self._capacity = float(burst)
        self._tokens = float(burst)
        self._clock = clock
        self._last = clock()

    def allow(self) -> bool:
        now = self._clock()
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


def restrict_to_current_user(path: Path) -> None:
    """Replace the file's permissions with "current user: full control" only (no inheritance)."""
    if sys.platform != "win32":  # pragma: no cover - ACE targets Windows
        path.chmod(0o600)
        return
    import ntsecuritycon
    import win32api
    import win32security

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)
    try:
        user_sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        win32api.CloseHandle(token)
    dacl = win32security.ACL()
    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, user_sid)
    win32security.SetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None,
        None,
        dacl,
        None,
    )
