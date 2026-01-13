"""CSRF helpers for UI routes.

We keep CSRF validation logic centralized so UI POST routes behave consistently
across the FastAPI migration.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from starlette.datastructures import FormData
    from starlette.requests import Request

    from fishtest.http.cookie_session import CookieSession


def csrf_token_from_form(form: FormData) -> str | None:
    """Extract a CSRF token from a form payload, if present."""
    token = form.get("csrf_token")
    return token if isinstance(token, str) else None


def csrf_is_valid(
    *,
    request: Request,
    session: CookieSession,
    form_token: str | None,
) -> bool:
    """Validate CSRF using `X-CSRF-Token` header or `csrf_token` form field."""
    header_token = request.headers.get("x-csrf-token")
    token = header_token or form_token
    if not token:
        return False
    expected = session.get_csrf_token()
    return secrets.compare_digest(token, expected)


def csrf_or_403(
    *,
    request: Request,
    session: CookieSession,
    form_token: str | None,
) -> None:
    """Raise HTTP 403 if CSRF validation fails."""
    if not csrf_is_valid(request=request, session=session, form_token=form_token):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
