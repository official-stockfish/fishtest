"""FastAPI/Starlette error handlers.

Ownership: API/UI error shaping; UI HTML rendering delegated to ui_errors.

These handlers preserve legacy fishtest behavior:
- JSON 404s for `/api/...`
- HTML 404 page for UI routes rendered via Jinja2
- Cookie-session commit for UI 404 rendering
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final

from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from fishtest.api import WORKER_API_PATHS
from fishtest.api import router as api_router
from fishtest.http.ui_errors import render_forbidden_response, render_notfound_response

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.requests import Request
    from starlette.responses import Response

STATUS_NOT_FOUND: Final[int] = 404
STATUS_UNAUTHORIZED: Final[int] = 401
STATUS_FORBIDDEN: Final[int] = 403


def _derive_worker_api_paths() -> set[str]:
    router_paths = {
        route.path for route in api_router.routes if isinstance(route, Route)
    }
    return {path for path in WORKER_API_PATHS if path in router_paths}


_WORKER_API_PATHS: Final[set[str]] = _derive_worker_api_paths()


def _duration_from_request(request: Request) -> float:
    started_at = getattr(request.state, "request_started_at", None)
    if isinstance(started_at, (int, float)):
        return max(0.0, time.monotonic() - float(started_at))
    return 0.0


async def _http_exception_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)

    # Preserve legacy behavior: when an endpoint raises an HTTP exception with a
    # dict payload, return that dict as the response body.
    if isinstance(getattr(exc, "detail", None), dict):
        return JSONResponse(exc.detail, status_code=exc.status_code)

    # UI auth failures should not return JSON.
    if exc.status_code in {STATUS_UNAUTHORIZED, STATUS_FORBIDDEN}:
        if request.url.path.startswith("/api"):
            response = await http_exception_handler(request, exc)
        else:
            try:
                response = await render_forbidden_response(request)
            except Exception:  # noqa: BLE001
                response = PlainTextResponse("Forbidden", status_code=exc.status_code)
        return response

    if exc.status_code != STATUS_NOT_FOUND:
        return await http_exception_handler(request, exc)

    # Preserve JSON behavior for API endpoints.
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": "Not Found"}, status_code=STATUS_NOT_FOUND)

    try:
        response = await render_notfound_response(request)
    except Exception:  # noqa: BLE001
        response = PlainTextResponse("Not Found", status_code=STATUS_NOT_FOUND)
    return response


async def _request_validation_handler(
    request: Request,
    exc: Exception,
) -> Response:
    if not isinstance(exc, RequestValidationError):
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)

    # Keep worker protocol stable (always dict + duration).
    if request.url.path in _WORKER_API_PATHS:
        return JSONResponse(
            {
                "error": f"{request.url.path}: invalid request",
                "duration": _duration_from_request(request),
            },
            status_code=400,
        )

    # Preserve API semantics (JSON) while keeping UI routes out of it.
    if request.url.path.startswith("/api"):
        return JSONResponse(
            {
                "detail": "Invalid request",
                "errors": exc.errors(),
            },
            status_code=400,
        )

    return await request_validation_exception_handler(request, exc)


async def _unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> Response:
    _ = exc
    # Worker protocol must return a JSON dict with duration.
    if request.url.path in _WORKER_API_PATHS:
        return JSONResponse(
            {
                "error": f"{request.url.path}: Internal Server Error",
                "duration": _duration_from_request(request),
            },
            status_code=500,
        )

    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)

    # For UI routes, avoid returning JSON by default.
    return PlainTextResponse("Internal Server Error", status_code=500)


def install_error_handlers(app: FastAPI) -> None:
    """Register exception handlers to preserve legacy API/UI error behavior."""
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _request_validation_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
