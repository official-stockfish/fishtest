"""FastAPI ASGI application factory and runtime wiring.

This module provides the production entrypoint ``uvicorn fishtest.app:app`` and
owns application-level orchestration:

- lifespan startup/shutdown around ``RunDb``,
- primary-instance safety checks,
- middleware and error-handler installation,
- static mount and router registration.

The HTTP behavior itself lives in ``fishtest.http`` (API/UI routers, middleware,
session handling, and error shaping).
"""

from __future__ import annotations

import asyncio
import faulthandler
import logging
import os
import signal
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Protocol, cast

from anyio.to_thread import current_default_thread_limiter
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from starlette.staticfiles import StaticFiles

import fishtest.github_api as gh
from fishtest import schemas
from fishtest.api import router as api_router
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
    RejectNonPrimaryWorkerApiMiddleware,
    ShutdownGuardMiddleware,
)
from fishtest.http.session_middleware import FishtestSessionMiddleware
from fishtest.http.settings import (
    THREADPOOL_TOKENS,
    AppSettings,
    default_static_dir,
)
from fishtest.rundb import RunDb
from fishtest.views import router as views_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.types import ASGIApp


logger = logging.getLogger(__name__)


class MiddlewareFactory(Protocol):
    def __call__(self, app: ASGIApp, /, *args: object, **kwargs: object) -> ASGIApp: ...


def _install_sigusr1_thread_dump_handler() -> None:
    if not hasattr(signal, "SIGUSR1"):
        return

    try:
        faulthandler.register(signal.SIGUSR1, all_threads=True)
    except RuntimeError:
        logger.debug("SIGUSR1 thread-dump handler not installed")
    except ValueError:
        logger.debug("SIGUSR1 thread-dump handler already installed")


async def _shutdown_rundb(rundb: RunDb) -> None:
    rundb._shutdown = True  # noqa: SLF001
    await asyncio.sleep(0.5)

    try:
        if rundb.scheduler is not None:
            await run_in_threadpool(rundb.scheduler.stop)
    except Exception:
        logger.exception("Shutdown: error stopping scheduler")

    try:
        if rundb.is_primary_instance():
            await run_in_threadpool(rundb.run_cache.flush_all)
            await run_in_threadpool(rundb.save_persistent_data)
    except Exception:
        logger.exception("Shutdown: error flushing/saving")

    try:
        if rundb.port >= 0:
            await run_in_threadpool(
                rundb.actiondb.system_event,
                message=f"stop fishtest@{rundb.port}",
            )
    except Exception:
        logger.exception("Shutdown: error writing system_event")

    try:
        await run_in_threadpool(rundb.conn.close)
    except Exception:
        logger.exception("Shutdown: error closing MongoDB connection")


def _require_single_worker_on_primary(settings: AppSettings) -> None:
    if not settings.is_primary_instance:
        return

    workers_raw = (
        os.environ.get("UVICORN_WORKERS", "").strip()
        or os.environ.get("WEB_CONCURRENCY", "").strip()
    )
    if not workers_raw:
        return

    try:
        workers = int(workers_raw)
    except ValueError:
        return

    if workers != 1:
        message = (
            "Primary instance must run with a single Uvicorn worker "
            "(to avoid duplicated scheduler/GitHub side effects)."
        )
        raise RuntimeError(message)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    bootstrap_settings = AppSettings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = AppSettings.from_env()
        app.state.settings = settings

        limiter = current_default_thread_limiter()
        limiter.total_tokens = THREADPOOL_TOKENS

        _require_single_worker_on_primary(settings)

        rundb = await run_in_threadpool(
            RunDb,
            port=settings.port,
            is_primary_instance=settings.is_primary_instance,
        )

        app.state.rundb = rundb
        app.state.userdb = rundb.userdb
        app.state.actiondb = rundb.actiondb
        app.state.workerdb = rundb.workerdb

        _install_sigusr1_thread_dump_handler()

        # All instances should use the same user schema.
        schemas.legacy_usernames = set(rundb.kvstore.get("legacy_usernames", []))

        if settings.is_primary_instance:
            await run_in_threadpool(gh.init, rundb.kvstore, rundb.actiondb)
            await run_in_threadpool(rundb.update_aggregated_data)
            await run_in_threadpool(rundb.schedule_tasks)

        try:
            yield
        finally:
            await _shutdown_rundb(rundb)

    # OpenAPI docs are disabled in production (openapi_url defaults to None).
    # To enable /docs and /redoc during development, start with:
    #   OPENAPI_URL=/openapi.json uvicorn fishtest.app:app --reload
    openapi_url = bootstrap_settings.openapi_url

    app = FastAPI(
        lifespan=lifespan,
        openapi_url=openapi_url,
    )

    install_error_handlers(app)

    app.add_middleware(cast("MiddlewareFactory", HeadMethodMiddleware))
    app.add_middleware(cast("MiddlewareFactory", ShutdownGuardMiddleware))
    app.add_middleware(cast("MiddlewareFactory", AttachRequestStateMiddleware))
    app.add_middleware(
        cast("MiddlewareFactory", RejectNonPrimaryWorkerApiMiddleware),
    )
    app.add_middleware(cast("MiddlewareFactory", RedirectBlockedUiUsersMiddleware))
    app.add_middleware(
        cast("MiddlewareFactory", FishtestSessionMiddleware),
        secret_key=session_secret_key,
        session_cookie=SESSION_COOKIE_NAME,
        max_age=None,
        same_site=DEFAULT_SAMESITE,
        https_only=False,
    )

    static_dir = default_static_dir()

    app.mount(
        "/static",
        StaticFiles(directory=str(static_dir)),
        name="static",
    )

    app.include_router(views_router)
    app.include_router(api_router)

    return app


app = create_app()


__all__ = [
    "app",
    "create_app",
]
