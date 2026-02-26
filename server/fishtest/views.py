import copy
import gzip
import hashlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlencode

import bson
import regex
import requests
from fastapi import APIRouter
from markupsafe import Markup
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
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
    github_repo,
    is_undecided,
    runs_schema,
    short_worker_name,
)
from fishtest.schemas import tc as tc_schema
from fishtest.util import (
    VALID_USERNAME_PATTERN,
    email_valid,
    format_bounds,
    format_date,
    format_group,
    format_time_ago,
    get_chi2,
    get_hash,
    get_tc_ratio,
    is_sprt_ltc_data,
    password_strength,
    plural,
    reasonable_run_hashes,
    supported_arches,
    supported_compilers,
    tests_repo,
    worker_name,
)

HTTP_TIMEOUT = 15.0
FORM_MAX_FILES = 2
FORM_MAX_FIELDS = 200
FORM_MAX_PART_SIZE = 200 * 1024 * 1024
DEFAULT_RECAPTCHA_SITE_KEY = "6LePs8YUAAAAABMmqHZVyVjxat95Z1c_uHrkugZM"

router = APIRouter(tags=["ui"])


class _ViewContext:
    def __init__(self, request, session, post, matchdict, context=None):
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
    def authenticated_userid(self):
        return authenticated_user(self.session)

    def has_permission(self, permission):
        if permission != "approve_run":
            return False
        username = self.authenticated_userid
        if not username:
            return False
        groups = self.userdb.get_user_groups(username)
        return "group:approvers" in (groups or [])


_RequestShim = _ViewContext


def _apply_response_headers(shim, response):
    for key, value in getattr(shim, "response_headers", {}).items():
        response.headers[key] = value
    for key, value in getattr(shim, "response_headerlist", []):
        response.headers[key] = value
    return response


async def _dispatch_view(fn, cfg, request, path_params):
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

    if isinstance(result, RedirectResponse):
        commit_session_response(request, session, shim, result)
        return _apply_response_headers(shim, result)

    status_code = getattr(shim, "response_status", 200) or 200

    renderer = cfg.get("renderer")
    if int(status_code) == 204:
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
    return _apply_response_headers(shim, response)


def pagination(page_idx, num, page_size, query_params):
    pages = [
        {
            "idx": "Prev",
            "url": "?page={}".format(page_idx) + query_params,
            "state": "disabled" if page_idx == 0 else "",
        }
    ]

    if num <= 0:
        pages.append(
            {
                "idx": 1,
                "url": "?page=1" + query_params,
                "state": "active" if page_idx == 0 else "",
            }
        )
        pages.append(
            {
                "idx": "Next",
                "url": "?page={}".format(page_idx + 2) + query_params,
                "state": "disabled",
            }
        )
        return pages

    last_idx = (num - 1) // page_size

    disable_next = page_idx >= last_idx

    def add_page(idx):
        pages.append(
            {
                "idx": idx + 1,
                "url": "?page={}".format(idx + 1) + query_params,
                "state": "active" if page_idx == idx else "",
            }
        )

    # Always show page 1.
    add_page(0)

    # Compact mobile-friendly layout:
    # Prev, 1, ..., (current-1,current,current+1), ..., last, Next
    if page_idx <= 2:
        for idx in range(1, min(last_idx, 4)):
            add_page(idx)
    elif page_idx >= last_idx - 2:
        pages.append({"idx": "...", "url": "", "state": "disabled"})
        for idx in range(max(1, last_idx - 3), last_idx):
            add_page(idx)
    else:
        pages.append({"idx": "...", "url": "", "state": "disabled"})
        for idx in (page_idx - 1, page_idx, page_idx + 1):
            add_page(idx)

    if last_idx >= 5 and page_idx < last_idx - 2:
        pages.append({"idx": "...", "url": "", "state": "disabled"})

    if last_idx > 0:
        add_page(last_idx)

    pages.append(
        {
            "idx": "Next",
            "url": "?page={}".format(page_idx + 2) + query_params,
            "state": "disabled" if disable_next else "",
        }
    )
    return pages


def _host_url(request) -> str:
    host_url = getattr(request, "host_url", None)
    if host_url:
        return host_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def _path_qs(request) -> str:
    path_qs = getattr(request, "path_qs", None)
    if path_qs:
        return path_qs
    url = getattr(request, "url", None)
    if url is None:
        path = getattr(request, "path", "")
        query_params = getattr(request, "params", {})
        query = urlencode(query_params) if query_params else ""
        return path if not query else f"{path}?{query}"
    query = url.query if hasattr(url, "query") else ""
    path = url.path if hasattr(url, "path") else str(url).split("?", 1)[0]
    return path if not query else f"{path}?{query}"


def _path_url(request) -> str:
    path_url = getattr(request, "path_url", None)
    if path_url:
        return path_url
    url = getattr(request, "url", None)
    if url is None:
        host_url = _host_url(request)
        path = getattr(request, "path", "")
        return f"{host_url}{path}"
    return str(url).split("?", 1)[0]


# === Home redirect ===
def home(request=None):
    """Redirect / to /tests. Registered directly on the router (no _dispatch_view)."""
    return RedirectResponse(url="/tests", status_code=302)


# === Authentication views ===
def ensure_logged_in(request):
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


def login(request):
    userid = request.authenticated_userid
    if userid:
        return home(request)
    login_url = f"{_host_url(request)}/login"
    referrer = request.url
    if referrer == login_url:
        referrer = "/"  # never use the login form itself as came_from
    came_from = request.params.get("came_from", referrer)

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        token = request.userdb.authenticate(username, password)
        if "error" not in token:
            if request.POST.get("stay_logged_in"):
                # Session persists for a year after login
                remember(request, username, max_age=60 * 60 * 24 * 365)
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


# === Worker administration ===
# Note that the allowed length of mailto URLs on Chrome/Windows is severely
# limited.
def worker_email(worker_name, blocker_name, message, host_url, blocked):
    owner_name = worker_name.split("-")[0]
    body = f"""\
Dear {owner_name},

Thank you for contributing to the development of Stockfish. Unfortunately, it seems your Fishtest worker {worker_name} has some issue(s). More specifically the following has been reported:

{message}

You may possibly find more information about this in our event log at {host_url}/actions

Feel free to reply to this email if you require any help, or else contact the #fishtest-dev channel on the Stockfish Discord server: https://discord.com/invite/awnh2qZfTT

Enjoy your day,

{blocker_name} (Fishtest approver)

"""
    return body


def normalize_lf(m):
    m = m.replace("\r\n", "\n").replace("\r", "\n")
    return m.rstrip()


def _blocked_worker_rows(blocked_workers, *, show_email):
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
                "last_updated_label": last_updated_label,
                "actions_url": actions_url,
                "owner_email": owner_email,
                "mailto_url": mailto_url,
            }
        )
    return rows


def workers(request):
    is_approver = request.has_permission("approve_run")

    blocked_workers = request.rundb.workerdb.get_blocked_workers()
    blocker_name = request.authenticated_userid

    # If we are approver then we are logged in, so blocker_name is not None
    if is_approver:
        for w in blocked_workers:
            owner_name = w["worker_name"].split("-")[0]
            owner = request.userdb.get_user(owner_name)
            w["owner_email"] = owner["email"] if owner is not None else ""
            w["body"] = worker_email(
                w["worker_name"],
                blocker_name,
                w["message"],
                _host_url(request),
                w["blocked"],
            )
            w["subject"] = f"Issue(s) with worker {w['worker_name']}"

    worker_name = request.matchdict.get("worker_name")
    try:
        validate(union(short_worker_name, "show"), worker_name, name="worker_name")
    except ValidationError as e:
        request.session.flash(str(e), "error")
        return {
            "show_admin": False,
            "show_email": is_approver,
            "blocked_workers": _blocked_worker_rows(
                blocked_workers,
                show_email=is_approver,
            ),
        }
    if len(worker_name.split("-")) != 3:
        return {
            "show_admin": False,
            "show_email": is_approver,
            "blocked_workers": _blocked_worker_rows(
                blocked_workers,
                show_email=is_approver,
            ),
        }
    result = ensure_logged_in(request)
    if isinstance(result, RedirectResponse):
        return result
    owner_name = worker_name.split("-")[0]
    if not is_approver and blocker_name != owner_name:
        request.session.flash("Only owners and approvers can block/unblock", "error")
        return {
            "show_admin": False,
            "show_email": is_approver,
            "blocked_workers": _blocked_worker_rows(
                blocked_workers,
                show_email=is_approver,
            ),
        }

    if request.method == "POST":
        button = request.POST.get("submit")
        if button == "Submit":
            blocked = request.POST.get("blocked") is not None
            message = request.POST.get("message")
            max_chars = 500
            if len(message) > max_chars:
                request.session.flash(
                    f"Warning: your description of the issue has been truncated to {max_chars} characters",
                    "error",
                )
                message = message[:max_chars]
            message = normalize_lf(message)
            was_blocked = request.workerdb.get_worker(worker_name)["blocked"]
            request.rundb.workerdb.update_worker(
                worker_name, blocked=blocked, message=message
            )
            if blocked != was_blocked:
                request.session.flash(
                    f"Worker {worker_name} {'blocked' if blocked else 'unblocked'}!",
                )
                request.actiondb.block_worker(
                    username=blocker_name,
                    worker=worker_name,
                    message="blocked" if blocked else "unblocked",
                )
        return RedirectResponse(url="/workers/show", status_code=302)

    w = request.rundb.workerdb.get_worker(worker_name)
    return {
        "show_admin": True,
        "worker_name": worker_name,
        "blocked": w["blocked"],
        "message": w["message"],
        "show_email": is_approver,
        "last_updated_label": (
            format_time_ago(w["last_updated"]) if w["last_updated"] else "Never"
        ),
        "blocked_workers": _blocked_worker_rows(
            blocked_workers,
            show_email=is_approver,
        ),
    }


# === Neural network uploads + tools ===
def upload(request):
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
            "Specify a network file with the 'Choose File' button", "error"
        )
        return base_context
    except Exception as e:
        print("Error reading the network file:", e)
        request.session.flash("Error reading the network file", "error")
        return base_context
    if request.rundb.get_nn(filename):
        request.session.flash(f"Network {filename} already exists", "error")
        return base_context
    errors = []
    if len(network) >= 200000000:
        errors.append("Network must be < 200MB")
    if not re.match(r"^nn-[0-9a-f]{12}\.nnue$", filename):
        errors.append('Name must match "nn-[SHA256 first 12 digits].nnue"')
    hash = hashlib.sha256(network).hexdigest()
    if hash[:12] != filename[3:15]:
        errors.append(f"Wrong SHA256 hash: {hash[:12]} Filename: {filename[3:15]}")
    if errors:
        for error in errors:
            request.session.flash(error, "error")
        return base_context
    net_file_gz = Path("/var/www/fishtest/nn") / f"{filename}.gz"
    try:
        with gzip.open(net_file_gz, "xb") as f:
            f.write(network)
    except FileExistsError as e:
        print(f"Network {filename} already uploaded:", e)
        request.session.flash(f"Network {filename} already uploaded", "error")
        return base_context
    except Exception as e:
        net_file_gz.unlink(missing_ok=True)
        print(f"Failed to write network {filename}:", e)
        request.session.flash(f"Failed to write network {filename}", "error")
        return base_context
    try:
        net_data = gzip.decompress(net_file_gz.read_bytes())
    except Exception as e:
        net_file_gz.unlink()
        print(f"Failed to read uploaded network {filename}:", e)
        request.session.flash(f"Failed to read uploaded network {filename}", "error")
        return base_context

    hash = hashlib.sha256(net_data).hexdigest()
    if hash[:12] != filename[3:15]:
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


def logout(request):
    session = request.session
    forget(request)
    session.invalidate()
    return RedirectResponse(url="/tests", status_code=302)


def signup(request):
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

    signup_username = request.POST.get("username", "").strip()
    signup_password = request.POST.get("password", "").strip()
    signup_password_verify = request.POST.get("password2", "").strip()
    signup_email = request.POST.get("email", "").strip()
    tests_repo = request.POST.get("tests_repo", "").strip()

    strong_password, password_err = password_strength(
        signup_password, signup_username, signup_email
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
        validate(union(github_repo, ""), tests_repo, "tests_repo")
    except ValidationError as e:
        errors.append(f"Error! Invalid tests repo {tests_repo}: {str(e)}")

    if errors:
        for error in errors:
            request.session.flash(error, "error")
        return signup_context

    secret = os.environ.get("FISHTEST_CAPTCHA_SECRET", "").strip()
    captcha_response = request.POST.get("g-recaptcha-response", "").strip()

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
            print(response["error-codes"])
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
            "Thank you for contributing!"
        )
        return RedirectResponse(url="/login", status_code=302)
    return signup_context


def nns(request):
    user = request.params.get("user", "")
    network_name = request.params.get("network_name", "")
    master_only = request.params.get("master_only", False)

    page_param = request.params.get("page", "")
    page_idx = max(0, int(page_param) - 1) if page_param.isdigit() else 0
    page_size = 25

    nns, num_nns = request.rundb.get_nns(
        user=user,
        network_name=network_name,
        master_only=master_only,
        limit=page_size,
        skip=page_idx * page_size,
    )

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
            }
        )

    query_params = ""
    if user:
        query_params += "&user={}".format(user)
    if network_name:
        query_params += "&network_name={}".format(network_name)
    if master_only:
        query_params += "&master_only={}".format(master_only)

    pages = pagination(page_idx, num_nns, page_size, query_params)

    return {
        "nns": formatted_nns,
        "pages": pages,
        "master_only": request.cookies.get("master_only") == "true",
        "filters": {
            "network_name": network_name,
            "user": user,
            "master_only": master_only,
        },
        "network_name_filter": network_name,
        "user_filter": user,
    }


def sprt_calc(request):
    return {}


def rate_limits(request):
    return {}


# Different LOCALES may have different quotation marks.
# See https://op.europa.eu/en/web/eu-vocabularies/formex/physical-specifications/character-encoding/quotation-marks

quotation_marks = (
    0x0022,
    0x0027,
    0x00AB,
    0x00BB,
    0x2018,
    0x2019,
    0x201A,
    0x201B,
    0x201C,
    0x201D,
    0x201E,
    0x201F,
    0x2039,
    0x203A,
)

quotation_marks = "".join(chr(c) for c in quotation_marks)
quotation_marks_translation = str.maketrans(quotation_marks, len(quotation_marks) * '"')


def sanitize_quotation_marks(text):
    return text.translate(quotation_marks_translation)


# === Actions log ===
def actions(request):
    DEFAULT_MAX_ACTIONS_AUTH = 50000
    HARD_MAX_ACTIONS_ANON = 5000

    is_authenticated = request.authenticated_userid is not None

    search_action = request.params.get("action", "")
    username = request.params.get("user", "")
    text = sanitize_quotation_marks(request.params.get("text", ""))
    before = request.params.get("before", None)
    max_actions_param = request.params.get("max_actions", None)
    max_actions = None
    run_id = request.params.get("run_id", "")

    if before:
        before = float(before)
    if max_actions_param:
        try:
            max_actions = int(max_actions_param)
        except ValueError:
            max_actions = None
        if max_actions is not None and max_actions <= 0:
            max_actions = None

    if not is_authenticated:
        max_actions = HARD_MAX_ACTIONS_ANON if max_actions is None else max_actions
        max_actions = min(max_actions, HARD_MAX_ACTIONS_ANON)
    elif max_actions is None and not (username or search_action or text or run_id):
        # Default cap for unfiltered /actions.
        max_actions = DEFAULT_MAX_ACTIONS_AUTH

    page_param = request.params.get("page", "")
    page_idx = max(0, int(page_param) - 1) if page_param.isdigit() else 0
    page_size = 25

    actions, num_actions = request.actiondb.get_actions(
        username=username,
        action=search_action,
        text=text,
        skip=page_idx * page_size,
        limit=page_size,
        utc_before=before,
        max_actions=max_actions,
        run_id=run_id,
    )
    actions = list(actions)

    for action in actions:
        action.setdefault("action", "")
        action.setdefault("username", "")
        time_value = action.get("time")
        if time_value is None:
            time_label = ""
        else:
            time_label = datetime.fromtimestamp(float(time_value), UTC).strftime(
                "%y-%m-%d %H:%M:%S"
            )
            time_label = time_label.replace("-", "\u2011", 2)

        time_query = {
            "max_actions": "1",
            "action": search_action,
            "user": username,
            "text": text,
            "before": time_value or "",
            "run_id": run_id,
        }
        time_url = "/actions?" + urlencode(time_query)

        agent_name = ""
        agent_url = ""
        if "worker" in action and action.get("action") != "block_worker":
            agent_name = action.get("worker", "")
            agent_short = "-".join(agent_name.split("-")[0:3]) if agent_name else ""
            agent_url = f"/workers/{agent_short}" if agent_short else ""
        else:
            agent_name = action.get("username", "")
            agent_url = f"/user/{agent_name}" if agent_name else ""

        if action.get("action") in ("system_event", "log_message"):
            agent_url = ""
            if "worker" in action:
                agent_name = action.get("worker", agent_name)

        target_name = ""
        target_url = ""
        if "nn" in action:
            raw_name = action.get("nn", "")
            target_name = raw_name.replace("-", "\u2011") if raw_name else ""
            target_url = f"/api/nn/{raw_name}" if raw_name else ""
        elif "run" in action and "run_id" in action:
            target_name = action.get("run", "")
            task_id = action.get("task_id")
            task_suffix = f"/{task_id}" if task_id is not None else ""
            target_name = f"{target_name}{task_suffix}" if target_name else ""
            task_query = f"?show_task={task_id}" if task_id is not None else ""
            target_url = f"/tests/view/{action.get('run_id')}{task_query}"
        elif request.has_permission("approve_run") and "user" in action:
            target_name = action.get("user", "")
            target_url = f"/user/{target_name}" if target_name else ""
        elif action.get("action") == "block_worker" and "worker" in action:
            target_name = action.get("worker", "")
            target_url = f"/workers/{target_name}" if target_name else ""
        else:
            target_name = action.get("user", "")

        action.update(
            {
                "time_label": time_label,
                "time_url": time_url,
                "event": action.get("action", ""),
                "agent_name": agent_name,
                "agent_url": agent_url or None,
                "target_name": target_name,
                "target_url": target_url or None,
                "message": action.get("message", ""),
            }
        )

    # If the requested page is out of range, redirect to the last page.
    if num_actions > 0:
        last_page = (num_actions - 1) // page_size + 1
        if page_param.isdigit() and int(page_param) > last_page:
            redirect_query = dict(request.params)
            redirect_query["page"] = str(last_page)
            if max_actions is not None:
                redirect_query["max_actions"] = str(max_actions)
            return RedirectResponse(
                url=_path_url(request) + "?" + urlencode(redirect_query),
                status_code=302,
            )

    query_params = ""
    if username:
        query_params += "&user={}".format(username)
    if search_action:
        query_params += "&action={}".format(search_action)
    if text:
        query_params += "&text={}".format(text)
    if max_actions:
        query_params += "&max_actions={}".format(max_actions)
    if before:
        query_params += "&before={}".format(before)
    if run_id:
        query_params += "&run_id={}".format(run_id)

    pages = pagination(page_idx, num_actions, page_size, query_params)

    return {
        "actions": actions,
        "pages": pages,
        "filters": {
            "action": search_action,
            "username": username,
            "text": text,
            "run_id": run_id,
        },
        "usernames": [user["username"] for user in request.userdb.get_users()],
    }


# === User management + profiles ===
def get_idle_users(users, request):
    idle = {}
    for u in users:
        idle[u["username"]] = u
    for u in request.userdb.user_cache.find():
        del idle[u["username"]]
    idle = list(idle.values())
    return idle


def _user_management_rows(users):
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
                "registration_label": registration_label,
                "groups": groups,
                "groups_label": format_group(groups),
                "email": user.get("email", ""),
            }
        )
    return rows


def user_management(request):
    if not request.has_permission("approve_run"):
        request.session.flash("You cannot view user management", "error")
        return home(request)

    users = list(request.userdb.get_users())
    pending_users = request.userdb.get_pending()
    blocked_users = request.userdb.get_blocked()
    idle_users = get_idle_users(users, request)

    return {
        "all_users": _user_management_rows(users),
        "pending_users": _user_management_rows(pending_users),
        "blocked_users": _user_management_rows(blocked_users),
        "approvers_users": [
            user
            for user in _user_management_rows(users)
            if "group:approvers" in user.get("groups", [])
        ],
        "idle_users": _user_management_rows(idle_users),  # depends on cache too
    }


def user(request):
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
            old_password = request.POST.get("old_password", "").strip()
            new_password = request.POST.get("password", "").strip()
            new_password_verify = request.POST.get("password2", "").strip()
            new_email = request.POST.get("email", "").strip()
            tests_repo = request.POST.get("tests_repo", "").strip()

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
                        "Error! Matching verify password required", "error"
                    )
                    return home(request)

            try:
                validate(union(github_repo, ""), tests_repo, "tests_repo")
            except ValidationError as e:
                request.session.flash(
                    f"Error! Invalid test repo {tests_repo}: {str(e)}", "error"
                )
                return home(request)

            user_data["tests_repo"] = tests_repo

            if len(new_email) > 0 and user_data["email"] != new_email:
                email_is_valid, validated_email = email_valid(new_email)
                if not email_is_valid:
                    request.session.flash(
                        "Error! Invalid email: " + validated_email, "error"
                    )
                    return home(request)
                else:
                    user_data["email"] = validated_email
                    request.session.flash("Success! Email updated")
            request.userdb.save_user(user_data)
        elif "blocked" in request.POST and request.POST["blocked"].isdigit():
            user_data["blocked"] = bool(int(request.POST["blocked"]))
            request.session.flash(
                ("Blocked" if user_data["blocked"] else "Unblocked")
                + " user "
                + user_name
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
        except Exception:
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


# === Contributors views ===
def contributors(request):
    users_list = list(request.userdb.user_cache.find())
    users_list.sort(key=lambda k: k["cpu_hours"], reverse=True)
    is_approver = request.has_permission("approve_run")
    return {
        "is_monthly": False,
        "monthly_suffix": "",
        "summary": build_contributors_summary(users_list),
        "users": build_contributors_rows(users_list, is_approver=is_approver),
        "is_approver": is_approver,
    }


def contributors_monthly(request):
    users_list = list(request.userdb.top_month.find())
    users_list.sort(key=lambda k: k["cpu_hours"], reverse=True)
    is_approver = request.has_permission("approve_run")
    return {
        "is_monthly": True,
        "monthly_suffix": " - Top Month",
        "summary": build_contributors_summary(users_list),
        "users": build_contributors_rows(users_list, is_approver=is_approver),
        "is_approver": is_approver,
    }


# === Run creation helpers ===


def get_master_info(
    user="official-stockfish", repo="Stockfish", ignore_rate_limit=False
):
    # Contract: always return a dict with stable keys so templates/callers do
    # not crash when GitHub is transiently unavailable.
    default_info = {"bench": None, "message": "", "date": ""}

    try:
        commits = gh.get_commits(
            user=user, repo=repo, ignore_rate_limit=ignore_rate_limit
        )
    except Exception as e:
        # Most common production failure: ConnectionError/RemoteDisconnected.
        print(f"Exception getting commits:\n{e}", flush=True)
        return default_info

    if not isinstance(commits, list) or not commits:
        # GitHub can occasionally return an unexpected JSON shape.
        print(
            "Unexpected GitHub commits payload; expected non-empty list.",
            flush=True,
        )
        return default_info

    bench_search = re.compile(r"(^|\s)[Bb]ench[ :]+([1-9]\d{5,7})(?!\d)")
    latest_bench_match = None

    try:
        message = commits[0]["commit"]["message"].strip().split("\n")[0].strip()
        date_str = commits[0]["commit"]["committer"]["date"]
        date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
    except Exception as e:
        print(f"Unexpected commit payload shape: {e}", flush=True)
        return default_info

    for commit in commits:
        try:
            raw_message = commit["commit"]["message"]
        except KeyError, TypeError:
            # Be tolerant to partial payload corruption in later entries.
            continue
        if not isinstance(raw_message, str):
            continue

        message_lines = raw_message.strip().split("\n")
        for line in reversed(message_lines):
            bench = bench_search.search(line.strip())
            if bench:
                latest_bench_match = {
                    "bench": bench.group(2),
                    "message": message,
                    "date": date.strftime("%b %d"),
                }
                break
        if latest_bench_match:
            break

    if latest_bench_match is None:
        # Keep message/date for PT info text, but leave bench unset.
        return {"bench": None, "message": message, "date": date.strftime("%b %d")}

    return latest_bench_match


def get_sha(branch, repo_url):
    """Resolves the git branch to sha commit"""
    user, repo = gh.parse_repo(repo_url)
    try:
        commit = gh.get_commit(user=user, repo=repo, branch=branch)
    except Exception as e:
        raise Exception(f"Unable to access developer repository {repo_url}: {str(e)}")

    if not isinstance(commit, dict):
        return "", ""

    sha = commit.get("sha")
    if not isinstance(sha, str) or sha == "":
        return "", ""

    message = ""
    commit_data = commit.get("commit")
    if isinstance(commit_data, dict):
        raw_message = commit_data.get("message", "")
        if isinstance(raw_message, str):
            message = raw_message.split("\n", 1)[0]

    return sha, message


def get_nets(commit_sha, repo_url):
    """Get the nets from evaluate.h or ucioption.cpp in the repo"""
    try:
        nets = []
        pattern = re.compile("nn-[a-f0-9]{12}.nnue")

        user, repo = gh.parse_repo(repo_url)
        options = gh.download_from_github(
            "/src/evaluate.h", user=user, repo=repo, branch=commit_sha, method="raw"
        ).decode()
        for line in options.splitlines():
            if "EvalFileDefaultName" in line and "define" in line:
                m = pattern.search(line)
                if m:
                    net = m.group(0)
                    if net not in nets:
                        nets.append(net)

        if nets:
            return nets

        options = gh.download_from_github(
            "/src/ucioption.cpp", user=user, repo=repo, branch=commit_sha, method="raw"
        ).decode()
        for line in options.splitlines():
            if "EvalFile" in line and "Option" in line:
                m = pattern.search(line)
                if m:
                    net = m.group(0)
                    if net not in nets:
                        nets.append(net)
        return nets
    except Exception as e:
        raise Exception(f"Unable to access developer repository {repo_url}: {str(e)}")


def parse_spsa_params(spsa):
    raw = spsa["raw_params"]
    params = []
    for line in raw.split("\n"):
        chunks = line.strip().split(",")
        if len(chunks) == 1 and chunks[0] == "":  # blank line
            continue
        if len(chunks) != 6:
            raise Exception("the line {} does not have 6 entries".format(chunks))
        param = {
            "name": chunks[0],
            "start": float(chunks[1]),
            "min": float(chunks[2]),
            "max": float(chunks[3]),
            "c_end": float(chunks[4]),
            "r_end": float(chunks[5]),
        }
        param["c"] = param["c_end"] * spsa["num_iter"] ** spsa["gamma"]
        param["a_end"] = param["r_end"] * param["c_end"] ** 2
        param["a"] = param["a_end"] * (spsa["A"] + spsa["num_iter"]) ** spsa["alpha"]
        param["theta"] = param["start"]
        params.append(param)
    return params


def validate_modify(request, run):
    """Return None on success, or a RedirectResponse on validation failure."""
    now = datetime.now(UTC)
    if "start_time" not in run or (now - run["start_time"]).days > 30:
        request.session.flash("Run too old to be modified", "error")
        return home(request)

    if "num-games" not in request.POST:
        request.session.flash("Unable to modify with no number of games!", "error")
        return home(request)

    bad_values = not all(
        value is not None and value.replace("-", "").isdigit()
        for value in [
            request.POST["priority"],
            request.POST["num-games"],
            request.POST["throughput"],
        ]
    )

    if bad_values:
        request.session.flash("Bad values!", "error")
        return home(request)

    num_games = int(request.POST["num-games"])
    if (
        num_games > run["args"]["num_games"]
        and "sprt" not in run["args"]
        and "spsa" not in run["args"]
    ):
        request.session.flash(
            "Unable to modify number of games in a fixed game test!", "error"
        )
        return home(request)

    if "spsa" in run["args"] and num_games != run["args"]["num_games"]:
        request.session.flash(
            "Unable to modify number of games for SPSA tests, SPSA hyperparams are based off the initial number of games",
            "error",
        )
        return home(request)

    max_games = 3200000
    if num_games > max_games:
        request.session.flash("Number of games must be <= " + str(max_games), "error")
        return home(request)

    return None


def sanitize_options(options):
    try:
        options.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("Options must contain only ASCII characters")

    tokens = options.split()
    token_regex = re.compile(r"^[^\s=]+=[^\s=]+$", flags=re.ASCII)
    for token in tokens:
        if not token_regex.fullmatch(token):
            raise ValueError(
                "Each option must be a 'key=value' pair with no extra spaces and exactly one '='"
            )
    return " ".join(tokens)


def validate_form(request):
    data = {
        "base_tag": request.POST["base-branch"],
        "new_tag": request.POST["test-branch"],
        "tc": request.POST["tc"],
        "new_tc": request.POST["new_tc"],
        "book": request.POST["book"],
        "book_depth": request.POST["book-depth"],
        "base_signature": request.POST["base-signature"],
        "new_signature": request.POST["test-signature"],
        "base_options": sanitize_options(request.POST["base-options"]),
        "new_options": sanitize_options(request.POST["new-options"]),
        "username": request.authenticated_userid,
        "tests_repo": request.POST["tests-repo"],
        "info": request.POST["run-info"],
        "arch_filter": request.POST["arch-filter"],
        "compiler": request.POST["compiler"],
    }
    try:
        # Deal with people that have changed their GitHub username
        # but still use the old repo url
        data["tests_repo"] = gh.normalize_repo(data["tests_repo"])
    except Exception as e:
        raise Exception(
            f"Unable to access developer repository {data['tests_repo']}: {str(e)}"
        ) from e

    user, repo = gh.parse_repo(data["tests_repo"])
    username = request.authenticated_userid
    u = request.userdb.get_user(username)

    # Deal with people that have forked from "mcostalba/Stockfish" instead
    # of from "official-stockfish/Stockfish".
    official_repo = "https://github.com/official-stockfish/Stockfish"
    master_repo = official_repo
    try:
        master_repo = gh.get_master_repo(user, repo, ignore_rate_limit=True)
    except Exception as e:
        print(
            f"Unable to determine master repo for {data['tests_repo']}: {str(e)}",
            flush=True,
        )
    else:
        if master_repo != official_repo:
            data["master_repo"] = master_repo
            message = (
                f"It seems that your repo {data['tests_repo']} has been forked from "
                f"{master_repo} and not from {official_repo} "
                "as recommended in the wiki. As such, some functionality may be broken. "
            )
            suffix_soft = (
                "Please consider replacing your repo with one forked from the official "
                "Stockfish repo!"
            )
            suffix_hard = (
                "Please replace your repo with one forked from the official "
                "Stockfish repo!"
            )
            if u["registration_time"] >= datetime(2025, 7, 1, tzinfo=UTC):
                raise Exception(message + " " + suffix_hard)
            else:
                request.session.flash(
                    message + " " + suffix_soft,
                    "warning",
                )
    odds = request.POST.get("odds", "off")  # off checkboxes are not posted
    if odds == "off":
        data["new_tc"] = data["tc"]

    checkbox_compiler = request.POST.get(
        "checkbox-compiler", "off"
    )  # off checkboxes are not posted
    if checkbox_compiler == "off":
        del data["compiler"]

    checkbox_arch_filter = request.POST.get(
        "checkbox-arch-filter", "off"
    )  # off checkboxes are not posted
    if checkbox_arch_filter == "off":
        data["arch_filter"] = ""

    if data["arch_filter"] == "":
        del data["arch_filter"]

    # check if arch filter is a valid regular expression
    try:
        if "arch_filter" in data:
            regex.compile(data["arch_filter"])
    except regex.error as e:
        raise Exception(f"Invalid arch filter: {e}") from e

    # check if there are any remaining arches
    if "arch_filter" in data:
        filtered_arches = filter(
            lambda x: regex.search(data["arch_filter"], x) is not None, supported_arches
        )
        if list(filtered_arches) == []:
            raise Exception(f"filter {data['arch_filter']} has no compatible arches")

    validate(tc_schema, data["tc"], "data['tc']")
    validate(tc_schema, data["new_tc"], "data['new_tc']")

    if request.POST.get("rescheduled_from"):
        data["rescheduled_from"] = request.POST["rescheduled_from"]

    def strip_message(m):
        lines = m.strip().split("\n")
        bench_search = re.compile(r"(^|\s)[Bb]ench[ :]+([1-9]\d{5,7})(?!\d)")
        for i, line in enumerate(reversed(lines)):
            new_line, n = bench_search.subn("", line)
            if n:
                lines[-i - 1] = new_line
                break
        s = "\n".join(lines)
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n+", r"\n", s)
        return s.rstrip()

    # Fill new_signature/info from commit info if left blank
    if len(data["new_signature"]) == 0 or len(data["info"]) == 0:
        try:
            c = gh.get_commit(
                user=user, repo=repo, branch=data["new_tag"], ignore_rate_limit=True
            )
        except Exception as e:
            raise Exception(
                f"Unable to access developer repository {data['tests_repo']}: {str(e)}"
            ) from e
        if "commit" not in c:
            raise Exception(
                f"Cannot find branch {data['new_tag']} in developer repository"
            )
        if len(data["new_signature"]) == 0:
            bench_search = re.compile(r"(^|\s)[Bb]ench[ :]+([1-9]\d{5,7})(?!\d)")
            lines = c["commit"]["message"].split("\n")
            for line in reversed(lines):  # Iterate in reverse to find the last match
                m = bench_search.search(line)
                if m:
                    data["new_signature"] = m.group(2)
                    break
            else:
                raise Exception(
                    "This commit has no signature: please supply it manually."
                )
        if len(data["info"]) == 0:
            data["info"] = strip_message(c["commit"]["message"])

    if request.POST["stop_rule"] == "spsa":
        data["base_signature"] = data["new_signature"]

    for k, v in data.items():
        if len(v) == 0:
            raise Exception(f"Missing required option: {k}")

    # Handle boolean options
    data["auto_purge"] = request.POST.get("auto-purge") is not None
    # checkbox is to _disable_ adjudication
    data["adjudication"] = request.POST.get("adjudication") is None

    # In case of reschedule use old data,
    # otherwise resolve sha and update user's tests_repo
    if "resolved_base" in request.POST:
        data["resolved_base"] = request.POST["resolved_base"]
        data["resolved_new"] = request.POST["resolved_new"]
        data["msg_base"] = request.POST["msg_base"]
        data["msg_new"] = request.POST["msg_new"]
    else:
        data["resolved_base"], data["msg_base"] = get_sha(
            data["base_tag"], data["tests_repo"]
        )
        data["resolved_new"], data["msg_new"] = get_sha(
            data["new_tag"], data["tests_repo"]
        )
        u = request.userdb.get_user(data["username"])
        if u.get("tests_repo", "") != data["tests_repo"]:
            u["tests_repo"] = data["tests_repo"]
            request.userdb.save_user(u)

    if len(data["resolved_base"]) == 0 or len(data["resolved_new"]) == 0:
        raise Exception("Unable to find branch!")

    # Check entered bench
    if data["base_tag"] == "master":
        master_info = get_master_info(user=user, repo=repo, ignore_rate_limit=True)
        master_bench = (
            master_info.get("bench") if isinstance(master_info, dict) else None
        )
        if master_bench is None:
            # GitHub is transiently unavailable; skip strict verification.
            print(
                "Unable to verify master bench signature (GitHub API unavailable).",
                flush=True,
            )
        elif master_bench != data["base_signature"]:
            raise Exception(
                "Bench signature of Base master does not match, "
                + 'please "git pull upstream master" !'
            )

    stop_rule = request.POST["stop_rule"]

    # Store nets info
    data["base_nets"] = get_nets(data["resolved_base"], data["tests_repo"])
    data["new_nets"] = get_nets(data["resolved_new"], data["tests_repo"])

    # Test existence of nets
    missing_nets = []
    for net_name in set(data["base_nets"]) | set(data["new_nets"]):
        net = request.rundb.get_nn(net_name)
        if net is None:
            missing_nets.append(net_name)
    if missing_nets:
        raise Exception(
            "Missing net(s). Please upload to: {} the following net(s): {}".format(
                _host_url(request),
                ", ".join(missing_nets),
            )
        )

    # Integer parameters
    data["threads"] = int(request.POST["threads"])
    data["priority"] = int(request.POST["priority"])
    data["throughput"] = int(request.POST["throughput"])

    if data["threads"] <= 0:
        raise Exception("Threads must be >= 1")

    if stop_rule == "sprt":
        # Too small a number results in many API calls, especially with highly concurrent workers.
        # This expression results in 32 games per batch for single threaded STC games.
        # This means a batch with be completed in roughly 2 minutes on a 8 core worker.
        # This expression adjusts the batch size for threads and TC, to keep timings somewhat similar.
        sprt_batch_size_games = 2 * max(
            1, int(0.5 + 16 / get_tc_ratio(data["tc"], data["threads"]))
        )
        assert sprt_batch_size_games % 2 == 0
        elo_model = request.POST["elo_model"]
        if elo_model not in ["BayesElo", "logistic", "normalized"]:
            raise Exception("Unknown Elo model")
        data["sprt"] = fishtest.stats.stat_util.SPRT(
            alpha=0.05,
            beta=0.05,
            elo0=float(request.POST["sprt_elo0"]),
            elo1=float(request.POST["sprt_elo1"]),
            elo_model=elo_model,
            batch_size=sprt_batch_size_games // 2,
        )  # game pairs
        # Limit on number of games played.
        data["num_games"] = 800000
    elif stop_rule == "spsa":
        data["num_games"] = int(request.POST["num-games"])
        if data["num_games"] <= 0:
            raise Exception("Number of games must be >= 0")

        data["spsa"] = {
            "A": int(float(request.POST["spsa_A"]) * data["num_games"] / 2),
            "alpha": float(request.POST["spsa_alpha"]),
            "gamma": float(request.POST["spsa_gamma"]),
            "raw_params": request.POST["spsa_raw_params"],
            "iter": 0,
            "num_iter": int(data["num_games"] / 2),
        }
        data["spsa"]["params"] = parse_spsa_params(data["spsa"])
        if len(data["spsa"]["params"]) == 0:
            raise Exception("Number of params must be > 0")
    else:
        data["num_games"] = int(request.POST["num-games"])
        if data["num_games"] <= 0:
            raise Exception("Number of games must be >= 0")

    max_games = 3200000
    if data["num_games"] > max_games:
        raise Exception("Number of games must be <= " + str(max_games))

    return data


def del_tasks(run):
    run = copy.copy(run)
    run.pop("tasks", None)
    run = copy.deepcopy(run)
    return run


def update_nets(request, run):
    run_id = str(run["_id"])
    data = run["args"]
    base_nets, new_nets, missing_nets = [], [], []
    for net_name in set(data["base_nets"]) | set(data["new_nets"]):
        net = request.rundb.get_nn(net_name)
        if net is None:
            # This should never happen
            missing_nets.append(net_name)
        else:
            if net_name in data["base_nets"]:
                base_nets.append(net)
            if net_name in data["new_nets"]:
                new_nets.append(net)
    if missing_nets:
        raise Exception(
            "Missing net(s). Please upload to {} the following net(s): {}".format(
                _host_url(request),
                ", ".join(missing_nets),
            )
        )

    tests_repo_ = tests_repo(run)
    user, repo = gh.parse_repo(tests_repo_)
    try:
        if gh.is_master(
            run["args"]["resolved_base"],
        ):
            for net in base_nets:
                if "is_master" not in net:
                    net["is_master"] = True
                    request.rundb.update_nn(net)
    except Exception as e:
        print(f"Unable to evaluate is_master({run['args']['resolved_base']}): {str(e)}")

    for net in new_nets:
        if "first_test" not in net:
            net["first_test"] = {"id": run_id, "date": datetime.now(UTC)}
        net["last_test"] = {"id": run_id, "date": datetime.now(UTC)}
        request.rundb.update_nn(net)


def new_run_message(request, run):
    if "sprt" in run["args"]:
        sprt = run["args"]["sprt"]
        elo_model = sprt.get("elo_model")
        ret = f"SPRT{format_bounds(elo_model, sprt['elo0'], sprt['elo1'])}"
    elif "spsa" in run["args"]:
        ret = f"SPSA[{run['args']['num_games']}]"
    else:
        ret = f"NumGames[{run['args']['num_games']}]"
        if run["args"]["resolved_base"] == request.rundb.pt_info["pt_branch"]:
            ret += f"(PT:{request.rundb.pt_info['pt_version']})"
    ret += f" TC:{run['args']['tc']}"
    ret += (
        f"[{run['args']['new_tc']}]"
        if run["args"]["new_tc"] != run["args"]["tc"]
        else ""
    )
    ret += "(LTC)" if run["tc_base"] >= request.rundb.ltc_lower_bound else ""
    ret += f" Book:{run['args']['book']}"
    ret += f" Threads:{run['args']['threads']}"
    ret += "(SMP)" if run["args"]["threads"] > 1 else ""
    ret += f" Hash:{get_hash(run['args']['base_options'])}/{get_hash(run['args']['new_options'])}"
    return ret


# === Run creation ===
def tests_run(request):
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
                "The test was submitted to the queue. Please wait for approval."
            )
            return RedirectResponse(
                url="/tests/view/" + str(run_id) + "?follow=1", status_code=302
            )
        except Exception as e:
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
        "rescheduled_from": request.params["id"] if "id" in request.params else None,
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


def is_same_user(request, run):
    return run["args"]["username"] == request.authenticated_userid


def can_modify_run(request, run):
    return is_same_user(request, run) or request.has_permission("approve_run")


# === Run admin actions ===
def tests_modify(request):
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
        run["args"]["auto_purge"] = True if request.POST.get("auto_purge") else False
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
                        k.replace("_", "-"), before_, after_
                    )
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


def tests_stop(request):
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


def tests_approve(request):
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
        except Exception as e:
            request.session.flash(str(e), "error")
        request.actiondb.approve_run(username=username, run=run, message="approved")
        request.session.flash(message)
    return home(request)


def tests_purge(request):
    run = request.rundb.get_run(request.POST["run-id"])
    if not request.has_permission("approve_run") and not is_same_user(request, run):
        request.session.flash(
            "Only approvers or the submitting user can purge the run."
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


def tests_delete(request):
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
                f"The run object {request.POST['run-id']} does not validate: {str(e)}"
            )
            print(message, flush=True)
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


# === Run detail views ===
def get_page_title(run):
    if run["args"].get("sprt"):
        page_title = "SPRT {} vs {}".format(
            run["args"]["new_tag"], run["args"]["base_tag"]
        )
    elif run["args"].get("spsa"):
        page_title = "SPSA {}".format(run["args"]["new_tag"])
    else:
        page_title = "{} games - {} vs {}".format(
            run["args"]["num_games"], run["args"]["new_tag"], run["args"]["base_tag"]
        )
    return page_title


def _build_live_elo_context(run):
    """Compute SPRT analytics and return template context for gauges + details."""
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
    WLD = [results["wins"], results["losses"], results["draws"]]
    games = sum(WLD)
    pentanomial = results.get("pentanomial", [])
    return {
        "run": run,
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


def tests_elo(request):
    run = request.rundb.get_run(request.matchdict["id"])
    if run is None:
        raise StarletteHTTPException(status_code=404)

    is_finished = run.get("finished", False)
    is_active = run.get("workers", 0) > 0
    expected = request.params.get("expected")

    if expected:
        actual = "finished" if is_finished else ("active" if is_active else "paused")
        if expected != actual:
            request.response_headers["HX-Refresh"] = "true"
        if is_finished:
            request.response_status = 286
        else:
            request.response_status = 204
    else:
        if is_finished:
            request.response_status = 286
        elif not is_active:
            request.response_status = 204

    return {"run": run}


def tests_live_elo(request):
    run = request.rundb.get_run(request.matchdict["id"])
    if run is None or "sprt" not in run["args"]:
        raise StarletteHTTPException(status_code=404)
    context = _build_live_elo_context(run)
    context["page_title"] = get_page_title(run)
    return context


def live_elo_update(request):
    run = request.rundb.get_run(request.matchdict["id"])
    if run is None or "sprt" not in run["args"]:
        raise StarletteHTTPException(status_code=404)

    context = _build_live_elo_context(run)
    if context["sprt_state"]:
        request.response_status = 286
    return context


def tests_stats(request):
    run = request.rundb.get_run(request.matchdict["id"])
    if run is None:
        raise StarletteHTTPException(status_code=404)
    return {
        "run": run,
        "page_title": get_page_title(run),
        "stats": build_tests_stats_context(run),
    }


def tests_tasks(request):
    run = request.rundb.get_run(request.matchdict["id"])
    if run is None:
        raise StarletteHTTPException(status_code=404)
    chi2 = get_chi2(run["tasks"])

    try:
        show_task = int(request.params.get("show_task", -1))
    except ValueError:
        show_task = -1
    if show_task >= len(run["tasks"]) or show_task < -1:
        show_task = -1

    approver = request.has_permission("approve_run")
    tasks, show_pentanomial, show_residual = build_tasks_rows(
        run,
        show_task=show_task,
        chi2=chi2,
        is_approver=approver,
    )

    return {
        "run": run,
        "approver": approver,
        "show_task": show_task,
        "chi2": chi2,
        "tasks": tasks,
        "show_pentanomial": show_pentanomial,
        "show_residual": show_residual,
    }


def tests_machines(request):
    def _clip_long(text: str, max_length: int = 20) -> str:
        if len(text) > max_length:
            return text[:max_length] + "..."
        return text

    machines_list = request.rundb.get_machines()
    machines = []
    for machine in machines_list:
        gcc_version = ".".join(str(m) for m in machine.get("gcc_version", []))
        compiler = machine.get("compiler", "g++")
        python_version = ".".join(str(m) for m in machine.get("python_version", []))
        version = str(machine.get("version", "")) + "*" * machine.get("modified", False)
        worker_short = machine.get("unique_key", "").split("-")[0]
        worker_url = f"/workers/{worker_name(machine, short=True)}"
        formatted_time_ago = format_time_ago(machine["last_updated"])
        sort_value_time_ago = -machine["last_updated"].timestamp()
        branch = machine["run"]["args"]["new_tag"]
        task_id = str(machine["task_id"])
        run_id = str(machine["run"]["_id"])

        machines.append(
            {
                "username": machine["username"],
                "country_code": machine.get("country_code", "").lower(),
                "concurrency": machine["concurrency"],
                "worker_url": worker_url,
                "worker_short": worker_short,
                "nps_m": f"{machine['nps'] / 1000000:.2f}",
                "max_memory": machine["max_memory"],
                "system": machine["uname"],
                "worker_arch": machine["worker_arch"],
                "compiler_label": f"{compiler} {gcc_version}",
                "python_label": python_version,
                "version_label": version,
                "run_url": f"/tests/view/{run_id}?show_task={task_id}",
                "run_label": f"{_clip_long(branch)}/{task_id}",
                "last_active_label": formatted_time_ago,
                "last_active_sort": sort_value_time_ago,
            }
        )

    return {"machines_list": machines_list, "machines": machines}


def tests_view(request):
    run = request.rundb.get_run(request.matchdict["id"])
    if run is None:
        raise StarletteHTTPException(status_code=404)
    run_id = str(run["_id"])
    follow = 1 if "follow" in request.params else 0
    run_args = [("id", str(run["_id"]), "")]
    if run.get("rescheduled_from"):
        run_args.append(("rescheduled_from", run["rescheduled_from"], ""))

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

        value = run["args"][name]
        url = ""

        if name == "arch_filter":
            if value != "":
                filtered_arches = list(
                    filter(
                        lambda x: regex.search(value, x) is not None, supported_arches
                    )
                )
                value += "  (" + ", ".join(filtered_arches) + ")"
            else:
                continue

        if name == "new_tag" and "msg_new" in run["args"]:
            value += "  (" + run["args"]["msg_new"][:50] + ")"

        if name == "base_tag" and "msg_base" in run["args"]:
            value += "  (" + run["args"]["msg_base"][:50] + ")"

        if name in ("new_nets", "base_nets"):
            value = ", ".join(value)

        if name == "sprt" and value != "-":
            value = "elo0: {:.2f} alpha: {:.2f} elo1: {:.2f} beta: {:.2f} state: {} ({})".format(
                value["elo0"],
                value["alpha"],
                value["elo1"],
                value["beta"],
                value.get("state", "-"),
                value.get("elo_model", "BayesElo"),
            )

        if name == "spsa" and value != "-":
            iter_local = value["iter"] + 1  # start from 1 to avoid division by zero
            A = value["A"]
            alpha = value["alpha"]
            gamma = value["gamma"]
            summary = "iter: {:d}, A: {:d}, alpha: {:0.3f}, gamma: {:0.3f}".format(
                iter_local,
                A,
                alpha,
                gamma,
            )
            params = value["params"]
            value = [summary]
            for p in params:
                try:
                    c_iter = p["c"] / (iter_local**gamma)
                    r_iter = p["a"] / (A + iter_local) ** alpha / c_iter**2
                except (ArithmeticError, TypeError, ValueError) as e:
                    print(
                        "Invalid SPSA param state while rendering "
                        f"run {run['_id']} (iter={iter_local}, "
                        f"param={p.get('name', '<unknown>')}): {str(e)}"
                    )
                    c_iter = float("nan")
                    r_iter = float("nan")
                value.append(
                    [
                        p["name"],
                        "{:.2f}".format(p["theta"]),
                        int(p["start"]),
                        int(p["min"]),
                        int(p["max"]),
                        "{:.3f}".format(c_iter),
                        "{:.3f}".format(p["c_end"]),
                        "{:.2e}".format(r_iter),
                        "{:.2e}".format(p["r_end"]),
                    ]
                )

        tests_repo_ = tests_repo(run)
        user, repo = gh.parse_repo(tests_repo_)
        if name == "tests_repo":
            value = tests_repo_
            url = value

        if name == "master_repo":
            url = value

        if name == "new_tag":
            url = gh.commit_url(
                user=user, repo=repo, branch=run["args"]["resolved_new"]
            )
        elif name == "base_tag":
            url = gh.commit_url(
                user=user, repo=repo, branch=run["args"]["resolved_base"]
            )

        if name == "spsa":
            run_args.append(("spsa", value, ""))
        else:
            run_args.append((name, str(value), url))

    active = 0
    cores = 0
    for task in run["tasks"]:
        if task["active"]:
            active += 1
            cores += task["worker_info"]["concurrency"]

    chi2 = get_chi2(run["tasks"])

    try:
        show_task = int(request.params.get("show_task", -1))
    except ValueError:
        show_task = -1
    if show_task >= len(run["tasks"]) or show_task < -1:
        show_task = -1

    same_user = is_same_user(request, run)

    spsa_data = request.rundb.spsa_handler.get_spsa_data(run_id)

    same_options = True
    try:
        # use sanitize_options for compatibility with old tests
        same_options = sanitize_options(run["args"]["new_options"]) == sanitize_options(
            run["args"]["base_options"]
        )
    except Exception:
        pass

    notes = []
    if (
        "spsa" not in run["args"]
        and run["args"]["base_signature"] == run["args"]["new_signature"]
    ):
        notes.append("new signature and base signature are identical")
    if run["deleted"]:
        notes.append("this test has been deleted")

    warnings = []
    if run["args"]["throughput"] > 100:
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
    book_exits = request.rundb.books.get(run["args"]["book"], {}).get("total", 100000)
    if book_exits < 100000:
        warnings.append(f"this test uses a small book with only {book_exits} exits")
    if "master_repo" in run["args"]:  # if present then it is non-standard
        warnings.append(
            "the developer repository is not forked from official-stockfish/Stockfish"
        )

    def allow_github_api_calls():
        # Avoid making pointless GitHub api calls on behalf of
        # crawlers
        if "master_repo" in run["args"]:  # if present then it is non-standard
            return False
        if request.authenticated_userid:
            return True
        now = datetime.now(UTC)
        # Period should be short enough so that it can be
        # served from the api cache!
        if (now - run["last_updated"]).days > 30:
            return False
        return True

    try:
        user, repo = gh.parse_repo(gh.normalize_repo(tests_repo(run)))
    except Exception as e:
        user, repo = gh.parse_repo(tests_repo(run))
        print(f"Unable to normalize_repo: {str(e)}")

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
        '<a class="alert-link" href="{}" target="_blank" rel="noopener noreferrer">base diff</a>'
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
                        Markup("base is not an ancestor of master: {}").format(anchor)
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
                            "base is not the latest common ancestor of new and master"
                        )
            use_3dot_diff = gh.is_ancestor(
                user1=user,
                sha1=run["args"]["resolved_base"],
                sha2=run["args"]["resolved_new"],
                ignore_rate_limit=irl,
            )
        except Exception as e:
            print(f"Exception processing api calls for {run['_id']}: {str(e)}")

    return {
        "run": run,
        "run_args": run_args,
        "page_title": get_page_title(run),
        "approver": request.has_permission("approve_run"),
        "chi2": chi2,
        "totals": "({} active worker{} with {} core{})".format(
            active, ("s" if active != 1 else ""), cores, ("s" if cores != 1 else "")
        ),
        "tasks_shown": show_task != -1 or request.cookies.get("tasks_state") == "Hide",
        "show_task": show_task,
        "follow": follow,
        "can_modify_run": can_modify_run(request, run),
        "same_user": same_user,
        "pt_info": request.rundb.pt_info,
        "document_size": len(bson.BSON.encode(run)),
        "spsa_data": spsa_data,
        "notes": notes,
        "warnings": warnings,
        "use_3dot_diff": use_3dot_diff,
        "allow_github_api_calls": allow_github_api_calls(),
    }


def get_paginated_finished_runs(request):
    username = request.matchdict.get("username", "")
    success_only = request.params.get("success_only", False)
    yellow_only = request.params.get("yellow_only", False)
    ltc_only = request.params.get("ltc_only", False)

    page_param = request.params.get("page", "")
    page_idx = max(0, int(page_param) - 1) if page_param.isdigit() else 0
    page_size = 25

    finished_runs, num_finished_runs = request.rundb.get_finished_runs(
        username=username,
        success_only=success_only,
        yellow_only=yellow_only,
        ltc_only=ltc_only,
        skip=page_idx * page_size,
        limit=page_size,
    )

    query_params = ""
    if success_only:
        query_params += "&success_only=1"
    if yellow_only:
        query_params += "&yellow_only=1"
    if ltc_only:
        query_params += "&ltc_only=1"
    pages = pagination(page_idx, num_finished_runs, page_size, query_params)

    failed_runs = []
    if page_idx == 0:
        for run in finished_runs:
            # Look for failed runs
            if "failed" in run and run["failed"]:
                failed_runs.append(run)

    filters = {
        "success_only": bool(success_only),
        "yellow_only": bool(yellow_only),
        "ltc_only": bool(ltc_only),
    }
    title_suffix = ""
    if filters["success_only"]:
        title_suffix = " - Greens"
    elif filters["yellow_only"]:
        title_suffix = " - Yellows"
    elif filters["ltc_only"]:
        title_suffix = " - LTC"

    return {
        "finished_runs": finished_runs,
        "finished_runs_pages": pages,
        "num_finished_runs": num_finished_runs,
        "failed_runs": failed_runs,
        "page_idx": page_idx,
        "filters": filters,
        "title_suffix": title_suffix,
    }


def _build_toggle_states(request, toggle_names):
    return {name: request.cookies.get(f"{name}_state", "Show") for name in toggle_names}


def _build_run_tables_context(
    request,
    *,
    runs,
    failed_runs,
    finished_runs,
    num_finished_runs,
    finished_runs_pages,
    page_idx,
    username="",
):
    runs = runs or {"pending": [], "active": []}
    pending_runs = [r for r in runs.get("pending", []) if not r.get("approved")]
    paused_runs = [r for r in runs.get("pending", []) if r.get("approved")]
    active_runs = list(runs.get("active", []))
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
            active_runs,
            allow_github_api_calls=False,
        ),
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
        "show_gauge": False,
    }


# === Run lists + homepage ===
def tests_finished(request):
    context = get_paginated_finished_runs(request)
    page_idx = context.get("page_idx", 0)
    title_suffix = context.get("title_suffix", "")
    title_text = (
        f"Finished Tests{title_suffix} - page {page_idx + 1} | Stockfish Testing"
    )
    return {
        **context,
        "query_params": request.query_params,
        "finished_runs": build_run_table_rows(
            context.get("finished_runs", []),
            allow_github_api_calls=False,
        ),
        "failed_runs": build_run_table_rows(
            context.get("failed_runs", []),
            allow_github_api_calls=False,
        ),
        "title": title_suffix,
        "title_text": title_text,
        "show_gauge": False,
    }


def tests_user(request):
    request.response_headerlist.extend(
        (
            ("Cache-Control", "no-store"),
            ("Expires", "0"),
        )
    )
    username = request.matchdict.get("username", "")
    user_data = request.userdb.get_user(username)
    if user_data is None:
        raise StarletteHTTPException(status_code=404)
    is_approver = request.has_permission("approve_run")
    finished_context = get_paginated_finished_runs(request)
    response = {
        **finished_context,
        "username": username,
        "is_approver": is_approver,
    }
    page_param = request.params.get("page", "")
    if not page_param.isdigit() or int(page_param) <= 1:
        runs = request.rundb.aggregate_unfinished_runs(username=username)[0]
        response["run_tables_ctx"] = _build_run_tables_context(
            request,
            runs=runs,
            failed_runs=finished_context.get("failed_runs", []),
            finished_runs=finished_context.get("finished_runs", []),
            num_finished_runs=finished_context.get("num_finished_runs", 0),
            finished_runs_pages=finished_context.get("finished_runs_pages", []),
            page_idx=finished_context.get("page_idx", 0),
            username=username,
        )
    else:
        response["run_tables_ctx"] = _build_run_tables_context(
            request,
            runs=None,
            failed_runs=finished_context.get("failed_runs", []),
            finished_runs=finished_context.get("finished_runs", []),
            num_finished_runs=finished_context.get("num_finished_runs", 0),
            finished_runs_pages=finished_context.get("finished_runs_pages", []),
            page_idx=finished_context.get("page_idx", 0),
            username=username,
        )
    # page 2 and beyond only show finished test results
    return response


def homepage_stats(request):
    (
        _runs,
        pending_hours,
        cores,
        nps,
        games_per_minute,
        _machines_count,
    ) = request.rundb.aggregate_unfinished_runs()
    return {
        "pending_hours": "{:.1f}".format(pending_hours),
        "cores": cores,
        "nps_m": f"{nps / 1000000:.0f}M",
        "games_per_minute": int(games_per_minute),
    }


def homepage_results(request):
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
    run_tables_ctx = _build_run_tables_context(
        request,
        runs=runs,
        failed_runs=finished_context.get("failed_runs", []),
        finished_runs=finished_context.get("finished_runs", []),
        num_finished_runs=finished_context.get("num_finished_runs", 0),
        finished_runs_pages=finished_context.get("finished_runs_pages", []),
        page_idx=finished_context.get("page_idx", 0),
    )
    return {
        **finished_context,
        "runs": runs,
        "run_tables_ctx": run_tables_ctx,
        "machines_count": machines_count,
        "pending_hours": "{:.1f}".format(pending_hours),
        "cores": cores,
        "nps": nps,
        "nps_m": f"{nps / 1000000:.0f}M",
        "games_per_minute": int(games_per_minute),
        "height": f"{machines_count * 37}px",
        "min_height": "37px",
        "max_height": "34.7vh",
    }


def tests(request):
    request.response_headerlist.extend(
        (
            ("Cache-Control", "no-store"),
            ("Expires", "0"),
        )
    )
    page_param = request.params.get("page", "")
    if page_param.isdigit() and int(page_param) > 1:
        # page 2 and beyond only show finished test results
        finished_context = get_paginated_finished_runs(request)
        return {
            **finished_context,
            "run_tables_ctx": _build_run_tables_context(
                request,
                runs=None,
                failed_runs=finished_context.get("failed_runs", []),
                finished_runs=finished_context.get("finished_runs", []),
                num_finished_runs=finished_context.get("num_finished_runs", 0),
                finished_runs_pages=finished_context.get("finished_runs_pages", []),
                page_idx=finished_context.get("page_idx", 0),
            ),
        }

    last_tests = homepage_results(request)

    return {
        **last_tests,
        "machines_shown": request.cookies.get("machines_state") == "Hide",
    }


# === Router registration ===

# Each entry: (view_function, path, config_dict)
# Config keys: renderer, require_csrf, require_primary, request_method, http_cache
# Special: direct=True bypasses _dispatch_view (for pure redirects, no DB/session needed)
_VIEW_ROUTES = [
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
        {"renderer": "workers.html.j2", "require_csrf": True},
    ),
    (upload, "/upload", {"renderer": "nn_upload.html.j2", "require_csrf": True}),
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
    (actions, "/actions", {"renderer": "actions.html.j2"}),
    (user_management, "/user_management", {"renderer": "user_management.html.j2"}),
    (user, "/user/{username}", {"renderer": "user.html.j2"}),
    (user, "/user", {"renderer": "user.html.j2"}),
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
    (tests_elo, "/tests/elo/{id}", {"renderer": "elo_results_fragment.html.j2"}),
    (
        homepage_stats,
        "/tests/stats_summary",
        {"renderer": "homepage_stats_fragment.html.j2"},
    ),
    (tests_stats, "/tests/stats/{id}", {"renderer": "tests_stats.html.j2"}),
    (
        tests_tasks,
        "/tests/tasks/{id}",
        {"renderer": "tasks_fragment.html.j2"},
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


def _make_endpoint(fn, cfg_local):
    async def endpoint(request: Request):
        return await _dispatch_view(
            fn,
            cfg_local,
            request,
            dict(getattr(request, "path_params", {}) or {}),
        )

    return endpoint


def _normalize_methods(methods):
    if methods is None:
        return ["GET", "POST"]
    if isinstance(methods, str):
        return [methods]
    return list(methods)


def _register_view_routes():
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
