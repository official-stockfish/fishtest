"""Session helpers for the FastAPI UI.

This keeps the legacy `CookieSession` surface while delegating persistence to
Starlette's session middleware. The session data lives in `request.scope["session"]`.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.requests import Request

SESSION_COOKIE_NAME: Final[str] = "fishtest_session"
DEFAULT_SAMESITE: Final[Literal["lax", "strict", "none"]] = "lax"
REMEMBER_MAX_AGE_SECONDS: Final[int] = 60 * 60 * 24 * 365
MAX_COOKIE_BYTES: Final[int] = 3800
INSECURE_DEV_ENV: Final[str] = "FISHTEST_INSECURE_DEV"


class MissingAuthenticationSecretError(RuntimeError):
    """Raised when the authentication secret is missing and insecure mode is off."""

    def __init__(self, env_name: str) -> None:
        """Create a MissingAuthenticationSecretError for the given env var name."""
        message = (
            "Missing FISHTEST_AUTHENTICATION_SECRET "
            f"(set {env_name}=1 to allow insecure dev fallback)."
        )
        super().__init__(message)


def _secret_key() -> str:
    """Return the application secret used for cookie signing."""
    value = os.environ.get("FISHTEST_AUTHENTICATION_SECRET", "").strip()
    if not value:
        insecure = os.environ.get(INSECURE_DEV_ENV, "").strip().lower()
        if insecure in {"1", "true", "yes", "on"}:
            value = "insecure-dev-secret"
        else:
            env_name = INSECURE_DEV_ENV
            raise MissingAuthenticationSecretError(env_name)
    return value


def session_secret_key() -> str:
    """Expose the session signing key for middleware configuration."""
    return _secret_key()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class CookieSession:
    """Dict-backed session with CSRF + flash helpers."""

    data: dict[str, Any]

    def get_csrf_token(self) -> str:
        """Return the CSRF token, generating one if needed."""
        token = self.data.get("csrf_token")
        if isinstance(token, str) and token:
            return token
        token = secrets.token_hex(32)
        self.data["csrf_token"] = token
        return token

    def new_csrf_token(self) -> str:
        """Rotate the CSRF token."""
        token = secrets.token_hex(32)
        self.data["csrf_token"] = token
        return token

    def flash(self, message: str, queue: str | None = None) -> None:
        """Add a flash message to the given queue."""
        key = queue or ""
        flashes = self.data.setdefault("flashes", {})
        if not isinstance(flashes, dict):
            flashes = {}
            self.data["flashes"] = flashes
        bucket = flashes.setdefault(key, [])
        if not isinstance(bucket, list):
            bucket = []
            flashes[key] = bucket
        bucket.append(str(message))

    def peek_flash(self, queue: str | None = None) -> bool:
        """Return whether there are queued flashes (without consuming them)."""
        key = queue or ""
        flashes = self.data.get("flashes")
        if not isinstance(flashes, dict):
            return False
        bucket = flashes.get(key)
        return isinstance(bucket, list) and len(bucket) > 0

    def pop_flash(self, queue: str | None = None) -> list[str]:
        """Consume and return flash messages for the given queue."""
        key = queue or ""
        flashes = self.data.get("flashes")
        if not isinstance(flashes, dict):
            return []
        bucket = flashes.pop(key, [])
        if not isinstance(bucket, list):
            bucket = []
        if not flashes:
            self.data.pop("flashes", None)
        return [str(x) for x in bucket]

    def invalidate(self) -> None:
        """Clear all session data."""
        self.data.clear()


def load_session(request: Request) -> CookieSession:
    """Return a `CookieSession` backed by `request.scope["session"]`."""
    scope = request.scope
    session = scope.get("session")
    if not isinstance(session, dict):
        session = {}
        scope["session"] = session
    session.setdefault("created_at", _utc_now_iso())
    return CookieSession(data=session)


def authenticated_user(session: CookieSession) -> str | None:
    """Return the logged-in username from the session, if present."""
    value = session.data.get("user")
    return value if isinstance(value, str) and value else None


def authenticated_user_from_data(session_data: Mapping[str, object]) -> str | None:
    """Return the logged-in username from raw session data, if present."""
    value = session_data.get("user")
    return value if isinstance(value, str) and value else None


def mark_session_max_age(request: Request, max_age: int | None) -> None:
    """Override the cookie max-age for the current request."""
    if max_age is None:
        return
    request.scope["session_max_age"] = max_age


def mark_session_force_clear(request: Request) -> None:
    """Force the response to emit an expired session cookie."""
    request.scope["session_force_clear"] = True


def is_https(request: Request) -> bool:
    """Return whether the original request was HTTPS (proxy-aware)."""
    forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded == "https"
    return request.url.scheme == "https"


__all__ = [
    "DEFAULT_SAMESITE",
    "INSECURE_DEV_ENV",
    "MAX_COOKIE_BYTES",
    "REMEMBER_MAX_AGE_SECONDS",
    "SESSION_COOKIE_NAME",
    "CookieSession",
    "MissingAuthenticationSecretError",
    "authenticated_user",
    "authenticated_user_from_data",
    "is_https",
    "load_session",
    "mark_session_force_clear",
    "mark_session_max_age",
    "session_secret_key",
]
