"""Shared HTTP boundary (FastAPI UI/API).

Ownership: request shims, session commit helpers, and template context wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from json import JSONDecodeError
from types import SimpleNamespace
from typing import TYPE_CHECKING, Protocol, cast

from starlette.requests import Request

from fishtest.http.cookie_session import (
    REMEMBER_MAX_AGE_SECONDS,
    CookieSession,
    authenticated_user,
    is_https,
    mark_session_force_clear,
    mark_session_max_age,
)
from fishtest.http.csrf import csrf_or_403
from fishtest.http.dependencies import (
    DependencyNotInitializedError,
    get_actiondb,
    get_rundb,
    get_userdb,
)
from fishtest.http.jinja import static_url

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.responses import Response


class _SessionFlags(Protocol):
    remember: bool
    forget: bool
    remember_max_age: int | None


class _SessionUser(_SessionFlags, Protocol):
    raw_request: Request | None
    session: CookieSession | dict[str, object]


@dataclass(frozen=True, slots=True)
class SessionCommitFlags:
    """Container for session persistence flags."""

    remember: bool
    forget: bool
    remember_max_age: int | None = None


class ApiRequestShim:
    """Minimal request shim to keep the API port mechanical."""

    def __init__(
        self,
        request: Request,
        *,
        json_body: object | None = None,
        json_error: bool = False,
        matchdict: dict[str, str] | None = None,
    ) -> None:
        """Initialize the request shim with parsed request metadata."""
        self._request = request
        self._json_body = json_body
        self._json_error = json_error
        self.matchdict = matchdict or {}
        self.params = request.query_params
        self.headers = request.headers
        self.cookies = request.cookies
        self.url = request.url
        self.scheme = request.url.scheme
        self.host = request.headers.get("host") or request.url.netloc
        self.host_url = str(request.base_url).rstrip("/")
        self.remote_addr = request.client.host if request.client else None
        self.response = SimpleNamespace(headers={})

        try:
            self.rundb = get_rundb(request)
        except DependencyNotInitializedError:
            self.rundb = None
        try:
            self.userdb = get_userdb(request)
        except DependencyNotInitializedError:
            self.userdb = None
        try:
            self.actiondb = get_actiondb(request)
        except DependencyNotInitializedError:
            self.actiondb = None

    @property
    def json_body(self) -> object | None:
        """Return the parsed JSON body, raising if the request was invalid."""
        if self._json_error:
            message = "request is not json encoded"
            raise ValueError(message)
        return self._json_body


@dataclass(frozen=True)
class JsonBodyResult:
    """Result of JSON parsing with error flag."""

    body: object | None
    error: bool


async def get_json_body(request: Request) -> JsonBodyResult:
    """Parse JSON body, preserving legacy error behavior."""
    try:
        body = await request.json()
    except JSONDecodeError, TypeError, ValueError:
        return JsonBodyResult(body=None, error=True)
    return JsonBodyResult(body=body, error=False)


async def get_request_shim(
    request: Request,
    matchdict: dict[str, str] | None = None,
) -> ApiRequestShim:
    """Dependency that builds the API request shim."""
    json_body = await get_json_body(request)
    return ApiRequestShim(
        request,
        json_body=json_body.body,
        json_error=json_body.error,
        matchdict=matchdict,
    )


def commit_session_flags(
    request: Request,
    session: CookieSession,
    response: Response,
    *,
    flags: SessionCommitFlags,
) -> Response:
    """Apply session persistence flags for the middleware."""
    if flags.forget:
        session.invalidate()
        mark_session_force_clear(request)
        return response

    if flags.remember:
        max_age = (
            flags.remember_max_age
            if flags.remember_max_age is not None
            else REMEMBER_MAX_AGE_SECONDS
        )
        mark_session_max_age(request, max_age)
        request.scope["session_secure"] = is_https(request)
    return response


def commit_session_response(
    request: Request,
    session: CookieSession,
    shim: _SessionFlags,
    response: Response,
) -> Response:
    """Commit or clear the session cookie based on shim flags."""
    remember_flag = getattr(shim, "remember", False)
    forget_flag = getattr(shim, "forget", False)
    remember_max_age = getattr(shim, "remember_max_age", None)
    if not remember_flag:
        remember_flag = getattr(shim, "_remember", False)
    if not forget_flag:
        forget_flag = getattr(shim, "_forget", False)
    return commit_session_flags(
        request,
        session,
        response,
        flags=SessionCommitFlags(
            remember=bool(remember_flag),
            forget=bool(forget_flag),
            remember_max_age=remember_max_age,
        ),
    )


def _resolve_session_data(session: object) -> dict[str, object] | None:
    if isinstance(session, CookieSession):
        return session.data
    if isinstance(session, dict):
        return cast("dict[str, object]", session)
    data = getattr(session, "data", None)
    if isinstance(data, dict):
        return cast("dict[str, object]", data)
    return None


def _invalidate_session(session: object) -> None:
    if isinstance(session, CookieSession):
        session.invalidate()
        return
    if isinstance(session, dict):
        session.clear()
        return
    invalidate = getattr(session, "invalidate", None)
    if callable(invalidate):
        invalidate()


def _resolve_raw_request(request: object) -> Request | None:
    if isinstance(request, Request):
        return request
    raw_request = getattr(request, "raw_request", None)
    if raw_request is None:
        raw_request = getattr(request, "_request", None)
    return raw_request


def remember(
    request: _SessionUser,
    username: str,
    max_age: int | None = None,
) -> list[tuple[str, str]]:
    """Remember a user in the session and mark the cookie for persistence."""
    session_data = _resolve_session_data(request.session)
    if session_data is not None:
        session_data["user"] = username
    request.remember = max_age is not None
    request.remember_max_age = max_age
    raw_request = _resolve_raw_request(request)
    if max_age is not None and raw_request is not None:
        mark_session_max_age(raw_request, max_age)
    return []


def forget(request: _SessionUser) -> list[tuple[str, str]]:
    """Forget the current user and mark the session to clear the cookie."""
    _invalidate_session(request.session)
    request.forget = True
    raw_request = _resolve_raw_request(request)
    if raw_request is not None:
        mark_session_force_clear(raw_request)
    return []


def build_template_context(
    request: Request,
    session: CookieSession,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the shared template context (includes `request`)."""

    def _pop_flash_list(queue: str | None = None) -> list[str]:
        return session.pop_flash(queue)

    user = authenticated_user(session)
    pending_users_count = 0
    try:
        pending_users_count = len(get_userdb(request).get_pending())
    except DependencyNotInitializedError:
        pending_users_count = 0

    base_context: dict[str, object] = {
        "csrf_token": session.get_csrf_token(),
        "current_user": {"username": user} if user else None,
        "flash": {
            "error": _pop_flash_list("error"),
            "warning": _pop_flash_list("warning"),
            "info": _pop_flash_list(),
        },
        "pending_users_count": pending_users_count,
        "static_url": static_url,
        "theme": request.cookies.get("theme", ""),
        "urls": {
            "home": "/",
            "login": "/login",
            "logout": "/logout",
            "signup": "/signup",
            "user_profile": "/user",
            "tests": "/tests",
            "tests_finished_ltc": "/tests/finished?ltc_only=1",
            "tests_finished_success": "/tests/finished?success_only=1",
            "tests_finished_yellow": "/tests/finished?yellow_only=1",
            "tests_run": "/tests/run",
            "tests_user_prefix": "/tests/user/",
            "tests_machines": "/tests/machines",
            "nn_upload": "/upload",
            "nns": "/nns",
            "contributors": "/contributors",
            "contributors_monthly": "/contributors/monthly",
            "actions": "/actions",
            "user_management": "/user_management",
            "workers_blocked": "/workers/show",
            "sprt_calc": "/sprt_calc",
            "rate_limits": "/rate_limits",
            "api_rate_limit": "/api/rate_limit",
        },
    }

    context: dict[str, object] = {
        "request": request,
        **base_context,
    }
    if extra:
        context.update(extra)
    return context


__all__ = [
    "ApiRequestShim",
    "JsonBodyResult",
    "SessionCommitFlags",
    "build_template_context",
    "commit_session_flags",
    "commit_session_response",
    "csrf_or_403",
    "forget",
    "get_json_body",
    "get_request_shim",
    "remember",
]
