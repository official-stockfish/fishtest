"""UI error rendering helpers for FastAPI.

Ownership: render legacy UI error templates and commit session cookies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.concurrency import run_in_threadpool

from fishtest.http.boundary import (
    SessionCommitFlags,
    build_template_context,
    commit_session_flags,
)
from fishtest.http.cookie_session import load_session
from fishtest.http.template_renderer import render_template_to_response

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response


async def render_notfound_response(request: Request) -> Response:
    """Render the legacy UI 404 page and commit the cookie session."""
    session = load_session(request)

    context = build_template_context(request, session)

    # Template rendering is sync and can be CPU heavy; keep it off the event loop.
    response = await run_in_threadpool(
        render_template_to_response,
        request=request,
        template_name="notfound.html.j2",
        context=context,
        status_code=404,
    )
    commit_session_flags(
        request,
        session,
        response,
        flags=SessionCommitFlags(remember=False, forget=False),
    )
    return response


async def render_forbidden_response(request: Request) -> Response:
    """Render the legacy UI 403 page (login) and commit the cookie session."""
    session = load_session(request)
    session.flash("Please login")

    context = build_template_context(request, session)

    response = await run_in_threadpool(
        render_template_to_response,
        request=request,
        template_name="login.html.j2",
        context=context,
        status_code=403,
    )
    commit_session_flags(
        request,
        session,
        response,
        flags=SessionCommitFlags(remember=False, forget=False),
    )
    return response
