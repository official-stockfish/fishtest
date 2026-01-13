"""Session middleware with per-request overrides.

This is a small wrapper around Starlette's session middleware behavior:
- Uses `itsdangerous.TimestampSigner` for signing.
- Persists a JSON-encoded session dict.
- Allows per-request `max_age` and secure flags via scope keys.
"""

from __future__ import annotations

import json
from base64 import b64decode, b64encode
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import TYPE_CHECKING, Literal, cast

import itsdangerous
from itsdangerous.exc import BadSignature
from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection

from fishtest.http.cookie_session import (
    DEFAULT_SAMESITE,
    MAX_COOKIE_BYTES,
    SESSION_COOKIE_NAME,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.types import ASGIApp, Message, Receive, Scope, Send


class FishtestSessionMiddleware:
    """Session middleware with per-request max-age and secure overrides."""

    def __init__(  # noqa: PLR0913
        self,
        app: ASGIApp,
        *,
        secret_key: str | Callable[[], str],
        session_cookie: str = SESSION_COOKIE_NAME,
        max_age: int | None = None,
        path: str = "/",
        same_site: Literal["lax", "strict", "none"] = DEFAULT_SAMESITE,
        https_only: bool = False,
        domain: str | None = None,
    ) -> None:
        """Initialize the session middleware wrapper."""
        self.app = app
        self._secret_key = secret_key
        self._signer: itsdangerous.TimestampSigner | None = None
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.path = path
        self.same_site = same_site
        self.https_only = https_only
        self.domain = domain

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Load and persist session data for HTTP/WebSocket scopes."""
        if scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        initial_session_was_empty = True

        session: dict[str, object] = {}
        signer = self._get_signer()
        if self.session_cookie in connection.cookies:
            raw = connection.cookies[self.session_cookie].encode("utf-8")
            try:
                if self.max_age is None:
                    unsigned = signer.unsign(raw)
                else:
                    unsigned = signer.unsign(raw, max_age=self.max_age)
                session = json.loads(b64decode(unsigned))
                initial_session_was_empty = False
            except BadSignature, ValueError, TypeError, json.JSONDecodeError:
                session = {}

        if not isinstance(session, dict):
            session = {}

        scope["session"] = session

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                session_data = scope.get("session") or {}
                headers = MutableHeaders(scope=message)
                max_age = _max_age_from_scope(scope, self.max_age)
                secure = _secure_from_scope(scope, https_only=self.https_only)
                force_clear = bool(scope.get("session_force_clear", False))

                if session_data:
                    session_data = _enforce_size_limit(session_data, signer)
                    scope["session"] = session_data
                    data = b64encode(json.dumps(session_data).encode("utf-8"))
                    signed = signer.sign(data)
                    headers.append(
                        "Set-Cookie",
                        _build_cookie_header(
                            name=self.session_cookie,
                            value=signed.decode("utf-8"),
                            max_age=max_age,
                            path=self.path,
                            secure=secure,
                            same_site=self.same_site,
                            domain=self.domain,
                        ),
                    )
                elif force_clear or not initial_session_was_empty:
                    headers.append(
                        "Set-Cookie",
                        _delete_cookie_header(
                            name=self.session_cookie,
                            path=self.path,
                            secure=secure,
                            same_site=self.same_site,
                            domain=self.domain,
                        ),
                    )

            await send(message)

        await self.app(scope, receive, send_wrapper)

    def _get_signer(self) -> itsdangerous.TimestampSigner:
        if self._signer is None:
            key = self._secret_key() if callable(self._secret_key) else self._secret_key
            self._signer = itsdangerous.TimestampSigner(str(key))
        return self._signer


def _max_age_from_scope(scope: Scope, fallback: int | None) -> int | None:
    value = scope.get("session_max_age", fallback)
    if value is None:
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return fallback


def _secure_from_scope(scope: Scope, *, https_only: bool) -> bool:
    override = scope.get("session_secure")
    if isinstance(override, bool):
        return override
    return https_only or _is_https_scope(scope)


def _is_https_scope(scope: Scope) -> bool:
    headers = dict(scope.get("headers") or [])
    forwarded = headers.get(b"x-forwarded-proto", b"").split(b",", 1)[0].strip()
    if forwarded:
        return forwarded == b"https"
    return scope.get("scheme") == "https"


def _build_cookie_header(  # noqa: PLR0913
    *,
    name: str,
    value: str,
    max_age: int | None,
    path: str,
    secure: bool,
    same_site: str,
    domain: str | None,
) -> str:
    flags = ["httponly", f"samesite={same_site}"]
    if secure:
        flags.append("secure")
    if domain:
        flags.append(f"domain={domain}")
    age_parts: list[str] = []
    if max_age is not None:
        expires_at = datetime.now(UTC) + timedelta(seconds=max_age)
        expires = format_datetime(expires_at, usegmt=True)
        age_parts.append(f"Max-Age={max_age}")
        age_parts.append(f"Expires={expires}")
    attrs = [f"{name}={value}", f"path={path}", *age_parts, *flags]
    return "; ".join(attrs)


def _delete_cookie_header(
    *,
    name: str,
    path: str,
    secure: bool,
    same_site: str,
    domain: str | None,
) -> str:
    flags = ["httponly", f"samesite={same_site}"]
    if secure:
        flags.append("secure")
    if domain:
        flags.append(f"domain={domain}")
    attrs = [
        f"{name}=null",
        f"path={path}",
        "Max-Age=0",
        "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
        *flags,
    ]
    return "; ".join(attrs)


def _cookie_size_ok(value: str) -> bool:
    return len(value.encode("utf-8")) <= MAX_COOKIE_BYTES


def _encode_cookie_value(
    payload: dict[str, object],
    signer: itsdangerous.TimestampSigner,
) -> str:
    data = b64encode(json.dumps(payload).encode("utf-8"))
    signed = signer.sign(data)
    return signed.decode("utf-8")


def _shrink_flashes(payload: dict[str, object]) -> None:
    flashes = payload.get("flashes")
    if not isinstance(flashes, dict):
        return

    typed_flashes = cast("dict[str, object]", flashes)
    queues: list[tuple[str, list[object]]] = []
    for key, bucket in typed_flashes.items():
        if isinstance(bucket, list) and bucket:
            queues.append((str(key), cast("list[object]", bucket)))

    while queues:
        key, bucket = queues.pop(0)
        if bucket:
            bucket.pop(0)
        if bucket:
            queues.append((key, bucket))
        else:
            typed_flashes.pop(key, None)
        if not typed_flashes:
            payload.pop("flashes", None)
            break


def _enforce_size_limit(
    payload: dict[str, object],
    signer: itsdangerous.TimestampSigner,
) -> dict[str, object]:
    candidate = dict(payload)
    value = _encode_cookie_value(candidate, signer)
    if _cookie_size_ok(value):
        return candidate

    _shrink_flashes(candidate)
    value = _encode_cookie_value(candidate, signer)
    if _cookie_size_ok(value):
        return candidate

    candidate.pop("flashes", None)
    value = _encode_cookie_value(candidate, signer)
    if _cookie_size_ok(value):
        return candidate

    minimal: dict[str, object] = {}
    for key in ("user", "csrf_token", "created_at", "updated_at"):
        if key in candidate:
            minimal[key] = candidate[key]
    return minimal
