"""Shared helpers for non-auth UI cookies.

These helpers keep the browser-readable cookie contract in one place while
preserving the existing raw ``Set-Cookie`` append behavior used by the UI.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableSequence
from typing import Any, Final, Protocol, cast
from urllib.parse import quote, unquote

ACTIVE_RUN_FILTERS_COOKIE_NAME: Final[str] = "active_run_filters"
ACTIVE_RUN_FILTERS_PANEL_COOKIE_NAME: Final[str] = "active_run_filters_panel"
CONTRIBUTORS_FINDME_COOKIE_NAME: Final[str] = "contributors_findme"
LIVE_ELO_MODE_COOKIE_NAME: Final[str] = "live_elo_mode"
LOGIN_REMEMBER_ME_COOKIE_NAME: Final[str] = "login_remember_me"
MACHINES_MY_WORKERS_COOKIE_NAME: Final[str] = "machines_my_workers"
MACHINES_ORDER_COOKIE_NAME: Final[str] = "machines_order"
MACHINES_PAGE_COOKIE_NAME: Final[str] = "machines_page"
MACHINES_QUERY_COOKIE_NAME: Final[str] = "machines_q"
MACHINES_SORT_COOKIE_NAME: Final[str] = "machines_sort"
MACHINES_STATE_COOKIE_NAME: Final[str] = "machines_state"
MASTER_ONLY_COOKIE_NAME: Final[str] = "master_only"
TASKS_ORDER_COOKIE_NAME: Final[str] = "tasks_order"
TASKS_QUERY_COOKIE_NAME: Final[str] = "tasks_q"
TASKS_SORT_COOKIE_NAME: Final[str] = "tasks_sort"
TASKS_STATE_COOKIE_NAME: Final[str] = "tasks_state"
TASKS_VIEW_COOKIE_NAME: Final[str] = "tasks_view"
THEME_COOKIE_NAME: Final[str] = "theme"

UI_COOKIE_PATH: Final[str] = "/"
UI_COOKIE_SAMESITE: Final[str] = "Lax"

_COOKIE_TRUE_VALUES = frozenset({"1", "true", "on", "yes"})
_TOGGLE_COOKIE_VALUES = frozenset({"Hide", "Show"})


class _CookieReader(Protocol):
    cookies: Mapping[str, Any]


class _CookieWriter(_CookieReader, Protocol):
    response_headerlist: MutableSequence[tuple[str, str]]


def _cookie_source(source: _CookieReader | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(source, Mapping):
        return cast("Mapping[str, Any]", source)
    return source.cookies


def build_ui_cookie_header(name: str, value: str, *, max_age_seconds: int) -> str:
    """Return the raw Set-Cookie value for a browser-readable UI cookie."""
    encoded_value = quote(str(value), safe="")
    return (
        f"{name}={encoded_value}; path={UI_COOKIE_PATH}; "
        f"max-age={max_age_seconds}; SameSite={UI_COOKIE_SAMESITE}"
    )


def append_ui_cookie(
    request: _CookieWriter,
    name: str,
    value: str,
    *,
    max_age_seconds: int,
) -> None:
    """Append a UI cookie header without collapsing duplicate Set-Cookie lines."""
    # Preserve duplicate Set-Cookie headers so UI-state cookies can coexist
    # with the signed session cookie on the same response.
    request.response_headerlist.append(
        (
            "Set-Cookie",
            build_ui_cookie_header(name, value, max_age_seconds=max_age_seconds),
        ),
    )


def read_cookie_text(
    source: _CookieReader | Mapping[str, Any],
    name: str,
    default: str = "",
) -> str:
    """Read and URL-decode a cookie value as normalized text."""
    raw_value = _cookie_source(source).get(name, default)
    return unquote(str(raw_value)).strip()


def read_cookie_bool(
    source: _CookieReader | Mapping[str, Any],
    name: str,
    *,
    default: bool = False,
) -> bool:
    """Interpret a browser-readable cookie as a conventional truthy flag."""
    raw_value = read_cookie_text(source, name)
    if not raw_value:
        return default
    return raw_value.lower() in _COOKIE_TRUE_VALUES


def read_cookie_toggle_state(
    source: _CookieReader | Mapping[str, Any],
    name: str,
    *,
    default: str = "Show",
) -> str:
    """Return a validated Show or Hide toggle cookie value."""
    raw_value = read_cookie_text(source, name)
    return raw_value if raw_value in _TOGGLE_COOKIE_VALUES else default
