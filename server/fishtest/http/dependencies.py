"""FastAPI dependency helpers.

This module provides a typed way to access DB handles attached to the app.
During migration we keep storing them on `app.state`, but prefer `request.state`
when available (set by middleware).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from starlette.requests import Request

from fishtest.actiondb import ActionDb
from fishtest.http.cookie_session import CookieSession, authenticated_user, load_session
from fishtest.rundb import RunDb
from fishtest.userdb import UserDb
from fishtest.workerdb import WorkerDb


class RequestContext(TypedDict):
    """Plain-data request context for HTTP handlers."""

    session: CookieSession
    user: str | None
    rundb: RunDb
    userdb: UserDb
    actiondb: ActionDb
    workerdb: WorkerDb


class DependencyNotInitializedError(RuntimeError):
    """Raised when an app dependency is missing from request/app state."""

    def __init__(self, dependency: str) -> None:
        """Create a DependencyNotInitializedError for the given dependency name."""
        message = f"{dependency} not initialized"
        super().__init__(message)


def _state_attr(request: Request, name: str) -> object | None:
    value = getattr(request.state, name, None)
    if value is not None:
        return value
    return getattr(request.app.state, name, None)


def _require_dependency[TDependency](
    request: Request,
    name: str,
    kind: type[TDependency],
) -> TDependency:
    value = _state_attr(request, name)
    if value is None:
        raise DependencyNotInitializedError(kind.__name__)
    if not isinstance(value, kind):
        raise DependencyNotInitializedError(kind.__name__)
    return value


def get_rundb(request: Request) -> RunDb:
    """Return the request-scoped RunDb handle."""
    return _require_dependency(request, "rundb", RunDb)


def get_userdb(request: Request) -> UserDb:
    """Return the request-scoped UserDb handle."""
    return _require_dependency(request, "userdb", UserDb)


def get_actiondb(request: Request) -> ActionDb:
    """Return the request-scoped ActionDb handle."""
    return _require_dependency(request, "actiondb", ActionDb)


def get_workerdb(request: Request) -> WorkerDb:
    """Return the request-scoped WorkerDb handle."""
    return _require_dependency(request, "workerdb", WorkerDb)


def get_request_context(request: Request) -> RequestContext:
    """Return a plain-data context for HTTP handlers (no control flow)."""
    session = load_session(request)
    return {
        "session": session,
        "user": authenticated_user(session),
        "rundb": get_rundb(request),
        "userdb": get_userdb(request),
        "actiondb": get_actiondb(request),
        "workerdb": get_workerdb(request),
    }
