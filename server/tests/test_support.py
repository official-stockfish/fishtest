import atexit
import os
import re
import unittest
from typing import Any

from fishtest.rundb import RunDb


def get_rundb():
    rundb = RunDb(db_name="fishtest_tests")
    atexit.register(rundb.conn.close)
    return rundb


def find_run(arg="username", value="travis"):
    rundb = RunDb(db_name="fishtest_tests")
    atexit.register(rundb.conn.close)
    for run in rundb.get_unfinished_runs():
        if run["args"][arg] == value:
            return run
    return None


def cleanup_test_rundb(
    rundb: Any,
    *,
    clear_usernames: list[str] | None = None,
    clear_users_regex: str | None = None,
    clear_user_cache: bool = True,
    clear_pgndb: bool = False,
    clear_runs: bool = False,
    drop_runs: bool = False,
    close_conn: bool = True,
) -> None:
    userdb = getattr(rundb, "userdb", None)
    if userdb is not None:
        if clear_usernames:
            userdb.users.delete_many({"username": {"$in": clear_usernames}})
            userdb.user_cache.delete_many({"username": {"$in": clear_usernames}})
        if clear_users_regex:
            userdb.users.delete_many({"username": {"$regex": clear_users_regex}})
            userdb.user_cache.delete_many({"username": {"$regex": clear_users_regex}})
        if clear_user_cache:
            userdb.clear_cache()

    if clear_pgndb and hasattr(rundb, "pgndb"):
        rundb.pgndb.delete_many({})

    if clear_runs and hasattr(rundb, "runs"):
        rundb.runs.delete_many({})

    if drop_runs and hasattr(rundb, "runs"):
        rundb.runs.drop()

    if close_conn and hasattr(rundb, "conn"):
        rundb.conn.close()


def require_fastapi() -> tuple[Any, Any]:
    """Return (FastAPI, TestClient) or skip the test module."""
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        return FastAPI, TestClient
    except (ModuleNotFoundError, RuntimeError) as exc:  # pragma: no cover
        name = getattr(exc, "name", None)
        raise unittest.SkipTest(
            f"FastAPI test dependencies missing ({name or exc}); skipping FastAPI HTTP tests",
        )


def build_test_app(*, rundb: Any, include_api: bool, include_views: bool):
    """Create a minimal FastAPI app wired like production (minus lifespan)."""
    os.environ.setdefault("FISHTEST_AUTHENTICATION_SECRET", "test-secret")

    FastAPI, _TestClient = require_fastapi()

    try:
        from fishtest.http.cookie_session import (
            DEFAULT_SAMESITE,
            SESSION_COOKIE_NAME,
            session_secret_key,
        )
        from fishtest.http.errors import install_error_handlers
        from fishtest.http.middleware import (
            AttachRequestStateMiddleware,
            HeadMethodMiddleware,
            RedirectBlockedUiUsersMiddleware,
            ShutdownGuardMiddleware,
        )
        from fishtest.http.session_middleware import FishtestSessionMiddleware
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise unittest.SkipTest(
            f"Server dependencies missing ({exc.name}); skipping FastAPI HTTP tests",
        )

    app = FastAPI()

    app.state.rundb = rundb
    app.state.userdb = getattr(rundb, "userdb", None)
    app.state.actiondb = getattr(rundb, "actiondb", None)
    app.state.workerdb = getattr(rundb, "workerdb", None)

    install_error_handlers(app)

    app.add_middleware(HeadMethodMiddleware)
    app.add_middleware(ShutdownGuardMiddleware)
    app.add_middleware(AttachRequestStateMiddleware)
    app.add_middleware(RedirectBlockedUiUsersMiddleware)
    app.add_middleware(
        FishtestSessionMiddleware,
        secret_key=session_secret_key,
        session_cookie=SESSION_COOKIE_NAME,
        max_age=None,
        same_site=DEFAULT_SAMESITE,
        https_only=False,
    )

    if include_api:
        try:
            from fishtest.api import router as api_router
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise unittest.SkipTest(
                f"Server dependencies missing ({exc.name}); skipping FastAPI HTTP tests",
            )
        app.include_router(api_router)

    if include_views:
        try:
            from fishtest.views import router as views_router
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise unittest.SkipTest(
                f"Server dependencies missing ({exc.name}); skipping FastAPI HTTP tests",
            )
        app.include_router(views_router)

    return app


def make_test_client(*, rundb: Any, include_api: bool, include_views: bool):
    """Create a starlette TestClient for the HTTP routers."""
    _FastAPI, TestClient = require_fastapi()
    app = build_test_app(
        rundb=rundb,
        include_api=include_api,
        include_views=include_views,
    )
    return TestClient(app)


_CSRF_META_RE = re.compile(
    r"<meta\s+name=\"csrf-token\"\s+content=\"([^\"]+)\"",
    re.IGNORECASE,
)


def extract_csrf_token(html: str) -> str:
    match = _CSRF_META_RE.search(html)
    if not match:
        raise AssertionError("Could not find csrf-token meta tag")
    return match.group(1)
