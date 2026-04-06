"""Dispatch fishtest UI routes and preserve the legacy request contract.

Group the UI layer into authentication, list pages, neural-network tools,
user and contributor flows, homepage run lists, run mutation, run detail, and
router registration.
"""

from __future__ import annotations

import contextlib
import copy
import gzip
import hashlib
import logging
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import quote, unquote, urlencode

import bson
import regex
import requests
from fastapi import APIRouter
from markupsafe import Markup
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request  # noqa: TC002
from starlette.responses import HTMLResponse, RedirectResponse, Response
from vtjson import ValidationError, union, validate

import fishtest.github_api as gh
import fishtest.stats.stat_util
from fishtest.http.boundary import (
    build_template_context,
    commit_session_response,
    csrf_or_403,
    forget,
    remember,
)
from fishtest.http.cookie_session import (
    CookieSession,
    authenticated_user,
)
from fishtest.http.csrf import csrf_token_from_form
from fishtest.http.dependencies import (
    get_actiondb,
    get_request_context,
    get_rundb,
    get_userdb,
    get_workerdb,
)
from fishtest.http.open_graph import build_tests_view_open_graph
from fishtest.http.settings import (
    ACTIONS_PAGE_SIZE,
    CONTRIBUTORS_MAX_ALL,
    CONTRIBUTORS_PAGE_SIZE,
    NNS_MAX_ALL,
    NNS_PAGE_SIZE,
    SESSION_REMEMBER_ME_MAX_AGE_SECONDS,
    TASKS_MAX_ALL,
    TASKS_PAGE_SIZE,
    UI_FORM_MAX_FIELDS,
    UI_FORM_MAX_FILES,
    UI_FORM_MAX_PART_SIZE_BYTES,
    UI_HTTP_TIMEOUT_SECONDS,
    UI_STATE_COOKIE_MAX_AGE_SECONDS,
    USER_MANAGEMENT_MAX_ALL,
    USER_MANAGEMENT_PAGE_SIZE,
    WORKERS_MAX_ALL,
    WORKERS_PAGE_SIZE,
)
from fishtest.http.template_helpers import (
    build_contributors_rows,
    build_contributors_summary,
    build_run_table_rows,
    build_tasks_rows,
    build_tests_stats_context,
    run_tables_prefix,
    tests_run_setup,
)
from fishtest.http.template_renderer import render_template_to_response
from fishtest.http.ui_pipeline import apply_http_cache
from fishtest.run_cache import Prio
from fishtest.schemas import (
    RUN_VERSION,
    github_repo_input,
    is_undecided,
    runs_schema,
    short_worker_name,
)
from fishtest.util import (
    VALID_USERNAME_PATTERN,
    email_valid,
    format_date,
    format_group,
    format_results,
    format_time_ago,
    get_chi2,
    get_tc_ratio,
    is_sprt_ltc_data,
    password_strength,
    plural,
    reasonable_run_hashes,
    supported_arches,
    supported_compilers,
    tests_repo,
)
from fishtest.views_actions import actions as _actions_impl
from fishtest.views_finished import get_paginated_finished_runs
from fishtest.views_helpers import (
    _SORT_ORDER_VALUES,
    _append_no_store_headers,
    _append_vary_header,
    _apply_response_headers,
    _build_query_string,
    _clamp_page_index,
    _form_string_value,
    _host_url,
    _is_hx_request,
    _is_truthy_param,
    _normalize_sort_order,
    _normalize_view_mode,
    _page_index_from_params,
    _path_qs,
    pagination,
)
from fishtest.views_machines import (
    _MACHINES_DEFAULT_SORT,
    _MACHINES_PAGE_SIZE,  # noqa: F401 — re-exported for test_users.py
    _MACHINES_SORT_MAP,
    _filtered_machine_count,
    _machine_filter_state,
    _workers_count_label,
)
from fishtest.views_machines import tests_machines as _tests_machines_impl
from fishtest.views_run import (
    can_modify_run,
    del_tasks,
    get_master_info,
    get_nets,  # noqa: F401 — re-exported for test_github_api.py
    get_sha,  # noqa: F401 — re-exported for test_github_api.py
    is_same_user,
    new_run_message,
    parse_spsa_params,  # noqa: F401 — re-exported for test compatibility
    sanitize_options,
    update_nets,
    validate_form,
    validate_modify,
)

HTTP_TIMEOUT = UI_HTTP_TIMEOUT_SECONDS
FORM_MAX_FILES = UI_FORM_MAX_FILES
FORM_MAX_FIELDS = UI_FORM_MAX_FIELDS
FORM_MAX_PART_SIZE = UI_FORM_MAX_PART_SIZE_BYTES
DEFAULT_RECAPTCHA_SITE_KEY = "6LePs8YUAAAAABMmqHZVyVjxat95Z1c_uHrkugZM"

router = APIRouter(tags=["ui"])
logger = logging.getLogger(__name__)

_LTC_TC_RATIO_THRESHOLD = 4
_WORKER_NAME_PARTS = 3
_MAX_NETWORK_SIZE_BYTES = 200_000_000
_THROUGHPUT_NORMAL_LIMIT = 100
_MIN_BOOK_EXITS = 100_000
_RUN_AGE_GITHUB_API_MAX_DAYS = 30

_ACTIVE_RUN_FILTER_VALUES = {
    "test-type": ("sprt", "spsa", "numgames"),
    "time-control": ("stc", "ltc"),
    "threads": ("st", "smp"),
}
_ACTIVE_RUN_FILTER_DIMENSION_BY_VALUE = {
    value: dimension
    for dimension, values in _ACTIVE_RUN_FILTER_VALUES.items()
    for value in values
}

type _RunTableRow = dict[str, str | list[dict[object, object]] | bool]
type _RunTableRows = list[_RunTableRow]
type _SpsaTableRow = list[str]
type _RunArgValue = str | list[str | _SpsaTableRow]
type _RunArg = tuple[str, _RunArgValue, str]
type _RouteMethods = str | tuple[str, ...] | list[str]


class _ActiveRunFilterContext(TypedDict):
    all_enabled: bool
    count_text: str
    enabled_by_dim: dict[str, tuple[str, ...]]
    hidden_selectors: list[str]
    style_text: str
    ordered_runs: list[dict]


class _BatchPanel(TypedDict):
    tbody_id: str
    rows: _RunTableRows
    show_delete: bool
    empty_text: str


class _CountUpdate(TypedDict):
    id: str
    text: str


class _BatchStats(TypedDict):
    pending_hours: str
    cores: int
    nps_m: str
    games_per_minute: int


def _classify_active_run_filters(run: dict) -> dict[str, str]:
    args = run.get("args", {})
    is_spsa = "spsa" in args
    is_sprt = "sprt" in args and not is_spsa
    test_type = "spsa" if is_spsa else ("sprt" if is_sprt else "numgames")
    time_control = (
        "ltc"
        if get_tc_ratio(args.get("tc", "10+0.1"), args.get("threads", 1))
        > _LTC_TC_RATIO_THRESHOLD
        else "stc"
    )
    try:
        threads = int(args.get("threads", 1))
    except TypeError, ValueError:
        threads = 1
    thread_group = "smp" if threads > 1 else "st"
    return {
        "test-type": test_type,
        "time-control": time_control,
        "threads": thread_group,
    }


def _default_active_run_filter_state() -> dict[str, set[str]]:
    return {
        dimension: set(values)
        for dimension, values in _ACTIVE_RUN_FILTER_VALUES.items()
    }


def _parse_active_run_filter_cookie(raw: str) -> dict[str, set[str]]:
    raw = raw.strip()
    if not raw:
        return _default_active_run_filter_state()
    if raw == "none":
        return {dimension: set() for dimension in _ACTIVE_RUN_FILTER_VALUES}

    parsed = {dimension: set() for dimension in _ACTIVE_RUN_FILTER_VALUES}
    saw_valid_value = False
    for token in raw.split(","):
        value = token.strip()
        dimension = _ACTIVE_RUN_FILTER_DIMENSION_BY_VALUE.get(value)
        if dimension is None:
            continue
        parsed[dimension].add(value)
        saw_valid_value = True

    return parsed if saw_valid_value else _default_active_run_filter_state()


def _active_run_matches_enabled_filters(
    run: dict,
    enabled_by_dim: dict[str, set[str]],
) -> bool:
    classifications = _classify_active_run_filters(run)
    return all(
        classifications[dimension] in enabled_by_dim[dimension]
        for dimension in _ACTIVE_RUN_FILTER_VALUES
    )


def _order_active_runs_for_filters(
    active_runs: list[dict],
    enabled_by_dim: dict[str, set[str]],
) -> tuple[list[dict], int]:
    visible_runs: list[dict] = []
    hidden_runs: list[dict] = []

    for index, run in enumerate(active_runs):
        run_copy = dict(run)
        run_copy["_active_filter_index"] = index
        if _active_run_matches_enabled_filters(run_copy, enabled_by_dim):
            visible_runs.append(run_copy)
        else:
            hidden_runs.append(run_copy)

    return visible_runs + hidden_runs, len(visible_runs)


def _build_active_run_filter_context(
    request: _ViewContext,
    active_runs: list[dict],
) -> _ActiveRunFilterContext:
    enabled_by_dim = _parse_active_run_filter_cookie(
        request.cookies.get("active_run_filters", ""),
    )
    hidden_selectors: list[str] = []
    style_text = ""
    ordered_runs, visible_count = _order_active_runs_for_filters(
        active_runs,
        enabled_by_dim,
    )

    all_enabled = True
    for dimension, values in _ACTIVE_RUN_FILTER_VALUES.items():
        enabled_values = enabled_by_dim[dimension]
        if len(enabled_values) < len(values):
            all_enabled = False
        hidden_selectors.extend(
            f'#active-tbody tr[data-{dimension}="{value}"]'
            for value in values
            if value not in enabled_values
        )

    if hidden_selectors:
        hidden_rows = ",\n".join(hidden_selectors)
        style_text = f"{hidden_rows} {{ display: none !important; }}"

    total_count = len(active_runs)
    count_text = (
        f"Active - {total_count} tests"
        if all_enabled
        else f"Active - {total_count} ({visible_count}) tests"
    )

    return {
        "all_enabled": all_enabled,
        "count_text": count_text,
        "enabled_by_dim": {
            dimension: tuple(
                value for value in values if value in enabled_by_dim[dimension]
            )
            for dimension, values in _ACTIVE_RUN_FILTER_VALUES.items()
        },
        "hidden_selectors": hidden_selectors,
        "style_text": style_text,
        "ordered_runs": ordered_runs,
    }


class _TestsRunTablesFragmentContext(TypedDict, total=False):
    panels: list[_BatchPanel]
    count_updates: list[_CountUpdate]
    machines_count: int
    workers_count_text: str
    stats: _BatchStats


class _ViewRouteConfig(TypedDict, total=False):
    renderer: str
    require_csrf: bool
    require_primary: bool
    request_method: _RouteMethods
    http_cache: int
    direct: bool


type _ViewRoute = tuple[Callable[..., Any], str, _ViewRouteConfig]


class _ViewContext:
    """Compatibility shim for the legacy sync view functions.

    The UI layer still uses Pyramid-style handlers that expect a rich request
    object with DB handles, session helpers, and a mutable response header bag.
    FastAPI/Starlette requests are adapted once in `_dispatch_view()` so the
    individual handlers can stay synchronous and focused on shaping template
    context.
    """

    def __init__(
        self,
        request: Request,
        session: CookieSession,
        post: Any,  # noqa: ANN401
        matchdict: dict[str, str],
        context: Any = None,  # noqa: ANN401
    ) -> None:
        self._request = request
        self.raw_request = request
        self.session = session
        self.POST = post or {}
        self.params = request.query_params
        self.query_params = request.query_params
        self.cookies = request.cookies
        self.headers = request.headers
        self.method = request.method
        self.matchdict = matchdict or {}
        self.remember = False
        self.forget = False
        self.remember_max_age = None
        self.response_headers = {}
        self.response_headerlist = []
        self.response_status = 200

        self.url = str(request.url)
        self.path = request.url.path
        self.scheme = request.url.scheme
        self.host = request.headers.get("host") or request.url.netloc
        self.base_url = request.base_url
        self.host_url = str(request.base_url).rstrip("/")
        self.path_qs = request.url.path
        if request.url.query:
            self.path_qs = f"{self.path_qs}?{request.url.query}"
        self.path_url = str(request.url).split("?", 1)[0]
        self.remote_addr = request.client.host if request.client else None

        if context is None:
            self.rundb = get_rundb(request)
            self.userdb = get_userdb(request)
            self.actiondb = get_actiondb(request)
            self.workerdb = get_workerdb(request)
        else:
            self.rundb = context["rundb"]
            self.userdb = context["userdb"]
            self.actiondb = context["actiondb"]
            self.workerdb = context["workerdb"]

    @property
    def authenticated_userid(self) -> str | None:
        return authenticated_user(self.session)

    def has_permission(self, permission: str) -> bool:
        if permission != "approve_run":
            return False
        username = self.authenticated_userid
        if not username:
            return False
        groups = self.userdb.get_user_groups(username)
        return "group:approvers" in (groups or [])


_RequestShim = _ViewContext


async def _dispatch_view(
    fn: Callable[..., Any],
    cfg: _ViewRouteConfig,
    request: Request,
    path_params: dict[str, str],
) -> Response:
    context = get_request_context(request)
    session = context["session"]
    post = None
    if request.method == "POST":
        post = await request.form(
            max_files=FORM_MAX_FILES,
            max_fields=FORM_MAX_FIELDS,
            max_part_size=FORM_MAX_PART_SIZE,
        )
        if cfg.get("require_csrf"):
            csrf_or_403(
                request=request,
                session=session,
                form_token=csrf_token_from_form(post),
            )

    shim = _ViewContext(request, session, post, path_params, context=context)

    if (
        request.method == "POST"
        and cfg.get("require_primary")
        and not shim.rundb.is_primary_instance()
    ):
        response = HTMLResponse(
            "<h1>503 Service Unavailable</h1><p>Primary instance required.</p>",
            status_code=503,
        )
        response.headers.setdefault("Cache-Control", "no-store")
        commit_session_response(request, session, shim, response)
        return _apply_response_headers(shim, response)

    result = await run_in_threadpool(fn, shim)

    if isinstance(result, Response):
        commit_session_response(request, session, shim, result)
        apply_http_cache(result, cfg)
        if request.method == "GET":
            # Same URL can serve full page or htmx fragment depending on headers.
            _append_vary_header(result, "HX-Request")
            result.headers.setdefault("Cache-Control", "no-cache, private")
        return _apply_response_headers(shim, result)

    status_code = getattr(shim, "response_status", 200) or 200

    renderer = cfg.get("renderer")
    if int(status_code) == 204:  # noqa: PLR2004
        response = HTMLResponse("", status_code=204)
    elif isinstance(renderer, str):
        context = result if isinstance(result, dict) else {}
        response = await run_in_threadpool(
            render_template_to_response,
            request=request,
            template_name=renderer,
            context=build_template_context(request, session, context),
            status_code=int(status_code),
        )
    else:
        # Most UI endpoints either redirect or render templates.
        response = HTMLResponse("", status_code=204)

    commit_session_response(request, session, shim, response)
    apply_http_cache(response, cfg)
    if request.method == "GET":
        # Several UI endpoints return either full-page HTML or fragment HTML
        # for the same URL based on the HX-Request header.
        _append_vary_header(response, "HX-Request")
        response.headers.setdefault("Cache-Control", "no-cache, private")
    return _apply_response_headers(shim, response)


# === Authentication ===


def _render_hx_fragment(
    request: _ViewContext,
    template_name: str,
    context: dict[str, Any],
) -> Response | None:
    if not _is_hx_request(request):
        return None
    return render_template_to_response(
        request=request.raw_request,
        template_name=template_name,
        context=build_template_context(request.raw_request, request.session, context),
    )


def _render_hx_or_context(
    request: _ViewContext,
    template_name: str,
    context: dict[str, Any],
    *,
    extra_context: dict[str, Any] | None = None,
) -> Response | dict[str, Any]:
    hx_context = context if extra_context is None else {**context, **extra_context}
    return _render_hx_fragment(request, template_name, hx_context) or context


# === Home Redirect ===
def home(request: object = None) -> RedirectResponse:  # noqa: ARG001
    """Redirect / to /tests. Registered directly on the router (no _dispatch_view)."""
    response = RedirectResponse(url="/tests", status_code=302)
    response.headers.setdefault("Cache-Control", "no-cache, private")
    return response


# === Login And Signup ===
def ensure_logged_in(request: _ViewContext) -> str | RedirectResponse:
    """Return authenticated user id or a login RedirectResponse.

    Pyramid used exception-based redirect control flow. In the FastAPI port,
    callers must check `isinstance(result, RedirectResponse)`.
    """
    userid = request.authenticated_userid
    if not userid:
        request.session.flash("Please login")
        return RedirectResponse(
            url=f"/login?{urlencode({'next': _path_qs(request)})}",
            status_code=302,
        )
    return userid


def login(request: _ViewContext) -> dict[str, Any] | RedirectResponse:
    _append_no_store_headers(request)
    userid = request.authenticated_userid
    if userid:
        return home(request)
    login_url = f"{_host_url(request)}/login"
    referrer = request.url
    if referrer == login_url:
        referrer = "/"  # never use the login form itself as came_from
    came_from = request.params.get("came_from", referrer)

    if request.method == "POST":
        stay_logged_in_values: list[str] = []
        getlist = getattr(request.POST, "getlist", None)
        if callable(getlist):
            stay_logged_in_values = [
                str(v).strip().lower() for v in getlist("stay_logged_in")
            ]
        else:
            raw_stay_logged_in = request.POST.get("stay_logged_in")
            if raw_stay_logged_in is not None:
                stay_logged_in_values = [str(raw_stay_logged_in).strip().lower()]

        # Default to persistent login when the field is absent, and allow
        # explicit opt-out via stay_logged_in=0.
        stay_logged_in = not stay_logged_in_values or any(
            value in {"1", "true", "on", "yes"} for value in stay_logged_in_values
        )

        username = _form_string_value(request.POST, "username")
        password = _form_string_value(request.POST, "password")
        token = request.userdb.authenticate(username, password)
        if "error" not in token:
            if stay_logged_in:
                remember(request, username, max_age=SESSION_REMEMBER_ME_MAX_AGE_SECONDS)
            else:
                # Session ends when the browser is closed
                remember(request, username)
            next_page = request.params.get("next") or came_from
            return RedirectResponse(url=next_page, status_code=302)
        message = token["error"]
        # `error_code` is a stable contract from `UserDb.authenticate()`.
        if token.get("error_code") == "pending":
            message += (
                " If you recently registered to fishtest, "
                "a person will now manually approve your new account, to avoid spam. "
                "This is usually quick, but sometimes takes a few hours. "
                "Thank you!"
            )
        request.session.flash(message, "error")
    return {}


def logout(request: _ViewContext) -> RedirectResponse:
    session = request.session
    forget(request)
    session.invalidate()
    return RedirectResponse(url="/tests", status_code=302)


def signup(request: _ViewContext) -> dict[str, Any] | RedirectResponse:  # noqa: C901, PLR0911, PLR0912, PLR0915
    _append_no_store_headers(request)
    recaptcha_site_key = os.environ.get(
        "FISHTEST_CAPTCHA_SITE_KEY",
        DEFAULT_RECAPTCHA_SITE_KEY,
    ).strip()
    signup_context = {
        "recaptcha_site_key": recaptcha_site_key,
        "VALID_USERNAME_PATTERN": VALID_USERNAME_PATTERN,
    }

    if request.authenticated_userid:
        return home(request)
    if request.method != "POST":
        return signup_context
    errors = []

    signup_username = _form_string_value(request.POST, "username").strip()
    signup_password = _form_string_value(request.POST, "password").strip()
    signup_password_verify = _form_string_value(request.POST, "password2").strip()
    signup_email = _form_string_value(request.POST, "email").strip()
    tests_repo = _form_string_value(request.POST, "tests_repo").strip()

    strong_password, password_err = password_strength(
        signup_password,
        signup_username,
        signup_email,
    )
    if not strong_password:
        errors.append(password_err)
    if signup_password != signup_password_verify:
        errors.append("Error! Matching verify password required")
    email_is_valid, validated_email = email_valid(signup_email)
    if not email_is_valid:
        errors.append("Error! Invalid email: " + validated_email)
    if len(signup_username) == 0:
        errors.append("Error! Username required")
    if not signup_username.isalnum():
        errors.append("Error! Alphanumeric username required")

    try:
        validate(union(github_repo_input, ""), tests_repo, "tests_repo")
    except ValidationError as e:
        errors.append(f"Error! Invalid tests repo {tests_repo}: {e!s}")

    if errors:
        for error in errors:
            request.session.flash(error, "error")
        return signup_context

    secret = os.environ.get("FISHTEST_CAPTCHA_SECRET", "").strip()
    captcha_response = _form_string_value(
        request.POST,
        "g-recaptcha-response",
    ).strip()

    if not secret:
        request.session.flash("Captcha configuration is missing", "error")
        return signup_context

    if not captcha_response:
        request.session.flash("Captcha required", "error")
        return signup_context

    payload = {
        "secret": secret,
        "response": captcha_response,
        "remoteip": request.remote_addr,
    }
    try:
        response = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data=payload,
            timeout=HTTP_TIMEOUT,
        ).json()
    except requests.RequestException, ValueError:
        request.session.flash("Captcha verification failed", "error")
        return signup_context

    if "success" not in response or not response["success"]:
        if "error-codes" in response:
            logger.warning(response["error-codes"])
        request.session.flash("Captcha failed", "error")
        return signup_context

    result = request.userdb.create_user(
        username=signup_username,
        password=signup_password,
        email=validated_email,
        tests_repo=tests_repo,
    )

    if result is None:
        request.session.flash("Error! Invalid username or password", "error")
    elif not result:
        request.session.flash("Username or email is already registered", "error")
    else:
        request.session.flash(
            "Account created! "
            "To avoid spam, a person will now manually approve your new account. "
            "This is usually quick but sometimes takes a few hours. "
            "Thank you for contributing!",
        )
        return RedirectResponse(url="/login", status_code=302)
    return signup_context


# === Lists ===


# === Workers ===
# Note that the allowed length of mailto URLs on Chrome/Windows is severely
# limited.
def worker_email(
    worker_name: str,
    blocker_name: str,
    message: str,
    host_url: str,
    blocked: object,  # noqa: ARG001
) -> str:
    owner_name = worker_name.split("-", maxsplit=1)[0]
    body = f"""\
Dear {owner_name},

Thank you for contributing to the development of \
Stockfish. Unfortunately, it seems your Fishtest \
worker {worker_name} has some issue(s). More \
specifically the following has been reported:

{message}

You may possibly find more information about this \
in our event log at {host_url}/actions

Feel free to reply to this email if you require \
any help, or else contact the #fishtest-dev \
channel on the Stockfish Discord server: \
https://discord.com/invite/awnh2qZfTT

Enjoy your day,

{blocker_name} (Fishtest approver)

"""
    return body  # noqa: RET504


def normalize_lf(m: str) -> str:
    m = m.replace("\r\n", "\n").replace("\r", "\n")
    return m.rstrip()


def _blocked_worker_rows(
    blocked_workers: list[dict[str, Any]],
    *,
    show_email: bool,
) -> list[dict[str, Any]]:
    rows = []
    for worker in blocked_workers:
        worker_name_value = worker.get("worker_name", "")
        last_updated = worker.get("last_updated")
        last_updated_label = (
            format_time_ago(last_updated) if last_updated is not None else "Never"
        )
        actions_url = f"/actions?text={quote(f'"{worker_name_value}"')}"
        owner_email = worker.get("owner_email", "")
        subject = worker.get("subject", "")
        body = worker.get("body", "")
        mailto_url = ""
        if show_email and owner_email:
            body_encoded = quote(body.replace("\n", "\r\n"))
            mailto_url = (
                f"mailto:{owner_email}?subject={quote(subject)}&body={body_encoded}"
            )
        rows.append(
            {
                "worker_name": worker_name_value,
                "worker_name_key": worker_name_value.lower(),
                "last_updated": last_updated,
                "last_updated_label": last_updated_label,
                "actions_url": actions_url,
                "owner_email": owner_email,
                "mailto_url": mailto_url,
            },
        )
    return rows


def _filter_blocked_workers(
    blocked_workers: list[dict[str, Any]],
    filter_value: str,
) -> list[dict[str, Any]]:
    if filter_value == "all-workers":
        return blocked_workers

    threshold_5d = datetime.now(UTC) - timedelta(days=5)
    if filter_value == "gt-5days":
        return [
            worker
            for worker in blocked_workers
            if worker.get("last_updated") and worker["last_updated"] < threshold_5d
        ]

    # Default to recent workers when an unknown filter is provided.
    return [
        worker
        for worker in blocked_workers
        if not worker.get("last_updated") or worker["last_updated"] >= threshold_5d
    ]


_WORKERS_FILTER_DEFAULT = "le-5days"
_WORKERS_FILTER_VALUES = {"all-workers", "le-5days", "gt-5days"}
_WORKERS_SORT_MAP = {
    "worker": ("worker_name", False),
    "last_changed": ("last_updated", True),
    "events": ("actions_url", False),
    "email": ("owner_email", False),
}
_WORKERS_DEFAULT_SORT = "last_changed"
_WORKERS_PAGE_SIZE = WORKERS_PAGE_SIZE
_WORKERS_MAX_ALL = WORKERS_MAX_ALL
_WORKERS_FILTER_FIELD = "worker_name"

_USER_MANAGEMENT_GROUP_DEFAULT = "pending"
_USER_MANAGEMENT_GROUP_VALUES = {"all", "pending", "blocked", "idle", "approvers"}
_USER_MANAGEMENT_SORT_MAP = {
    "username": ("username", False),
    "registration": ("registration_time", True),
    "groups": ("groups_label", False),
    "email": ("email", False),
}
_USER_MANAGEMENT_DEFAULT_SORT = "registration"
_USER_MANAGEMENT_PAGE_SIZE = USER_MANAGEMENT_PAGE_SIZE
_USER_MANAGEMENT_MAX_ALL = USER_MANAGEMENT_MAX_ALL
_USER_MANAGEMENT_FILTER_FIELD = "username"


def _workers_query_string(
    *,
    filter_value: str,
    sort_param: str,
    order_param: str,
    query_filter: str,
    view: str,
) -> str:
    _, default_reverse = _WORKERS_SORT_MAP[_WORKERS_DEFAULT_SORT]
    default_order = "desc" if default_reverse else "asc"

    params = []
    if filter_value != _WORKERS_FILTER_DEFAULT:
        params.append(("filter", filter_value))
    if sort_param != _WORKERS_DEFAULT_SORT:
        params.append(("sort", sort_param))
    if order_param != default_order:
        params.append(("order", order_param))
    if query_filter:
        params.append(("q", query_filter))
    if view == "all":
        params.append(("view", "all"))
    return _build_query_string(params)


def _user_management_query_string(
    *,
    group: str,
    sort_param: str,
    order_param: str,
    query_filter: str,
    view: str,
) -> str:
    _, default_reverse = _USER_MANAGEMENT_SORT_MAP[_USER_MANAGEMENT_DEFAULT_SORT]
    default_order = "desc" if default_reverse else "asc"

    params = []
    if group != _USER_MANAGEMENT_GROUP_DEFAULT:
        params.append(("group", group))
    if sort_param != _USER_MANAGEMENT_DEFAULT_SORT:
        params.append(("sort", sort_param))
    if order_param != default_order:
        params.append(("order", order_param))
    if query_filter:
        params.append(("q", query_filter))
    if view == "all":
        params.append(("view", "all"))
    return _build_query_string(params)


def _workers_sort_value(row: dict[str, Any], sort_key: str) -> Any:  # noqa: ANN401
    if sort_key == "last_updated":
        value = row.get("last_updated")
        if isinstance(value, datetime):
            return value.timestamp()
        return 0
    return str(row.get(sort_key, "")).lower()


def _user_management_sort_value(row: dict[str, Any], sort_key: str) -> Any:  # noqa: ANN401
    if sort_key == "registration_time":
        value = row.get("registration_time")
        if isinstance(value, datetime):
            return value.timestamp()
        return 0
    return str(row.get(sort_key, "")).lower()


def workers(request: _ViewContext) -> dict[str, Any] | Response:  # noqa: C901, PLR0912, PLR0915
    is_approver = request.has_permission("approve_run")
    filter_value = request.params.get("filter", _WORKERS_FILTER_DEFAULT)
    if filter_value not in _WORKERS_FILTER_VALUES:
        filter_value = _WORKERS_FILTER_DEFAULT

    sort_param = request.params.get("sort", _WORKERS_DEFAULT_SORT)
    if sort_param not in _WORKERS_SORT_MAP:
        sort_param = _WORKERS_DEFAULT_SORT
    if not is_approver and sort_param == "email":
        sort_param = _WORKERS_DEFAULT_SORT

    sort_key, default_reverse = _WORKERS_SORT_MAP[sort_param]
    default_order = "desc" if default_reverse else "asc"
    order_param = request.params.get("order", default_order)
    if order_param not in _SORT_ORDER_VALUES:
        order_param = default_order

    view_param = _normalize_view_mode(request.params.get("view", "paged"))

    query_filter = request.params.get("q", "").strip()
    page_idx = _page_index_from_params(request.params)

    blocked_workers = request.rundb.workerdb.get_blocked_workers()
    authenticated_username = request.authenticated_userid

    # Approvers should already be authenticated; keep the login redirect
    # contract here so the type is narrowed by control flow.
    if is_approver:
        approver_result = ensure_logged_in(request)
        if isinstance(approver_result, RedirectResponse):
            return approver_result
        authenticated_username = approver_result
        for w in blocked_workers:
            owner_name = w["worker_name"].split("-")[0]
            owner = request.userdb.get_user(owner_name)
            w["owner_email"] = owner["email"] if owner is not None else ""
            w["body"] = worker_email(
                w["worker_name"],
                authenticated_username,
                w["message"],
                _host_url(request),
                w["blocked"],
            )
            w["subject"] = f"Issue(s) with worker {w['worker_name']}"

    worker_name = request.matchdict.get("worker_name")
    show_admin = False
    admin_context = {}

    try:
        validate(union(short_worker_name, "show"), worker_name, name="worker_name")
    except ValidationError as e:
        request.session.flash(str(e), "error")
    else:
        if not isinstance(worker_name, str) or (
            len(worker_name.split("-")) != _WORKER_NAME_PARTS
        ):
            pass  # fall through to shared rendering
        else:
            result = ensure_logged_in(request)
            if isinstance(result, RedirectResponse):
                return result
            authenticated_username = result
            owner_name = worker_name.split("-")[0]
            if not is_approver and authenticated_username != owner_name:
                request.session.flash(
                    "Only owners and approvers can block/unblock",
                    "error",
                )
            elif request.method == "POST":
                button = request.POST.get("submit")
                if button == "Submit":
                    blocked = request.POST.get("blocked") is not None
                    message = _form_string_value(request.POST, "message")
                    max_chars = 500
                    if len(message) > max_chars:
                        request.session.flash(
                            "Warning: your description of the"
                            " issue has been truncated to"
                            f" {max_chars} characters",
                            "error",
                        )
                        message = message[:max_chars]
                    message = normalize_lf(message)
                    was_blocked = request.workerdb.get_worker(worker_name)["blocked"]
                    request.rundb.workerdb.update_worker(
                        worker_name,
                        blocked=blocked,
                        message=message,
                    )
                    if blocked != was_blocked:
                        request.session.flash(
                            f"Worker {worker_name}"
                            f" {'blocked' if blocked else 'unblocked'}!",
                        )
                        request.actiondb.block_worker(
                            username=authenticated_username,
                            worker=worker_name,
                            message="blocked" if blocked else "unblocked",
                        )
                return RedirectResponse(url="/workers/show", status_code=302)
            else:
                w = request.rundb.workerdb.get_worker(worker_name)
                show_admin = True
                admin_context = {
                    "worker_name": worker_name,
                    "blocked": w["blocked"],
                    "message": w["message"],
                    "last_updated_label": (
                        format_time_ago(w["last_updated"])
                        if w["last_updated"]
                        else "Never"
                    ),
                }

    # --- shared rendering for all non-redirect branches ---
    filtered_rows = _blocked_worker_rows(
        _filter_blocked_workers(blocked_workers, filter_value),
        show_email=is_approver,
    )

    if query_filter:
        query_folded = query_filter.casefold()
        filtered_rows = [
            row
            for row in filtered_rows
            if query_folded in str(row.get(_WORKERS_FILTER_FIELD, "")).casefold()
        ]

    filtered_rows.sort(
        key=lambda row: (
            _workers_sort_value(row, sort_key),
            row.get("worker_name_key", ""),
        ),
        reverse=(order_param == "desc"),
    )

    num_workers = len(filtered_rows)
    is_truncated = False
    if view_param == "all":
        if len(filtered_rows) > _WORKERS_MAX_ALL:
            filtered_rows = filtered_rows[:_WORKERS_MAX_ALL]
            is_truncated = True
    else:
        start = page_idx * _WORKERS_PAGE_SIZE
        filtered_rows = filtered_rows[start : start + _WORKERS_PAGE_SIZE]

    query_params = _workers_query_string(
        filter_value=filter_value,
        sort_param=sort_param,
        order_param=order_param,
        query_filter=query_filter,
        view=view_param,
    )
    pages = (
        pagination(page_idx, num_workers, _WORKERS_PAGE_SIZE, query_params)
        if view_param == "paged"
        else []
    )

    context = {
        "show_admin": show_admin,
        "show_email": is_approver,
        "blocked_workers": filtered_rows,
        "filter_value": filter_value,
        "sort": sort_param,
        "order": order_param,
        "q": query_filter,
        "view": view_param,
        "pages": pages,
        "num_workers": num_workers,
        "max_all": _WORKERS_MAX_ALL,
        "is_truncated": is_truncated,
        **admin_context,
    }

    return _render_hx_or_context(
        request,
        "workers_content_fragment.html.j2",
        context,
        extra_context={"is_hx": True},
    )


# === Neural Networks ===
def upload(request: _ViewContext) -> dict[str, Any] | RedirectResponse:  # noqa: C901, PLR0911, PLR0912, PLR0915
    result = ensure_logged_in(request)
    if isinstance(result, RedirectResponse):
        return result
    base_context = {
        "upload_url": str(request.url),
        "testing_guidelines_url": "https://github.com/official-stockfish/fishtest/wiki/Creating-my-first-test",
        "cc0_url": "https://creativecommons.org/share-your-work/public-domain/cc0/",
        "nn_stats_url": "/nns",
    }

    if request.method != "POST":
        return base_context
    try:
        filename = request.POST["network"].filename
        input_file = request.POST["network"].file
        network = input_file.read()
    except AttributeError:
        request.session.flash(
            "Specify a network file with the 'Choose File' button",
            "error",
        )
        return base_context
    except Exception:
        logger.exception("Error reading the network file")
        request.session.flash("Error reading the network file", "error")
        return base_context
    if request.rundb.get_nn(filename):
        request.session.flash(f"Network {filename} already exists", "error")
        return base_context
    errors = []
    if len(network) >= _MAX_NETWORK_SIZE_BYTES:
        errors.append("Network must be < 200MB")
    if not re.match(r"^nn-[0-9a-f]{12}\.nnue$", filename):
        errors.append('Name must match "nn-[SHA256 first 12 digits].nnue"')
    net_hash = hashlib.sha256(network).hexdigest()
    if net_hash[:12] != filename[3:15]:
        errors.append(f"Wrong SHA256 hash: {net_hash[:12]} Filename: {filename[3:15]}")
    if errors:
        for error in errors:
            request.session.flash(error, "error")
        return base_context
    net_file_gz = Path("/var/www/fishtest/nn") / f"{filename}.gz"
    try:
        with gzip.open(net_file_gz, "xb") as f:
            f.write(network)
    except FileExistsError:
        logger.exception("Network %s already uploaded", filename)
        request.session.flash(f"Network {filename} already uploaded", "error")
        return base_context
    except Exception:
        net_file_gz.unlink(missing_ok=True)
        logger.exception("Failed to write network %s", filename)
        request.session.flash(f"Failed to write network {filename}", "error")
        return base_context
    try:
        net_data = gzip.decompress(net_file_gz.read_bytes())
    except Exception:
        net_file_gz.unlink()
        logger.exception("Failed to read uploaded network %s", filename)
        request.session.flash(f"Failed to read uploaded network {filename}", "error")
        return base_context

    net_hash = hashlib.sha256(net_data).hexdigest()
    if net_hash[:12] != filename[3:15]:
        net_file_gz.unlink()
        request.session.flash(f"Invalid hash for uploaded network {filename}", "error")
        return base_context

    if request.rundb.get_nn(filename):
        request.session.flash(f"Network {filename} already exists", "error")
        return base_context

    request.rundb.upload_nn(request.authenticated_userid, filename)

    request.actiondb.upload_nn(
        username=request.authenticated_userid,
        nn=filename,
    )

    return RedirectResponse(url="/nns", status_code=302)


def nns(request: _ViewContext) -> dict[str, Any] | Response:  # noqa: C901, PLR0912, PLR0915
    user = request.params.get("user", "")
    network_name = request.params.get("network_name", "")
    sort_param = request.params.get("sort", "time")
    if sort_param not in {
        "time",
        "name",
        "user",
        "first_test",
        "last_test",
        "downloads",
    }:
        sort_param = "time"
    order_param = request.params.get("order", "desc")
    if order_param not in {"asc", "desc"}:
        order_param = "desc"
    view_param = request.params.get("view", "paged")
    if view_param not in {"paged", "all"}:
        view_param = "paged"

    page_size = NNS_PAGE_SIZE
    max_all = NNS_MAX_ALL

    def _truthy(value: Any) -> bool:  # noqa: ANN401
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "on", "yes"}

    master_only_param = request.params.get("master_only")
    if master_only_param is None:
        master_only = _truthy(request.cookies.get("master_only", "false"))
    else:
        master_only = _truthy(master_only_param)

    page_idx = 0
    page_param = request.params.get("page", "")
    if view_param == "paged":
        page_idx = max(0, int(page_param) - 1) if page_param.isdigit() else 0

    nns, num_nns = request.rundb.get_nns(
        user=user,
        network_name=network_name,
        master_only=master_only,
        limit=0,
        skip=0,
    )
    nns = list(nns)
    nns_summary = {
        "nets": num_nns,
        "master_nets": sum(1 for nn in nns if nn.get("is_master")),
        "contributors": len({nn.get("user") for nn in nns if nn.get("user")}),
        "downloads": sum(int(nn.get("downloads", 0)) for nn in nns),
    }

    def _first_test_date(nn: dict[str, Any]) -> datetime:
        return (nn.get("first_test") or {}).get("date") or datetime.min.replace(
            tzinfo=UTC,
        )

    def _last_test_date(nn: dict[str, Any]) -> datetime:
        return (nn.get("last_test") or {}).get("date") or datetime.min.replace(
            tzinfo=UTC,
        )

    def _sort_key(nn: dict[str, Any]) -> tuple[object, str]:
        key_map = {
            "time": nn.get("time") or datetime.min.replace(tzinfo=UTC),
            "name": nn.get("name", "").lower(),
            "user": nn.get("user", "").lower(),
            "first_test": _first_test_date(nn),
            "last_test": _last_test_date(nn),
            "downloads": int(nn.get("downloads", 0)),
        }
        # Deterministic tie-break to avoid row jitter between requests.
        return (key_map[sort_param], nn.get("name", "").lower())

    nns.sort(key=_sort_key, reverse=(order_param == "desc"))

    if view_param == "paged":
        start = page_idx * page_size
        nns = nns[start : start + page_size]

    is_truncated = False
    if view_param == "all" and len(nns) > max_all:
        nns = nns[:max_all]
        is_truncated = True

    formatted_nns = []
    for nn in nns:
        time_value = nn.get("time")
        time_label = time_value.strftime("%y-%m-%d %H:%M:%S") if time_value else ""

        first_test = nn.get("first_test") or {}
        first_test_id = first_test.get("id")
        first_test_date = first_test.get("date")
        first_test_label = str(first_test_date).split(".")[0] if first_test_date else ""

        last_test = nn.get("last_test") or {}
        last_test_id = last_test.get("id")
        last_test_date = last_test.get("date")
        last_test_label = str(last_test_date).split(".")[0] if last_test_date else ""

        name = nn.get("name", "")
        formatted_nns.append(
            {
                **nn,
                "name": name,
                "user": nn.get("user", ""),
                "downloads": nn.get("downloads", 0),
                "is_master": bool(nn.get("is_master")),
                "time_label": time_label,
                "name_url": f"/api/nn/{name}" if name else "",
                "first_test_label": first_test_label,
                "first_test_url": (
                    f"/tests/view/{first_test_id}" if first_test_id else ""
                ),
                "last_test_label": last_test_label,
                "last_test_url": f"/tests/view/{last_test_id}" if last_test_id else "",
            },
        )

    query_dict = {
        "view": view_param,
        "sort": sort_param,
        "order": order_param,
    }
    if user:
        query_dict["user"] = user
    if network_name:
        query_dict["network_name"] = network_name
    if master_only:
        query_dict["master_only"] = "1"

    query_params = "&" + urlencode(query_dict)

    pages = []
    if view_param == "paged":
        pages = pagination(page_idx, num_nns, page_size, query_params)

    context = {
        "nns": formatted_nns,
        "nns_summary": nns_summary,
        "pages": pages,
        "master_only": master_only,
        "view": view_param,
        "sort": sort_param,
        "order": order_param,
        "num_nns": num_nns,
        "max_all": max_all,
        "is_truncated": is_truncated,
        "filters": {
            "network_name": network_name,
            "user": user,
            "master_only": master_only,
        },
        "network_name_filter": network_name,
        "user_filter": user,
        "cookie_max_age": UI_STATE_COOKIE_MAX_AGE_SECONDS,
    }

    return (
        _render_hx_fragment(request, "nns_content_fragment.html.j2", context) or context
    )


def sprt_calc(request: _ViewContext) -> dict[str, Any]:  # noqa: ARG001
    return {}


def _build_rate_limits_context() -> dict[str, Any]:
    server_rate_limit = -1
    server_reset = "00:00:00"

    try:
        rate_limit = gh.rate_limit()
        server_rate_limit = int(rate_limit.get("remaining", -1))
        reset_timestamp = float(rate_limit.get("reset", 0))
        if reset_timestamp > 0:
            server_reset = datetime.fromtimestamp(reset_timestamp, UTC).strftime(
                "%H:%M:%S",
            )
    except Exception:  # noqa: BLE001, S110
        # Keep default placeholder values when GitHub is unavailable.
        pass

    return {
        "server_rate_limit": server_rate_limit,
        "server_reset": server_reset,
    }


def rate_limits(request: _ViewContext) -> dict[str, Any]:  # noqa: ARG001
    return _build_rate_limits_context()


def rate_limits_server(request: _ViewContext) -> Response:  # noqa: ARG001
    context = _build_rate_limits_context()
    server_rate_limit = context["server_rate_limit"]
    server_reset = context["server_reset"]
    return HTMLResponse(
        f'{server_rate_limit}<span id="server_reset" hx-swap-oob="innerHTML">'
        f"{server_reset}</span>",
    )


def user_management_pending_count(request: _ViewContext) -> dict[str, Any]:  # noqa: ARG001
    return {}


def actions(request: _ViewContext) -> dict[str, Any] | RedirectResponse | Response:
    result = _actions_impl(request, page_size=ACTIONS_PAGE_SIZE)
    if isinstance(result, RedirectResponse):
        return result
    return (
        _render_hx_fragment(request, "actions_content_fragment.html.j2", result)
        or result
    )


# === Users ===
def get_idle_users(
    users: list[dict[str, Any]],
    request: _ViewContext,
) -> list[dict[str, Any]]:
    idle = {}
    for u in users:
        idle[u["username"]] = u
    for u in request.userdb.user_cache.find():
        del idle[u["username"]]
    return list(idle.values())


def _user_management_rows(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for user in users:
        username = user.get("username", "")
        registration_time = user.get("registration_time")
        registration_label = (
            registration_time.strftime("%y-%m-%d %H:%M:%S")
            if registration_time
            else "Unknown"
        )
        groups = user.get("groups", [])
        rows.append(
            {
                "username": username,
                "user_url": f"/user/{username}" if username else "",
                "username_key": username.lower(),
                "registration_time": registration_time,
                "registration_label": registration_label,
                "groups": groups,
                "groups_label": format_group(groups),
                "email": user.get("email", ""),
            },
        )
    return rows


def user_management(request: _ViewContext) -> dict[str, Any] | Response:  # noqa: C901
    _append_no_store_headers(request)
    if not request.has_permission("approve_run"):
        request.session.flash("You cannot view user management", "error")
        return home(request)

    group = request.params.get("group", _USER_MANAGEMENT_GROUP_DEFAULT)
    if group not in _USER_MANAGEMENT_GROUP_VALUES:
        group = _USER_MANAGEMENT_GROUP_DEFAULT

    sort_param = request.params.get("sort", _USER_MANAGEMENT_DEFAULT_SORT)
    if sort_param not in _USER_MANAGEMENT_SORT_MAP:
        sort_param = _USER_MANAGEMENT_DEFAULT_SORT

    sort_key, default_reverse = _USER_MANAGEMENT_SORT_MAP[sort_param]
    order_param, _ = _normalize_sort_order(
        request.params.get("order", ""),
        default_reverse=default_reverse,
    )

    view_param = _normalize_view_mode(request.params.get("view", "paged"))

    query_filter = request.params.get("q", "").strip()
    page_idx = _page_index_from_params(request.params)

    users = list(request.userdb.get_users())
    pending_users = request.userdb.get_pending()
    blocked_users = request.userdb.get_blocked()
    idle_users = get_idle_users(users, request)

    all_count = len(users)
    pending_count = len(pending_users)
    blocked_count = len(blocked_users)
    idle_count = len(idle_users)

    if group == "all":
        selected_rows = _user_management_rows(users)
    elif group == "pending":
        selected_rows = _user_management_rows(pending_users)
    elif group == "blocked":
        selected_rows = _user_management_rows(blocked_users)
    elif group == "idle":
        selected_rows = _user_management_rows(idle_users)
    else:
        selected_rows = [
            user
            for user in _user_management_rows(users)
            if "group:approvers" in user.get("groups", [])
        ]

    if query_filter:
        query_folded = query_filter.casefold()
        selected_rows = [
            row
            for row in selected_rows
            if query_folded
            in str(row.get(_USER_MANAGEMENT_FILTER_FIELD, "")).casefold()
        ]

    selected_rows.sort(
        key=lambda row: (
            _user_management_sort_value(row, sort_key),
            row.get("username_key", ""),
        ),
        reverse=(order_param == "desc"),
    )

    num_selected = len(selected_rows)
    is_truncated = False
    if view_param == "all":
        if len(selected_rows) > _USER_MANAGEMENT_MAX_ALL:
            selected_rows = selected_rows[:_USER_MANAGEMENT_MAX_ALL]
            is_truncated = True
    else:
        start = page_idx * _USER_MANAGEMENT_PAGE_SIZE
        selected_rows = selected_rows[start : start + _USER_MANAGEMENT_PAGE_SIZE]

    query_params = _user_management_query_string(
        group=group,
        sort_param=sort_param,
        order_param=order_param,
        query_filter=query_filter,
        view=view_param,
    )
    pages = (
        pagination(page_idx, num_selected, _USER_MANAGEMENT_PAGE_SIZE, query_params)
        if view_param == "paged"
        else []
    )

    approvers_count = len(
        [user for user in users if "group:approvers" in user.get("groups", [])],
    )

    context = {
        "all_count": all_count,
        "pending_count": pending_count,
        "blocked_count": blocked_count,
        "idle_count": idle_count,
        "approvers_count": approvers_count,
        "group": group,
        "selected_users": selected_rows,
        "sort": sort_param,
        "order": order_param,
        "q": query_filter,
        "view": view_param,
        "pages": pages,
        "num_selected_users": num_selected,
        "max_all": _USER_MANAGEMENT_MAX_ALL,
        "is_truncated": is_truncated,
    }

    return _render_hx_or_context(
        request,
        "user_management_content_fragment.html.j2",
        context,
        extra_context={"is_hx": True},
    )


def user(request: _ViewContext) -> dict[str, Any] | RedirectResponse:  # noqa: C901, PLR0911, PLR0912, PLR0915
    _append_no_store_headers(request)
    userid = ensure_logged_in(request)
    if isinstance(userid, RedirectResponse):
        return userid

    user_name = request.matchdict.get("username", userid)
    profile = user_name == userid
    if not profile and not request.has_permission("approve_run"):
        request.session.flash("You cannot inspect users", "error")
        return home(request)

    user_data = request.userdb.get_user(user_name)
    if user_data is None:
        raise StarletteHTTPException(status_code=404)
    if "user" in request.POST:
        if profile:
            old_password = _form_string_value(request.POST, "old_password").strip()
            new_password = _form_string_value(request.POST, "password").strip()
            new_password_verify = _form_string_value(request.POST, "password2").strip()
            new_email = _form_string_value(request.POST, "email").strip()
            tests_repo = _form_string_value(request.POST, "tests_repo").strip()

            # Temporary comparison until passwords are hashed.
            if old_password != user_data["password"].strip():
                request.session.flash("Invalid password!", "error")
                return home(request)

            if len(new_password) > 0:
                if new_password == new_password_verify:
                    strong_password, password_err = password_strength(
                        new_password,
                        user_name,
                        user_data["email"],
                        (new_email if len(new_email) > 0 else None),
                    )
                    if strong_password:
                        user_data["password"] = new_password
                        request.session.flash("Success! Password updated")
                    else:
                        request.session.flash(password_err, "error")
                        return home(request)
                else:
                    request.session.flash(
                        "Error! Matching verify password required",
                        "error",
                    )
                    return home(request)

            try:
                validate(union(github_repo_input, ""), tests_repo, "tests_repo")
            except ValidationError as e:
                request.session.flash(
                    f"Error! Invalid test repo {tests_repo}: {e!s}",
                    "error",
                )
                return home(request)

            user_data["tests_repo"] = tests_repo

            if len(new_email) > 0 and user_data["email"] != new_email:
                email_is_valid, validated_email = email_valid(new_email)
                if not email_is_valid:
                    request.session.flash(
                        "Error! Invalid email: " + validated_email,
                        "error",
                    )
                    return home(request)
                user_data["email"] = validated_email
                request.session.flash("Success! Email updated")
            request.userdb.save_user(user_data)
        elif "blocked" in request.POST and request.POST["blocked"].isdigit():
            user_data["blocked"] = bool(int(request.POST["blocked"]))
            request.session.flash(
                ("Blocked" if user_data["blocked"] else "Unblocked")
                + " user "
                + user_name,
            )
            request.userdb.clear_cache()
            request.userdb.save_user(user_data)
            request.actiondb.block_user(
                username=userid,
                user=user_name,
                message="blocked" if user_data["blocked"] else "unblocked",
            )

        elif "pending" in request.POST and user_data["pending"]:
            request.userdb.clear_cache()
            if request.POST["pending"] == "0":
                user_data["pending"] = False
                request.userdb.save_user(user_data)
                request.actiondb.accept_user(
                    username=userid,
                    user=user_name,
                    message="accepted",
                )
            else:
                request.userdb.remove_user(user_data, userid)
        return home(request)
    userc = request.userdb.user_cache.find_one({"username": user_name})
    hours = int(userc["cpu_hours"]) if userc is not None else 0

    safe_tests_repo_url = ""
    extract_repo_from_link = ""
    if user_data["tests_repo"] != "":
        try:
            user, repo = gh.parse_repo(user_data["tests_repo"])
        except Exception:  # noqa: BLE001
            safe_tests_repo_url = ""
            extract_repo_from_link = ""
        else:
            safe_tests_repo_url = f"https://github.com/{user}/{repo}"
            extract_repo_from_link = f"{user}/{repo}"

    registration_time = user_data.get("registration_time")
    registration_time_label = (
        format_date(registration_time) if registration_time else "Unknown"
    )

    return {
        "user": user_data,
        "limit": request.userdb.get_machine_limit(user_name),
        "hours": hours,
        "profile": profile,
        "safe_tests_repo_url": safe_tests_repo_url,
        "extract_repo_from_link": extract_repo_from_link,
        "form_action": request.url,
        "registration_time_label": registration_time_label,
        "blocked": bool(user_data.get("blocked", False)),
    }


# === Contributors ===
_CONTRIBUTORS_SORT_MAP = {
    "cpu_hours": ("cpu_hours", True),
    "username": ("username", False),
    "last_updated": ("last_updated", True),
    "games_per_hour": ("games_per_hour", True),
    "games": ("games", True),
    "tests": ("tests", True),
    "tests_repo": ("tests_repo", False),
}
_CONTRIBUTORS_DEFAULT_SORT = "cpu_hours"
_CONTRIBUTORS_PAGE_SIZE = CONTRIBUTORS_PAGE_SIZE
_CONTRIBUTORS_MAX_ALL = CONTRIBUTORS_MAX_ALL


def _contributors_sort_value(user: dict[str, Any], sort_key: str) -> Any:  # noqa: ANN401
    if sort_key == "username":
        return str(user.get("username", "")).lower()
    if sort_key == "tests_repo":
        return str(user.get("tests_repo", "")).lower()
    if sort_key == "last_updated":
        value = user.get("last_updated")
        if isinstance(value, datetime):
            return value.timestamp()
        return 0
    try:
        return int(user.get(sort_key, 0))
    except TypeError, ValueError:
        return 0


def _contributors_common(  # noqa: C901, PLR0912, PLR0915
    request: _ViewContext,
    *,
    collection: Any,  # noqa: ANN401
    is_monthly: bool,
) -> dict[str, Any] | RedirectResponse | Response:
    page_idx = _page_index_from_params(request.params)

    search = request.params.get("search", "").strip()
    sort_param = request.params.get("sort", "").strip().lower()
    order_param = request.params.get("order", "").strip().lower()
    view_param = request.params.get("view", "").strip().lower()
    highlight = request.params.get("highlight", "").strip()

    if sort_param not in _CONTRIBUTORS_SORT_MAP:
        sort_param = _CONTRIBUTORS_DEFAULT_SORT
    sort_key, default_reverse = _CONTRIBUTORS_SORT_MAP[sort_param]

    order_param, reverse = _normalize_sort_order(
        order_param,
        default_reverse=default_reverse,
    )

    view_param = _normalize_view_mode(view_param)

    all_users_unfiltered = list(collection.find())
    users_list = list(all_users_unfiltered)

    # Stable two-pass sort: enforce username asc tie-breaker, then primary key.
    users_list.sort(key=lambda u: str(u.get("username", "")).lower())
    users_list.sort(
        key=lambda u: _contributors_sort_value(u, sort_key),
        reverse=reverse,
    )

    num_users = len(users_list)

    findme = request.params.get("findme", "").strip()
    username = request.authenticated_userid
    target_username = ""
    if findme and username:
        target_username = username
    elif search:
        search_lower = search.lower()
        exact_match = next(
            (
                user.get("username", "")
                for user in users_list
                if str(user.get("username", "")).lower() == search_lower
            ),
            "",
        )
        if exact_match:
            target_username = exact_match
        else:
            target_username = next(
                (
                    user.get("username", "")
                    for user in users_list
                    if search_lower in str(user.get("username", "")).lower()
                ),
                "",
            )

    if target_username:
        user_rank = next(
            (
                idx
                for idx, user in enumerate(users_list, start=1)
                if user.get("username") == target_username
            ),
            None,
        )
        if user_rank is not None:
            target_page = str((user_rank - 1) // _CONTRIBUTORS_PAGE_SIZE + 1)
            current_page = str(page_idx + 1)
            highlight_matches = highlight.lower() == target_username.lower()
            if view_param == "all":
                # In full view there is no page navigation, so a matching highlight
                # is the only signal that the jump/go-to has already been applied.
                already_on_target = highlight_matches
            else:
                already_on_target = current_page == target_page and highlight_matches
            if not already_on_target:
                params = {
                    "sort": sort_param,
                    "order": order_param,
                    "highlight": target_username,
                    "view": view_param,
                }
                # Keep findme sticky across redirect hops so a non-empty search
                # query cannot override jump-to-my-rank on the follow-up request.
                if findme:
                    params["findme"] = "1"
                if view_param == "paged":
                    params["page"] = target_page
                return RedirectResponse(
                    url=f"{request.path}?{urlencode(params)}#me",
                    status_code=302,
                )

    for idx, user in enumerate(users_list, start=1):
        user["_rank"] = idx

    if highlight and not any(
        str(user.get("username", "")).lower() == highlight.lower()
        for user in users_list
    ):
        highlight = ""

    if view_param == "all":
        users_page = users_list[:_CONTRIBUTORS_MAX_ALL]
        is_truncated = num_users > _CONTRIBUTORS_MAX_ALL
        if is_truncated:
            logger.info(
                "contributors view=all truncated at %d rows (total=%d, monthly=%s)",
                _CONTRIBUTORS_MAX_ALL,
                num_users,
                is_monthly,
            )
    else:
        start = page_idx * _CONTRIBUTORS_PAGE_SIZE
        end = (page_idx + 1) * _CONTRIBUTORS_PAGE_SIZE
        users_page = users_list[start:end]
        is_truncated = False

    is_approver = request.has_permission("approve_run")
    rows = build_contributors_rows(users_page, is_approver=is_approver)

    pages = []
    if view_param == "paged":
        default_order = "desc" if default_reverse else "asc"
        query_params = _build_query_string(
            [
                (
                    "sort",
                    sort_param if sort_param != _CONTRIBUTORS_DEFAULT_SORT else None,
                ),
                ("order", order_param if order_param != default_order else None),
            ],
        )
        pages = pagination(page_idx, num_users, _CONTRIBUTORS_PAGE_SIZE, query_params)

    context = {
        "is_monthly": is_monthly,
        "monthly_suffix": " - Top Month" if is_monthly else "",
        "summary": build_contributors_summary(all_users_unfiltered),
        "users": rows,
        "pages": pages,
        "is_approver": is_approver,
        "search": search,
        "sort": sort_param,
        "order": order_param,
        "view": view_param,
        "highlight": highlight,
        "is_truncated": is_truncated,
        "num_users": num_users,
        "max_all": _CONTRIBUTORS_MAX_ALL,
    }
    return _render_hx_or_context(
        request,
        "contributors_content_fragment.html.j2",
        context,
    )


def contributors(request: _ViewContext) -> dict[str, Any] | RedirectResponse | Response:
    return _contributors_common(
        request,
        collection=request.userdb.user_cache,
        is_monthly=False,
    )


def contributors_monthly(
    request: _ViewContext,
) -> dict[str, Any] | RedirectResponse | Response:
    return _contributors_common(
        request,
        collection=request.userdb.top_month,
        is_monthly=True,
    )


# === Homepage And Run Lists ===
def tests_machines(request: _ViewContext) -> dict[str, Any] | Response:
    return _tests_machines_impl(request)


def _build_toggle_states(
    request: _ViewContext,
    toggle_names: list[str],
) -> dict[str, str]:
    return {name: request.cookies.get(f"{name}_state", "Show") for name in toggle_names}


def _is_tests_run_tables_live_request(request: _ViewContext) -> bool:
    return request.params.get("live", "") == "run_tables"


def _tests_run_tables_query_pairs(
    request: _ViewContext,
    *,
    include_live: bool,
) -> list[tuple[str, str]]:
    query_pairs = [
        (key, value)
        for key, value in request.query_params.multi_items()
        if key not in {"live", "username"}
    ]
    if include_live:
        query_pairs.append(("live", "run_tables"))
    return query_pairs


def _tests_run_tables_url(
    request: _ViewContext,
    *,
    include_live: bool,
) -> str:
    query_string = _build_query_string(
        _tests_run_tables_query_pairs(request, include_live=include_live),
        leading="?",
    )
    return f"{request.path}{query_string}"


def _render_tests_run_tables_live_fragment(
    request: _ViewContext,
) -> Response | RedirectResponse | None:
    if not _is_tests_run_tables_live_request(request):
        return None

    if not _is_hx_request(request):
        return RedirectResponse(
            url=_tests_run_tables_url(request, include_live=False),
            status_code=302,
        )

    context = _build_tests_run_tables_fragment_context(request)
    if isinstance(context, RedirectResponse):
        return context

    return render_template_to_response(
        request=request.raw_request,
        template_name="tests_run_tables_fragment.html.j2",
        context=build_template_context(request.raw_request, request.session, context),
        status_code=int(request.response_status or 200),
    )


def _build_run_tables_context(  # noqa: PLR0913
    request: _ViewContext,
    *,
    runs: dict[str, list[dict[str, Any]]] | None,
    failed_runs: list[dict[str, Any]],
    finished_runs: list[dict[str, Any]],
    num_finished_runs: int,
    finished_runs_pages: list[dict[str, object]],
    page_idx: int,
    username: str = "",
) -> dict[str, Any]:
    runs = runs or {"pending": [], "active": []}
    pending_runs = [r for r in runs.get("pending", []) if not r.get("approved")]
    paused_runs = [r for r in runs.get("pending", []) if r.get("approved")]
    active_runs = list(runs.get("active", []))
    active_run_filters = (
        _build_active_run_filter_context(request, active_runs)
        if page_idx == 0 and not username
        else None
    )
    active_runs_for_display = (
        active_run_filters["ordered_runs"]
        if active_run_filters is not None
        else active_runs
    )
    prefix = run_tables_prefix(username)
    toggle_names = [prefix + "finished"]
    if page_idx == 0:
        toggle_names = [
            prefix + "pending",
            prefix + "paused",
            prefix + "failed",
            prefix + "active",
            prefix + "finished",
        ]
    toggle_states = _build_toggle_states(request, toggle_names)
    finished_title_text = (
        f"{username + ' - ' if username else ''}Finished Tests"
        f" - page {page_idx + 1} | Stockfish Testing"
    )

    return {
        "pending_approval_runs": build_run_table_rows(
            pending_runs,
            allow_github_api_calls=False,
        ),
        "paused_runs": build_run_table_rows(
            paused_runs,
            allow_github_api_calls=False,
        ),
        "failed_runs": build_run_table_rows(
            failed_runs,
            allow_github_api_calls=False,
        ),
        "active_runs": build_run_table_rows(
            active_runs_for_display,
            allow_github_api_calls=False,
        ),
        "active_count_text": (
            active_run_filters["count_text"]
            if active_run_filters is not None
            else f"Active - {len(active_runs)} tests"
        ),
        "active_run_filters": active_run_filters,
        "finished_runs": build_run_table_rows(
            finished_runs,
            allow_github_api_calls=False,
        ),
        "num_finished_runs": num_finished_runs,
        "finished_runs_pages": finished_runs_pages,
        "page_idx": page_idx,
        "prefix": prefix,
        "toggle_states": toggle_states,
        "finished_title_text": finished_title_text,
        "live_url": (
            _tests_run_tables_url(request, include_live=True) if page_idx == 0 else None
        ),
        "show_gauge": False,
    }


def tests_finished(request: _ViewContext) -> dict[str, Any] | Response:
    context = get_paginated_finished_runs(request)
    if isinstance(context, RedirectResponse):
        return context
    page_idx = context["page_idx"]
    title_suffix = context["title_suffix"]
    search_mode = context["search_mode"]
    if search_mode:
        title_text = f"Search Finished Tests - page {page_idx + 1} | Stockfish Testing"
    else:
        title_text = (
            f"Finished Tests{title_suffix} - page {page_idx + 1} | Stockfish Testing"
        )
    context_out = {
        **context,
        "query_params": request.query_params,
        "finished_runs": build_run_table_rows(
            context["finished_runs"],
            allow_github_api_calls=False,
        ),
        "failed_runs": build_run_table_rows(
            context["failed_runs"],
            allow_github_api_calls=False,
        ),
        "title": title_suffix,
        "title_text": title_text,
        "show_gauge": False,
    }

    return _render_hx_or_context(
        request,
        "tests_finished_results_fragment.html.j2",
        context_out,
        extra_context={"is_hx": True},
    )


def tests_user(request: _ViewContext) -> dict[str, Any] | Response:
    _append_no_store_headers(request)
    username = request.matchdict.get("username", "")
    user_data = request.userdb.get_user(username)
    if user_data is None:
        raise StarletteHTTPException(status_code=404)
    is_approver = request.has_permission("approve_run")
    page_idx = _page_index_from_params(request.params)
    if page_idx == 0:
        live_fragment = _render_tests_run_tables_live_fragment(request)
        if live_fragment is not None:
            return live_fragment
    finished_context = get_paginated_finished_runs(request)
    if isinstance(finished_context, RedirectResponse):
        return finished_context
    response = {
        **finished_context,
        "username": username,
        "is_approver": is_approver,
    }
    if finished_context["page_idx"] == 0:
        runs = request.rundb.aggregate_unfinished_runs(username=username)[0]
        response["run_tables_ctx"] = _build_run_tables_context(
            request,
            runs=runs,
            failed_runs=finished_context["failed_runs"],
            finished_runs=finished_context["finished_runs"],
            num_finished_runs=finished_context["num_finished_runs"],
            finished_runs_pages=finished_context["finished_runs_pages"],
            page_idx=finished_context["page_idx"],
            username=username,
        )
    else:
        response["run_tables_ctx"] = _build_run_tables_context(
            request,
            runs=None,
            failed_runs=finished_context["failed_runs"],
            finished_runs=finished_context["finished_runs"],
            num_finished_runs=finished_context["num_finished_runs"],
            finished_runs_pages=finished_context["finished_runs_pages"],
            page_idx=finished_context["page_idx"],
            username=username,
        )
    # page 2 and beyond only show finished test results
    return _render_hx_or_context(
        request,
        "tests_user_content_fragment.html.j2",
        response,
    )


def homepage_results(request: _ViewContext) -> dict[str, Any] | RedirectResponse:
    # Get updated results for unfinished runs + finished runs

    (
        runs,
        pending_hours,
        cores,
        nps,
        games_per_minute,
        machines_count,
    ) = request.rundb.aggregate_unfinished_runs()
    finished_context = get_paginated_finished_runs(request)
    if isinstance(finished_context, RedirectResponse):
        return finished_context
    run_tables_ctx = _build_run_tables_context(
        request,
        runs=runs,
        failed_runs=finished_context["failed_runs"],
        finished_runs=finished_context["finished_runs"],
        num_finished_runs=finished_context["num_finished_runs"],
        finished_runs_pages=finished_context["finished_runs_pages"],
        page_idx=finished_context["page_idx"],
    )
    return {
        **finished_context,
        "runs": runs,
        "run_tables_ctx": run_tables_ctx,
        "machines_count": machines_count,
        "pending_hours": f"{pending_hours:.1f}",
        "cores": cores,
        "nps": nps,
        "nps_m": f"{nps / 1000000:.0f}M",
        "games_per_minute": int(games_per_minute),
        "height": f"{machines_count * 37}px",
        "min_height": "37px",
        "max_height": "34.7vh",
    }


def tests(request: _ViewContext) -> dict[str, Any] | Response:
    # The homepage mixes user-specific state with frequently refreshed content,
    # so intermediary caches must not store it.
    _append_no_store_headers(request)
    page_param = request.params.get("page", "")
    if page_param.isdigit() and int(page_param) > 1:
        # page 2 and beyond only show finished test results
        finished_context = get_paginated_finished_runs(request)
        if isinstance(finished_context, RedirectResponse):
            return finished_context
        return {
            **finished_context,
            "run_tables_ctx": _build_run_tables_context(
                request,
                runs=None,
                failed_runs=finished_context["failed_runs"],
                finished_runs=finished_context["finished_runs"],
                num_finished_runs=finished_context["num_finished_runs"],
                finished_runs_pages=finished_context["finished_runs_pages"],
                page_idx=finished_context["page_idx"],
            ),
        }

    live_fragment = _render_tests_run_tables_live_fragment(request)
    if live_fragment is not None:
        return live_fragment

    last_tests = homepage_results(request)
    if isinstance(last_tests, RedirectResponse):
        return last_tests

    authenticated_user = request.authenticated_userid

    machines_sort = request.cookies.get("machines_sort", "").strip().lower()
    if machines_sort not in _MACHINES_SORT_MAP:
        machines_sort = _MACHINES_DEFAULT_SORT

    _, machines_default_reverse = _MACHINES_SORT_MAP[machines_sort]
    machines_order = request.cookies.get("machines_order", "").strip().lower()
    if machines_order not in {"asc", "desc"}:
        machines_order = "desc" if machines_default_reverse else "asc"

    machines_q = unquote(request.cookies.get("machines_q", ""))

    machines_page_raw = request.cookies.get("machines_page", "")
    if machines_page_raw.isdigit() and int(machines_page_raw) >= 1:
        machines_page = int(machines_page_raw)
    else:
        machines_page = 1

    machines_my_workers = _is_truthy_param(
        request.cookies.get("machines_my_workers", ""),
    )
    if not authenticated_user:
        machines_my_workers = False

    machine_filters = _machine_filter_state(
        request.cookies,
        authenticated_username=authenticated_user,
        use_cookies=True,
        query_key="machines_q",
        my_workers_key="machines_my_workers",
    )
    machines_filters_active = machine_filters["filters_active"]
    if machines_filters_active:
        machines_filtered_count = _filtered_machine_count(
            request,
            query_filter=machine_filters["query_filter"],
            my_workers=machine_filters["my_workers"],
            authenticated_username=authenticated_user,
        )
    else:
        machines_filtered_count = last_tests["machines_count"]
    workers_count = _workers_count_label(
        last_tests["machines_count"],
        query_filter=machine_filters["query_filter"],
        my_workers=machine_filters["my_workers"],
        filtered_count=machines_filtered_count,
    )

    return {
        **last_tests,
        "machines_shown": request.cookies.get("machines_state") == "Hide",
        "workers_count_text": workers_count,
        "machines_sort": machines_sort,
        "machines_order": machines_order,
        "machines_q": machines_q,
        "machines_page": machines_page,
        "machines_my_workers": machines_my_workers,
        "has_authenticated_user": bool(authenticated_user),
    }


# === Run Mutation ===


# === Run Creation ===
def tests_run(request: _ViewContext) -> dict[str, Any] | RedirectResponse:
    user_id = ensure_logged_in(request)
    if isinstance(user_id, RedirectResponse):
        return user_id

    if request.method == "POST":
        try:
            data = validate_form(request)
            if is_sprt_ltc_data(data):
                data["info"] = "LTC: " + data["info"]
            run_id = request.rundb.new_run(**data)
            run = request.rundb.get_run(run_id)
            request.actiondb.new_run(
                username=user_id,
                run=run,
                message=new_run_message(request, run),
            )
            request.session.flash(
                "The test was submitted to the queue. Please wait for approval.",
            )
            return RedirectResponse(
                url="/tests/view/" + str(run_id) + "?follow=1",
                status_code=302,
            )
        except Exception as e:  # noqa: BLE001
            request.session.flash(str(e), "error")

    run_args = {}
    if "id" in request.params:
        run = request.rundb.get_run(request.params["id"])
        if run is None:
            raise StarletteHTTPException(status_code=404)
        run_args = copy.deepcopy(run["args"])
        if "spsa" in run_args:
            # needs deepcopy
            run_args["spsa"]["A"] = (
                round(1000 * 2 * run_args["spsa"]["A"] / run_args["num_games"]) / 1000
            )

    username = request.authenticated_userid
    u = request.userdb.get_user(username)

    # Make sure that a newly committed book can be used immediately
    request.rundb.update_books()
    # Make sure that when the test is viewed after submission,
    # official_master_sha is up to date
    gh.update_official_master_sha()

    test_book = "UHO_Lichess_4852_v1.epd"
    pt_book = "UHO_Lichess_4852_v1.epd"
    master_info = get_master_info(ignore_rate_limit=True)
    setup = tests_run_setup(run_args, master_info, request.rundb.pt_info, test_book)
    tests_repo_value = run_args.get("tests_repo", u.get("tests_repo", ""))
    new_tag_value = run_args.get("new_tag", "")
    new_signature_value = run_args.get("new_signature", "")
    new_options_value = run_args.get("new_options", "Hash=16")
    base_options_value = run_args.get("base_options", "Hash=16")
    info_value = run_args.get("info", "")

    return {
        "args": run_args,
        "is_rerun": len(run_args) > 0,
        "rescheduled_from": request.params.get("id", None),
        "form_action": request.url,
        "tests_repo_value": tests_repo_value,
        "new_tag_value": new_tag_value,
        "new_signature_value": new_signature_value,
        "new_options_value": new_options_value,
        "base_options_value": base_options_value,
        "info_value": info_value,
        "test_book": test_book,
        "pt_book": pt_book,
        "master_info": master_info,
        "valid_books": request.rundb.books.keys(),
        "pt_info": request.rundb.pt_info,
        "setup": setup,
        "supported_arches": supported_arches,
        "supported_compilers": supported_compilers,
    }


# === Run Administration ===
def tests_modify(request: _ViewContext) -> RedirectResponse | dict[str, Any]:  # noqa: C901, PLR0912
    userid = ensure_logged_in(request)
    if isinstance(userid, RedirectResponse):
        return userid

    run = request.rundb.get_run(request.POST["run"])
    if run is None:
        request.session.flash("No run with this id", "error")
        return home(request)

    validation_error = validate_modify(request, run)
    if validation_error is not None:
        return validation_error

    if not can_modify_run(request, run):
        request.session.flash("Unable to modify another user's run!", "error")
        return home(request)

    run_id = run["_id"]
    is_approver = request.has_permission("approve_run")
    was_approved = run["approved"]
    if (
        not is_approver
        and was_approved
        and (
            (int(request.POST["throughput"]) > max(run["args"]["throughput"], 100))
            or (int(request.POST["priority"]) > max(run["args"]["priority"], 0))
            or run["failed"]
        )
    ):
        request.actiondb.approve_run(username=userid, run=run, message="unapproved")
        with request.rundb.active_run_lock(run_id):
            run["approved"] = False
            run["approver"] = ""

    before = del_tasks(run)
    with request.rundb.active_run_lock(run_id):
        run["args"]["num_games"] = int(request.POST["num-games"])
        run["args"]["priority"] = int(request.POST["priority"])
        run["args"]["throughput"] = int(request.POST["throughput"])
        run["args"]["auto_purge"] = bool(request.POST.get("auto_purge"))
        if (
            is_same_user(request, run)
            and "info" in request.POST
            and request.POST["info"].strip() != ""
        ):
            run["args"]["info"] = request.POST["info"].strip()

    if is_undecided(run):
        request.rundb.set_active_run(run)

    after = del_tasks(run)
    message = []

    for k in ("priority", "num_games", "throughput", "auto_purge"):
        try:
            before_ = before["args"][k]
            after_ = after["args"][k]
        except KeyError:
            pass
        else:
            if before_ != after_:
                message.append(
                    "{} changed from {} to {}".format(
                        k.replace("_", "-"),
                        before_,
                        after_,
                    ),
                )

    message = "modify: " + ", ".join(message)
    request.actiondb.modify_run(
        username=request.authenticated_userid,
        run=before,
        message=message,
    )
    if run["approved"]:
        request.session.flash("The test was successfully modified!")
    elif was_approved:
        request.session.flash(
            "The test was successfully modified but it will have to be reapproved...",
            "warning",
        )
    else:
        request.session.flash(
            "The test was successfully modified. Please wait for approval.",
        )
    return home(request)


def tests_stop(request: _ViewContext) -> RedirectResponse | dict[str, Any]:
    if not request.authenticated_userid:
        request.session.flash("Please login")
        return RedirectResponse(url="/login", status_code=302)
    if "run-id" in request.POST:
        run = request.rundb.get_run(request.POST["run-id"])
        if not can_modify_run(request, run):
            request.session.flash("Unable to modify another users run!", "error")
            return home(request)

        request.rundb.stop_run(request.POST["run-id"])
        request.actiondb.stop_run(
            username=request.authenticated_userid,
            run=run,
            message="User stop",
        )
        request.session.flash("Stopped run")
    return home(request)


def tests_approve(request: _ViewContext) -> RedirectResponse:
    if not request.authenticated_userid:
        return RedirectResponse(url="/login", status_code=302)
    if not request.has_permission("approve_run"):
        request.session.flash("Please login as approver")
        return RedirectResponse(url="/login", status_code=302)
    username = request.authenticated_userid
    run_id = request.POST["run-id"]
    run, message = request.rundb.approve_run(run_id, username)
    if run is None:
        request.session.flash(message, "error")
    else:
        try:
            update_nets(request, run)
        except Exception as e:  # noqa: BLE001
            request.session.flash(str(e), "error")
        request.actiondb.approve_run(username=username, run=run, message="approved")
        if message:
            request.session.flash(message)
    return home(request)


def tests_purge(request: _ViewContext) -> RedirectResponse | dict[str, Any]:
    run = request.rundb.get_run(request.POST["run-id"])
    if not request.has_permission("approve_run") and not is_same_user(request, run):
        request.session.flash(
            "Only approvers or the submitting user can purge the run.",
        )
        return RedirectResponse(url="/login", status_code=302)

    # More relaxed conditions than with auto purge.
    message = request.rundb.purge_run(run, p=0.01, res=4.5)

    username = request.authenticated_userid
    request.actiondb.purge_run(
        username=username,
        run=run,
        message=(
            f"Manual purge (not performed): {message}" if message else "Manual purge"
        ),
    )

    if message != "":
        request.session.flash(message)
        return home(request)

    request.session.flash("Purged run")
    return home(request)


def tests_delete(request: _ViewContext) -> RedirectResponse | dict[str, Any]:
    if not request.authenticated_userid:
        request.session.flash("Please login")
        return RedirectResponse(url="/login", status_code=302)
    if "run-id" in request.POST:
        run = request.rundb.get_run(request.POST["run-id"])
        if not can_modify_run(request, run):
            request.session.flash("Unable to modify another users run!", "error")
            return home(request)

        request.rundb.set_inactive_run(run)
        run["deleted"] = True
        try:
            validate(runs_schema, run, "run")
        except ValidationError as e:
            message = (
                f"The run object {request.POST['run-id']} does not validate: {e!s}"
            )
            logger.warning(message)
            if "version" in run and run["version"] >= RUN_VERSION:
                request.actiondb.log_message(
                    username="fishtest.system",
                    message=message,
                )
        request.rundb.buffer(run, priority=Prio.SAVE_NOW)

        request.actiondb.delete_run(
            username=request.authenticated_userid,
            run=run,
        )
        request.session.flash("Deleted run")
    return home(request)


# === Run Detail ===
def get_page_title(run: dict[str, Any]) -> str:
    if run["args"].get("sprt"):
        page_title = "SPRT {} vs {}".format(
            run["args"]["new_tag"],
            run["args"]["base_tag"],
        )
    elif run["args"].get("spsa"):
        page_title = "SPSA {}".format(run["args"]["new_tag"])
    else:
        page_title = "{} games - {} vs {}".format(
            run["args"]["num_games"],
            run["args"]["new_tag"],
            run["args"]["base_tag"],
        )
    return page_title


def _build_live_elo_context(run: dict[str, Any]) -> dict[str, Any]:
    """Compute SPRT analytics and return template context for gauges + details."""
    run_status_label = _classify_run_status(run)
    if run_status_label == "failed":
        run_status_label = "finished"

    results = run["results"]
    sprt = run["args"]["sprt"]
    elo_model = sprt.get("elo_model", "BayesElo")
    a = fishtest.stats.stat_util.SPRT_elo(
        results,
        alpha=sprt["alpha"],
        beta=sprt["beta"],
        elo0=sprt["elo0"],
        elo1=sprt["elo1"],
        elo_model=elo_model,
    )
    WLD = [results["wins"], results["losses"], results["draws"]]  # noqa: N806
    games = sum(WLD)
    pentanomial = results.get("pentanomial", [])
    return {
        "run": run,
        "run_status_label": run_status_label,
        "elo_raw": a["elo"],
        "ci_lower_raw": a["ci"][0],
        "ci_upper_raw": a["ci"][1],
        "LLR_raw": a["LLR"],
        "LOS_raw": 100 * a["LOS"],
        "a_raw": a["a"],
        "b_raw": a["b"],
        "elo_value": round(a["elo"], 2),
        "ci_lower": round(a["ci"][0], 2),
        "ci_upper": round(a["ci"][1], 2),
        "LLR": round(a["LLR"], 2),
        "LOS": round(100 * a["LOS"], 1),
        "a": round(a["a"], 2),
        "b": round(a["b"], 2),
        "W": WLD[0],
        "L": WLD[1],
        "D": WLD[2],
        "games": games,
        "w_pct": round((100 * WLD[0]) / (games + 0.001), 1),
        "l_pct": round((100 * WLD[1]) / (games + 0.001), 1),
        "d_pct": round((100 * WLD[2]) / (games + 0.001), 1),
        "pentanomial": pentanomial[:5],
        "sprt_state": sprt.get("state", ""),
        "elo_model": elo_model,
        "elo0": sprt["elo0"],
        "elo1": sprt["elo1"],
        "alpha": sprt["alpha"],
        "beta": sprt["beta"],
    }


def _classify_run_status(run: dict[str, Any]) -> str:
    if run.get("finished", False):
        return "failed" if run.get("failed") else "finished"
    if run.get("workers", 0) > 0:
        return "active"
    return "paused" if run.get("approved") else "pending"


def _build_tests_view_status_context(run: dict[str, Any]) -> dict[str, str]:
    active_workers = 0
    active_cores = 0
    for task in run["tasks"]:
        if task["active"]:
            active_workers += 1
            active_cores += task["worker_info"]["concurrency"]

    return {
        "run_status_label": _classify_run_status(run),
        "tasks_totals": "({} active worker{} with {} core{})".format(
            active_workers,
            ("s" if active_workers != 1 else ""),
            active_cores,
            ("s" if active_cores != 1 else ""),
        ),
    }


def _build_tests_run_tables_fragment_context(
    request: _ViewContext,
) -> _TestsRunTablesFragmentContext | RedirectResponse:
    username = request.matchdict.get("username", "")

    (
        runs,
        pending_hours,
        cores,
        nps,
        games_per_minute,
        machines_count,
    ) = request.rundb.aggregate_unfinished_runs(username=username or None)

    pending_all = list(runs.get("pending", []))
    active_runs = list(runs.get("active", []))
    pending_runs = [r for r in pending_all if not r.get("approved")]
    paused_runs = [r for r in pending_all if r.get("approved")]
    active_run_filters = (
        _build_active_run_filter_context(request, active_runs) if not username else None
    )
    active_runs_for_display = (
        active_run_filters["ordered_runs"]
        if active_run_filters is not None
        else active_runs
    )

    allow_github_api_calls = request.has_permission("approve_run")

    finished_context = get_paginated_finished_runs(request, username=username)
    if isinstance(finished_context, RedirectResponse):
        return finished_context
    failed_runs = finished_context["failed_runs"]
    finished_runs = finished_context["finished_runs"]

    panels: list[_BatchPanel] = [
        {
            "tbody_id": "pending-tbody",
            "rows": build_run_table_rows(
                pending_runs,
                allow_github_api_calls=allow_github_api_calls,
            ),
            "show_delete": True,
            "empty_text": "No tests pending approval",
        },
        {
            "tbody_id": "paused-tbody",
            "rows": build_run_table_rows(
                paused_runs,
                allow_github_api_calls=allow_github_api_calls,
            ),
            "show_delete": True,
            "empty_text": "No paused tests",
        },
        {
            "tbody_id": "failed-tbody",
            "rows": build_run_table_rows(
                failed_runs,
                allow_github_api_calls=allow_github_api_calls,
            ),
            "show_delete": True,
            "empty_text": "No failed tests on this page",
        },
        {
            "tbody_id": "active-tbody",
            "rows": build_run_table_rows(
                active_runs_for_display,
                allow_github_api_calls=allow_github_api_calls,
            ),
            "show_delete": False,
            "empty_text": "No active tests",
        },
        {
            "tbody_id": "finished-tbody",
            "rows": build_run_table_rows(
                finished_runs,
                allow_github_api_calls=allow_github_api_calls,
            ),
            "show_delete": False,
            "empty_text": "",
        },
    ]

    count_updates: list[_CountUpdate] = [
        {
            "id": "pending-count",
            "text": f"Pending approval - {len(pending_runs)} tests",
        },
        {
            "id": "paused-count",
            "text": f"Paused - {len(paused_runs)} tests",
        },
        {
            "id": "active-count",
            "text": (
                active_run_filters["count_text"]
                if active_run_filters is not None
                else f"Active - {len(active_runs)} tests"
            ),
        },
        {
            "id": "failed-count",
            "text": f"Failed - {len(failed_runs)} tests",
        },
        {
            "id": "finished-count",
            "text": f"Finished - {finished_context['num_finished_runs']} tests",
        },
    ]

    if not (pending_runs or paused_runs or active_runs):
        request.response_status = 286

    machine_filters = _machine_filter_state(
        request.cookies,
        authenticated_username=request.authenticated_userid,
        use_cookies=True,
        query_key="machines_q",
        my_workers_key="machines_my_workers",
    )
    filters_active = machine_filters["filters_active"]

    result: _TestsRunTablesFragmentContext = {
        "panels": panels,
        "count_updates": count_updates,
    }

    # workers-count target exists on homepage only.
    if not username:
        filtered_count = (
            _filtered_machine_count(
                request,
                query_filter=machine_filters["query_filter"],
                my_workers=machine_filters["my_workers"],
                authenticated_username=request.authenticated_userid,
            )
            if filters_active
            else machines_count
        )
        result["machines_count"] = machines_count
        workers_count = _workers_count_label(
            machines_count,
            query_filter=machine_filters["query_filter"],
            my_workers=machine_filters["my_workers"],
            filtered_count=filtered_count,
        )
        result["workers_count_text"] = workers_count

    # Include stats OOB updates for the homepage (no username filter).
    if not username:
        result["stats"] = {
            "pending_hours": f"{pending_hours:.1f}",
            "cores": cores,
            "nps_m": f"{nps / 1000000:.0f}M",
            "games_per_minute": int(games_per_minute),
        }

    return result


def tests_live_elo(request: _ViewContext) -> dict[str, Any]:
    run = request.rundb.get_run(request.matchdict["id"])
    if run is None or "sprt" not in run["args"]:
        raise StarletteHTTPException(status_code=404)
    context = _build_live_elo_context(run)
    context["page_title"] = get_page_title(run)
    return context


def live_elo_update(request: _ViewContext) -> dict[str, Any]:
    run = request.rundb.get_run(request.matchdict["id"])
    if run is None or "sprt" not in run["args"]:
        raise StarletteHTTPException(status_code=404)

    context = _build_live_elo_context(run)
    if context["sprt_state"]:
        request.response_status = 286
    return context


def tests_stats(request: _ViewContext) -> dict[str, Any] | Response:
    run = request.rundb.get_run(request.matchdict["id"])
    if run is None:
        raise StarletteHTTPException(status_code=404)

    context = {
        "run": run,
        "page_title": get_page_title(run),
        "stats": build_tests_stats_context(run),
    }

    if _is_hx_request(request):
        actual = _classify_run_status(run)
        if actual in {"finished", "failed"}:
            response = _render_hx_fragment(
                request,
                "tests_stats_content_fragment.html.j2",
                context,
            )
            if response is not None:
                response.status_code = 286
                return response
        elif actual != "active":
            request.response_status = 204
            return context

        response = _render_hx_fragment(
            request,
            "tests_stats_content_fragment.html.j2",
            context,
        )
        return response or context

    return context


_TASKS_SORT_MAP: dict[str, tuple[str, bool]] = {
    "idx": ("task_id", True),
    "worker": ("worker_label", False),
    "info": ("info_label", False),
    "last_updated": ("last_updated_sort", True),
    "played": ("played_sort", True),
    "wins": ("wins", True),
    "losses": ("losses", True),
    "draws": ("draws", True),
    "pentanomial": ("pentanomial_sort", True),
    "crashes": ("crashes", True),
    "time": ("time_losses", True),
    "residual": ("residual_sort", True),
}
_TASKS_DEFAULT_SORT = "idx"
_TASKS_PAGE_SIZE = TASKS_PAGE_SIZE
_TASKS_MAX_ALL = TASKS_MAX_ALL


def _tasks_cookie_value(request: _ViewContext, name: str) -> str:
    return unquote(str(request.cookies.get(name, ""))).strip()


def _parse_show_task_param(request: _ViewContext) -> int:
    try:
        show_task = int(request.params.get("show_task", -1))
    except ValueError:
        return -1
    return max(show_task, -1)


def _task_filter_value(
    request: _ViewContext,
    *,
    param_name: str,
    cookie_name: str,
) -> str:
    raw_value = request.params.get(param_name)
    if raw_value is None:
        raw_value = _tasks_cookie_value(request, cookie_name)
    return str(raw_value).strip()


def _filter_task_rows(
    tasks: list[dict[str, Any]],
    *,
    search_filter: str,
) -> list[dict[str, Any]]:
    filtered_tasks = tasks

    if search_filter:
        search_folded = search_filter.casefold()
        filtered_tasks = [
            task
            for task in filtered_tasks
            if search_folded in str(task.get("worker_label", "")).casefold()
            or search_folded
            in str(
                task.get("info_filter_text", task.get("info_label", "")),
            )
        ]

    return filtered_tasks


def _task_table_state(
    request: _ViewContext,
    *,
    run: dict[str, Any],
    show_task: int,
    chi2: float,
) -> dict[str, Any]:
    approver = request.has_permission("approve_run")
    tasks, show_pentanomial, show_residual = build_tasks_rows(
        run,
        show_task=show_task,
        chi2=chi2,
        is_approver=approver,
    )

    raw_sort = request.params.get("sort")
    if raw_sort is None:
        raw_sort = _tasks_cookie_value(request, "tasks_sort")
    sort_param = str(raw_sort).strip().lower() or _TASKS_DEFAULT_SORT
    if sort_param not in _TASKS_SORT_MAP:
        sort_param = _TASKS_DEFAULT_SORT

    sort_key, default_reverse = _TASKS_SORT_MAP[sort_param]
    order_param, reverse = _normalize_sort_order(
        request.params.get("order")
        if request.params.get("order") is not None
        else _tasks_cookie_value(request, "tasks_order"),
        default_reverse=default_reverse,
    )

    raw_view = request.params.get("view")
    if raw_view is None:
        raw_view = _tasks_cookie_value(request, "tasks_view")
    view_param = _normalize_view_mode(raw_view or "paged")

    query_filter = _task_filter_value(
        request,
        param_name="q",
        cookie_name="tasks_q",
    )

    tasks.sort(
        key=lambda row: (
            _tasks_sort_value(row, sort_key),
            row.get("task_id", 0),
        ),
        reverse=reverse,
    )

    tasks = _filter_task_rows(
        tasks,
        search_filter=query_filter,
    )

    valid_show_task = (
        show_task if any(task.get("task_id") == show_task for task in tasks) else -1
    )
    page_idx = _page_index_from_params(request.params)
    num_tasks = len(tasks)
    is_truncated = False

    if view_param == "all":
        if num_tasks > _TASKS_MAX_ALL:
            tasks = tasks[:_TASKS_MAX_ALL]
            is_truncated = True
    else:
        if request.params.get("page") is None and valid_show_task != -1:
            highlighted_index = next(
                index
                for index, task in enumerate(tasks)
                if task.get("task_id") == valid_show_task
            )
            page_idx = highlighted_index // _TASKS_PAGE_SIZE
        page_idx = _clamp_page_index(
            page_idx,
            total_count=num_tasks,
            page_size=_TASKS_PAGE_SIZE,
        )
        start = page_idx * _TASKS_PAGE_SIZE
        tasks = tasks[start : start + _TASKS_PAGE_SIZE]

    run_id = str(run["_id"])
    query_params = _tasks_query_string(
        sort_param=sort_param,
        order_param=order_param,
        query_filter=query_filter,
        view=view_param,
    )
    pages = (
        pagination(page_idx, num_tasks, _TASKS_PAGE_SIZE, query_params)
        if view_param == "paged"
        else []
    )
    for page in pages:
        page_url = str(page.get("url", ""))
        if page_url.startswith("?"):
            page["url"] = f"/tests/tasks/{run_id}{page_url}&show_task={show_task}"

    return {
        "run": run,
        "run_id": run_id,
        "approver": approver,
        "show_task": valid_show_task,
        "chi2": chi2,
        "tasks": tasks,
        "show_pentanomial": show_pentanomial,
        "show_residual": show_residual,
        "sort": sort_param,
        "order": order_param,
        "q": query_filter,
        "view": view_param,
        "current_page": page_idx + 1,
        "pages": pages,
        "num_tasks": num_tasks,
        "max_all": _TASKS_MAX_ALL,
        "is_truncated": is_truncated,
    }


def _set_tasks_cookie(
    request: _ViewContext,
    name: str,
    value: str,
    max_age_seconds: int,
) -> None:
    cookie_value = (
        f"{name}={quote(value, safe='')}; path=/; max-age={max_age_seconds}; "
        "SameSite=Lax"
    )
    request.response_headerlist.append(
        (
            "Set-Cookie",
            cookie_value,
        ),
    )


def _set_tasks_cookies(
    request: _ViewContext,
    state: dict[str, Any],
) -> None:
    cookie_max_age = UI_STATE_COOKIE_MAX_AGE_SECONDS
    _set_tasks_cookie(request, "tasks_sort", str(state["sort"]), cookie_max_age)
    _set_tasks_cookie(request, "tasks_order", str(state["order"]), cookie_max_age)
    _set_tasks_cookie(request, "tasks_view", str(state["view"]), cookie_max_age)
    _set_tasks_cookie(request, "tasks_q", str(state["q"]), cookie_max_age)


def _format_tests_view_spsa_value(
    run: dict[str, Any],
    value: dict[str, Any],
) -> list[str | _SpsaTableRow]:
    iter_local = value["iter"] + 1  # start from 1 to avoid division by zero
    A = value["A"]  # noqa: N806
    alpha = value["alpha"]
    gamma = value["gamma"]
    summary = (
        f"iter: {iter_local:d}, A: {A:d}, alpha: {alpha:0.3f}, gamma: {gamma:0.3f}"
    )
    params = value["params"]
    spsa_value: list[str | _SpsaTableRow] = [summary]
    for p in params:
        try:
            c_iter = p["c"] / (iter_local**gamma)
            r_iter = p["a"] / (A + iter_local) ** alpha / c_iter**2
        except (ArithmeticError, TypeError, ValueError) as e:
            logger.warning(
                "Invalid SPSA param state while rendering "
                "run %s (iter=%d, param=%s): %s",
                run["_id"],
                iter_local,
                p.get("name", "<unknown>"),
                e,
            )
            c_iter = float("nan")
            r_iter = float("nan")
        spsa_value.append(
            [
                p["name"],
                "{:.2f}".format(p["theta"]),
                str(int(p["start"])),
                str(int(p["min"])),
                str(int(p["max"])),
                f"{c_iter:.3f}",
                "{:.3f}".format(p["c_end"]),
                f"{r_iter:.2e}",
                "{:.2e}".format(p["r_end"]),
            ],
        )
    return spsa_value


def _format_tests_view_string_arg(
    run: dict[str, Any],
    name: str,
    value: str,
) -> str | None:
    if name == "arch_filter":
        if value == "":
            return None
        filtered_arches = list(
            filter(
                lambda x: regex.search(value, x) is not None,
                supported_arches,
            ),
        )
        return value + "  (" + ", ".join(filtered_arches) + ")"
    if name == "new_tag" and "msg_new" in run["args"]:
        return value + "  (" + run["args"]["msg_new"][:50] + ")"
    if name == "base_tag" and "msg_base" in run["args"]:
        return value + "  (" + run["args"]["msg_base"][:50] + ")"
    return value


def _format_tests_view_list_arg(name: str, value: list[str]) -> str:
    if name in ("new_nets", "base_nets"):
        return ", ".join(value)
    return str(value)


def _format_tests_view_dict_arg(
    run: dict[str, Any],
    name: str,
    value: dict[str, Any],
) -> _RunArgValue:
    if name == "sprt":
        return (
            "elo0: {:.2f} alpha: {:.2f} elo1: {:.2f} beta: {:.2f} state: {} ({})"
        ).format(
            value["elo0"],
            value["alpha"],
            value["elo1"],
            value["beta"],
            value.get("state", "-"),
            value.get("elo_model", "BayesElo"),
        )
    if name == "spsa":
        return _format_tests_view_spsa_value(run, value)
    return str(value)


def _normalize_tests_view_list_arg(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None

    normalized_value: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        normalized_value.append(item)
    return normalized_value


def _normalize_tests_view_dict_arg(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    normalized_value: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        normalized_value[key] = item
    return normalized_value


def _format_tests_view_arg_value(
    run: dict[str, Any],
    name: str,
    value: object,
) -> _RunArgValue | None:
    if isinstance(value, str):
        return _format_tests_view_string_arg(run, name, value)

    normalized_list = _normalize_tests_view_list_arg(value)
    if normalized_list is not None:
        return _format_tests_view_list_arg(name, normalized_list)

    normalized_dict = _normalize_tests_view_dict_arg(value)
    if normalized_dict is not None:
        return _format_tests_view_dict_arg(run, name, normalized_dict)

    return str(value)


def _build_tests_view_arg_url(
    run: dict[str, Any],
    name: str,
    value: _RunArgValue,
    *,
    tests_repo_value: str,
    repo_info: tuple[str, str],
) -> str:
    tests_repo_user, tests_repo_repo = repo_info
    if name == "tests_repo":
        return tests_repo_value
    if name == "master_repo":
        return str(value)
    if name == "new_tag":
        return gh.commit_url(
            user=tests_repo_user,
            repo=tests_repo_repo,
            branch=run["args"]["resolved_new"],
        )
    if name == "base_tag":
        return gh.commit_url(
            user=tests_repo_user,
            repo=tests_repo_repo,
            branch=run["args"]["resolved_base"],
        )
    return ""


def _build_tests_view_run_args(run: dict[str, Any]) -> list[_RunArg]:
    run_args: list[_RunArg] = [("id", str(run["_id"]), "")]
    if run.get("rescheduled_from"):
        run_args.append(("rescheduled_from", str(run["rescheduled_from"]), ""))

    tests_repo_value = tests_repo(run)
    tests_repo_user, tests_repo_repo = gh.parse_repo(tests_repo_value)

    for name in (
        "new_tag",
        "new_signature",
        "new_options",
        "resolved_new",
        "new_net",
        "new_nets",
        "base_tag",
        "base_signature",
        "base_options",
        "resolved_base",
        "base_net",
        "base_nets",
        "sprt",
        "num_games",
        "spsa",
        "tc",
        "new_tc",
        "threads",
        "book",
        "book_depth",
        "auto_purge",
        "priority",
        "itp",
        "throughput",
        "username",
        "tests_repo",
        "master_repo",
        "adjudication",
        "arch_filter",
        "compiler",
        "info",
    ):
        if name not in run["args"]:
            continue

        raw_value = tests_repo_value if name == "tests_repo" else run["args"][name]
        value = _format_tests_view_arg_value(run, name, raw_value)
        if value is None:
            continue
        url = _build_tests_view_arg_url(
            run,
            name,
            value,
            tests_repo_value=tests_repo_value,
            repo_info=(tests_repo_user, tests_repo_repo),
        )

        if name == "spsa":
            run_args.append(("spsa", value, ""))
        else:
            run_args.append((name, str(value), url))

    return run_args


def _build_tests_view_detail_context(
    request: _ViewContext,
    run: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(run["_id"])
    return {
        "run": run,
        **_build_tests_view_status_context(run),
        "run_args": _build_tests_view_run_args(run),
        "approver": request.has_permission("approve_run"),
        "chi2": get_chi2(run["tasks"]),
        "document_size": len(bson.BSON.encode(run)),
        "spsa_data": request.rundb.spsa_handler.get_spsa_data(run_id),
    }


def _tasks_query_string(
    *,
    sort_param: str,
    order_param: str,
    query_filter: str,
    view: str,
) -> str:
    _, default_reverse = _TASKS_SORT_MAP[_TASKS_DEFAULT_SORT]
    default_order = "desc" if default_reverse else "asc"

    params: list[tuple[str, str]] = []
    if sort_param != _TASKS_DEFAULT_SORT:
        params.append(("sort", sort_param))
    if order_param != default_order:
        params.append(("order", order_param))
    if query_filter:
        params.append(("q", query_filter))
    if view == "all":
        params.append(("view", "all"))
    return _build_query_string(params)


def _tasks_sort_value(
    row: dict[str, Any],
    sort_key: str,
) -> int | float | str | tuple[int, int, int, int, int]:
    value = row.get(sort_key, "")
    if sort_key == "task_id":
        return int(value) if isinstance(value, int) else 0

    if sort_key in (
        "crashes",
        "time_losses",
        "wins",
        "losses",
        "draws",
        "played_sort",
    ):
        fallback: int | float | str | tuple[int, int, int, int, int] = -1
    elif sort_key in ("last_updated_sort", "residual_sort"):
        fallback = float("-inf")
    elif sort_key == "pentanomial_sort":
        fallback = (0, 0, 0, 0, 0)
    else:
        return str(value).lower()

    if isinstance(fallback, tuple):
        return value if isinstance(value, tuple) else fallback
    if isinstance(fallback, float):
        return float(value) if isinstance(value, int | float) else fallback
    return value if isinstance(value, int) else fallback


def tests_tasks(request: _ViewContext) -> dict[str, Any] | Response:
    run = request.rundb.get_run(request.matchdict["id"])
    if run is None:
        raise StarletteHTTPException(status_code=404)
    chi2 = get_chi2(run["tasks"])
    show_task = _parse_show_task_param(request)

    context = _task_table_state(
        request,
        run=run,
        show_task=show_task,
        chi2=chi2,
    )
    _set_tasks_cookies(request, context)

    response = _render_hx_fragment(
        request,
        "tasks_content_fragment.html.j2",
        context,
    )
    return response or context


def tests_view_detail(request: _ViewContext) -> dict[str, Any] | Response:
    run = request.rundb.get_run(request.matchdict["id"])
    if run is None:
        raise StarletteHTTPException(status_code=404)

    context = _build_tests_view_detail_context(request, run)

    if _is_hx_request(request):
        expected = (request.params.get("expected") or "").strip().lower()
        actual = context["run_status_label"]

        if actual in {"finished", "failed"}:
            response = _render_hx_fragment(
                request,
                "tests_view_detail_fragment.html.j2",
                context,
            )
            if response is not None:
                response.status_code = 286
                return response
        elif (not expected and actual != "active") or (
            expected and actual == expected and actual != "active"
        ):
            request.response_status = 204
            return context

        response = _render_hx_fragment(
            request,
            "tests_view_detail_fragment.html.j2",
            context,
        )
        return response or context

    return context


def tests_view(request: _ViewContext) -> dict[str, Any] | RedirectResponse:  # noqa: C901, PLR0912, PLR0915
    run = request.rundb.get_run(request.matchdict["id"])
    if run is None:
        raise StarletteHTTPException(status_code=404)
    follow = 1 if "follow" in request.params else 0
    page_title = get_page_title(run)
    results_info = format_results(run)
    detail_context = _build_tests_view_detail_context(request, run)
    open_graph, theme_color = build_tests_view_open_graph(
        host_url=_host_url(request),
        run=run,
        page_title=page_title,
        results_info=results_info,
    )

    chi2 = detail_context["chi2"]

    show_task = _parse_show_task_param(request)

    tasks_table_context = _task_table_state(
        request,
        run=run,
        show_task=show_task,
        chi2=chi2,
    )

    same_user = is_same_user(request, run)

    same_options = True
    with contextlib.suppress(Exception):
        # use sanitize_options for compatibility with old tests
        same_options = sanitize_options(run["args"]["new_options"]) == sanitize_options(
            run["args"]["base_options"],
        )

    notes = []
    if (
        "spsa" not in run["args"]
        and run["args"]["base_signature"] == run["args"]["new_signature"]
    ):
        notes.append("new signature and base signature are identical")
    if run["deleted"]:
        notes.append("this test has been deleted")

    warnings = []
    if run["args"]["throughput"] > _THROUGHPUT_NORMAL_LIMIT:
        warnings.append("throughput exceeds the normal limit")
    if run["args"]["priority"] > 0:
        warnings.append("priority exceeds the normal limit")
    if not reasonable_run_hashes(run):
        warnings.append("hash options are too low or too high for this TC")
    if not same_options:
        warnings.append("base options differ from new options")
    if (f := run.get("failures", 0)) > 0:
        warnings.append(f"this test had {f} {plural(f, 'failure')}")
    elif run["failed"]:
        # for backward compatibility
        warnings.append("this is a failed test")
    if run["args"]["tc"] != run["args"]["new_tc"]:
        warnings.append("this is a test with time odds")
    if run["args"].get("arch_filter", "") != "":
        warnings.append("this test has a non-trivial arch filter")
    if run["args"].get("compiler", "") != "":
        warnings.append("this test has a pinned compiler")
    book_exits = request.rundb.books.get(
        run["args"]["book"],
        {},
    ).get("total", _MIN_BOOK_EXITS)
    if book_exits < _MIN_BOOK_EXITS:
        warnings.append(f"this test uses a small book with only {book_exits} exits")
    if "master_repo" in run["args"]:  # if present then it is non-standard
        warnings.append(
            "the developer repository is not forked from official-stockfish/Stockfish",
        )

    def allow_github_api_calls() -> bool:
        # Avoid making pointless GitHub api calls on behalf of
        # crawlers
        if "master_repo" in run["args"]:  # if present then it is non-standard
            return False
        if request.authenticated_userid:
            return True
        now = datetime.now(UTC)
        # Period should be short enough so that it can be
        # served from the api cache!
        return (now - run["last_updated"]).days <= _RUN_AGE_GITHUB_API_MAX_DAYS

    try:
        user, _repo = gh.parse_repo(gh.normalize_repo(tests_repo(run)))
    except Exception as e:  # noqa: BLE001
        user, _repo = gh.parse_repo(tests_repo(run))
        logger.warning("Unable to normalize_repo: %s", e)

    anchor_url = gh.compare_branches_url(
        user1="official-stockfish",
        branch1=gh.official_master_sha,
        user2=user,
        branch2=run["args"]["resolved_base"],
    )
    # This link is inserted into a warning string and rendered under Jinja
    # autoescape. Build it as Markup so the anchor tag is not escaped.
    # Markup.format will HTML-escape attribute values (defense in depth).
    anchor = Markup(
        '<a class="alert-link" href="{}"'
        ' target="_blank" rel="noopener noreferrer">'
        "base diff</a>",
    ).format(anchor_url)
    use_3dot_diff = False
    if "spsa" not in run["args"] and allow_github_api_calls():
        irl = bool(request.authenticated_userid)
        try:
            if not gh.is_master(
                run["args"]["resolved_new"],
            ):
                # new hasn't been merged
                if not gh.is_master(
                    run["args"]["resolved_base"],
                    ignore_rate_limit=irl,
                ):
                    warnings.append(
                        Markup("base is not an ancestor of master: {}").format(anchor),
                    )
                elif not gh.is_ancestor(
                    user1=user,
                    sha1=run["args"]["resolved_base"],
                    sha2=run["args"]["resolved_new"],
                    ignore_rate_limit=irl,
                ):
                    warnings.append("base is not an ancestor of new")
                else:
                    merge_base_commit = gh.get_merge_base_commit(
                        sha1=gh.official_master_sha,
                        user2=user,
                        sha2=run["args"]["resolved_new"],
                        ignore_rate_limit=irl,
                    )
                    if merge_base_commit != run["args"]["resolved_base"]:
                        warnings.append(
                            "base is not the latest common ancestor of new and master",
                        )
            use_3dot_diff = gh.is_ancestor(
                user1=user,
                sha1=run["args"]["resolved_base"],
                sha2=run["args"]["resolved_new"],
                ignore_rate_limit=irl,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Exception processing api calls for %s: %s", run["_id"], e)

    return {
        **detail_context,
        "open_graph": open_graph,
        "page_title": page_title,
        "results_info": results_info,
        "tasks_shown": tasks_table_context["show_task"] != -1
        or request.cookies.get("tasks_state") == "Hide",
        "show_task": tasks_table_context["show_task"],
        "tasks_sort": tasks_table_context["sort"],
        "tasks_order": tasks_table_context["order"],
        "tasks_view": tasks_table_context["view"],
        "tasks_page": tasks_table_context["current_page"],
        "tasks_q": tasks_table_context["q"],
        "tasks_pages": tasks_table_context["pages"],
        "tasks_num_tasks": tasks_table_context["num_tasks"],
        "tasks_max_all": tasks_table_context["max_all"],
        "tasks_is_truncated": tasks_table_context["is_truncated"],
        "follow": follow,
        "can_modify_run": can_modify_run(request, run),
        "same_user": same_user,
        "pt_info": request.rundb.pt_info,
        "notes": notes,
        "theme_color": theme_color,
        "warnings": warnings,
        "use_3dot_diff": use_3dot_diff,
        "allow_github_api_calls": allow_github_api_calls(),
    }


# === Router Registration ===

# Each entry: (view_function, path, config_dict)
# Config keys: renderer, require_csrf, require_primary, request_method, http_cache
# Special: direct=True bypasses _dispatch_view
# (for pure redirects, no DB/session needed)
_VIEW_ROUTES: list[_ViewRoute] = [
    (home, "/", {"direct": True}),
    (
        login,
        "/login",
        {
            "renderer": "login.html.j2",
            "require_csrf": True,
            "request_method": ("GET", "POST"),
        },
    ),
    (
        workers,
        "/workers/{worker_name}",
        {
            "renderer": "workers.html.j2",
            "require_csrf": True,
            "request_method": ("GET", "POST"),
        },
    ),
    (
        upload,
        "/upload",
        {
            "renderer": "nn_upload.html.j2",
            "require_csrf": True,
            "request_method": ("GET", "POST"),
        },
    ),
    (logout, "/logout", {"require_csrf": True, "request_method": "POST"}),
    (
        signup,
        "/signup",
        {
            "renderer": "signup.html.j2",
            "require_csrf": True,
            "request_method": ("GET", "POST"),
        },
    ),
    (nns, "/nns", {"renderer": "nns.html.j2"}),
    (sprt_calc, "/sprt_calc", {"renderer": "sprt_calc.html.j2"}),
    (rate_limits, "/rate_limits", {"renderer": "rate_limits.html.j2"}),
    (rate_limits_server, "/rate_limits/server", {}),
    (
        user_management_pending_count,
        "/user_management/pending_count",
        {"renderer": "pending_users_nav_fragment.html.j2"},
    ),
    (actions, "/actions", {"renderer": "actions.html.j2"}),
    (user_management, "/user_management", {"renderer": "user_management.html.j2"}),
    (
        user,
        "/user/{username}",
        {
            "renderer": "user.html.j2",
            "require_csrf": True,
            "request_method": ("GET", "POST"),
        },
    ),
    (
        user,
        "/user",
        {
            "renderer": "user.html.j2",
            "require_csrf": True,
            "request_method": ("GET", "POST"),
        },
    ),
    (contributors, "/contributors", {"renderer": "contributors.html.j2"}),
    (
        contributors_monthly,
        "/contributors/monthly",
        {"renderer": "contributors.html.j2"},
    ),
    (
        tests_run,
        "/tests/run",
        {
            "renderer": "tests_run.html.j2",
            "require_csrf": True,
            "require_primary": True,
            "request_method": ("GET", "POST"),
        },
    ),
    (
        tests_modify,
        "/tests/modify",
        {"require_csrf": True, "request_method": "POST", "require_primary": True},
    ),
    (
        tests_stop,
        "/tests/stop",
        {"require_csrf": True, "request_method": "POST", "require_primary": True},
    ),
    (
        tests_approve,
        "/tests/approve",
        {"require_csrf": True, "request_method": "POST", "require_primary": True},
    ),
    (
        tests_purge,
        "/tests/purge",
        {"require_csrf": True, "request_method": "POST", "require_primary": True},
    ),
    (
        tests_delete,
        "/tests/delete",
        {"require_csrf": True, "request_method": "POST", "require_primary": True},
    ),
    (tests_live_elo, "/tests/live_elo/{id}", {"renderer": "tests_live_elo.html.j2"}),
    (
        live_elo_update,
        "/tests/live_elo_update/{id}",
        {"renderer": "live_elo_fragment.html.j2"},
    ),
    (tests_stats, "/tests/stats/{id}", {"renderer": "tests_stats.html.j2"}),
    (
        tests_tasks,
        "/tests/tasks/{id}",
        {"renderer": "tasks_content_fragment.html.j2"},
    ),
    (
        tests_view_detail,
        "/tests/view/{id}/detail",
        {"renderer": "tests_view_detail_fragment.html.j2"},
    ),
    (
        tests_machines,
        "/tests/machines",
        {"renderer": "machines_fragment.html.j2", "http_cache": 10},
    ),
    (tests_view, "/tests/view/{id}", {"renderer": "tests_view.html.j2"}),
    (tests_finished, "/tests/finished", {"renderer": "tests_finished.html.j2"}),
    (tests_user, "/tests/user/{username}", {"renderer": "tests_user.html.j2"}),
    (tests, "/tests", {"renderer": "tests.html.j2"}),
]


def _make_endpoint(
    fn: Callable[..., Any],
    cfg_local: _ViewRouteConfig,
) -> Callable[..., Any]:
    async def endpoint(request: Request) -> Response:
        return await _dispatch_view(
            fn,
            cfg_local,
            request,
            dict(getattr(request, "path_params", {}) or {}),
        )

    return endpoint


def _normalize_methods(methods: _RouteMethods | None) -> list[str]:
    if methods is None:
        return ["GET"]
    if isinstance(methods, str):
        return [methods]
    return list(methods)


def _register_view_routes() -> None:
    for fn, path, cfg in _VIEW_ROUTES:
        methods = _normalize_methods(cfg.get("request_method"))
        endpoint = fn if cfg.get("direct") else _make_endpoint(fn, cfg)
        router.add_api_route(
            path,
            endpoint,
            methods=methods,
            include_in_schema=False,
        )


_register_view_routes()


__all__ = ["router"]
