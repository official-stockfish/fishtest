"""Jinja2 template rendering helpers for the FastAPI UI."""

from __future__ import annotations

import base64
import copy
import datetime
import hashlib
import math
import urllib.parse
from dataclasses import dataclass
from functools import lru_cache
from os import environ
from pathlib import Path
from typing import TYPE_CHECKING, Final

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from starlette.templating import Jinja2Templates

import fishtest
import fishtest.github_api as gh
from fishtest.http import template_helpers as helpers
from fishtest.http.settings import (
    POLL_BATCH_HOMEPAGE_S,
    POLL_ELO_DETAIL_S,
    POLL_LIVE_ELO_S,
    POLL_MACHINES_HOMEPAGE_S,
    POLL_RATE_LIMITS_SERVER_S,
    POLL_TASKS_DETAIL_S,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.background import BackgroundTask
    from starlette.requests import Request
    from starlette.responses import Response

TEMPLATES_DIR_ENV: Final[str] = "FISHTEST_JINJA_TEMPLATES_DIR"
_MISSING_REQUEST_ERROR: Final[str] = "context must include Request under 'request'"
_STATIC_DIR: Path = Path(__file__).resolve().parents[1] / "static"
_STATIC_URL_PARAM: Final[str] = "x"
_STATIC_TOKEN_CACHE_MAX: int = 1024


def templates_dir() -> Path:
    """Return the Jinja2 templates directory path."""
    raw = environ.get(TEMPLATES_DIR_ENV, "").strip()
    if raw:
        return Path(raw).expanduser()

    # Package-relative resolution works for both source checkouts and wheels.
    return Path(__file__).resolve().parents[1] / "templates"


@lru_cache(maxsize=_STATIC_TOKEN_CACHE_MAX)
def _static_file_token(rel_path: str) -> str | None:
    """Return a cache-buster token for a static file."""
    rel_path = rel_path.replace("\\", "/")
    rel_obj = Path(rel_path)
    if rel_obj.is_absolute() or ".." in rel_obj.parts:
        return None

    file_path = (_STATIC_DIR / rel_path).resolve()
    try:
        file_path.relative_to(_STATIC_DIR)
    except ValueError:
        return None
    try:
        content = file_path.read_bytes()
    except OSError:
        return None

    return (
        base64.urlsafe_b64encode(hashlib.sha384(content).digest())
        .decode("utf-8")
        .rstrip("=")
    )


def static_url(spec: str) -> str:
    """Map a legacy asset spec to the FastAPI static mount."""
    prefix = "fishtest:static/"
    rel_path = spec.removeprefix(prefix)
    rel_path = rel_path.lstrip("/")

    url = "/static/" + rel_path
    token = _static_file_token(rel_path)
    if token is None:
        return url
    return f"{url}?{_STATIC_URL_PARAM}={token}"


def default_environment() -> Environment:
    """Return a Jinja2 environment bound to the Jinja2 templates directory."""
    env = Environment(
        loader=FileSystemLoader(str(templates_dir())),
        autoescape=select_autoescape(["html", "xml", "j2"]),
        undefined=StrictUndefined,
        extensions=["jinja2.ext.do"],
    )
    env.filters["urlencode"] = helpers.urlencode
    env.filters["split"] = lambda value, sep=None, maxsplit=-1: str(value).split(
        sep,
        maxsplit,
    )
    env.filters["string"] = str
    env.globals.update(
        {
            "copy": copy,
            "datetime": datetime,
            "diff_url": helpers.diff_url,
            "display_residual": helpers.display_residual,
            "fishtest": fishtest,
            "float": float,
            "format_bounds": helpers.format_bounds,
            "format_date": helpers.format_date,
            "format_group": helpers.format_group,
            "format_results": helpers.format_results,
            "format_time_ago": helpers.format_time_ago,
            "gh": gh,
            "is_active_sprt_ltc": helpers.is_active_sprt_ltc,
            "is_elo_pentanomial_run": helpers.is_elo_pentanomial_run,
            "list_to_string": helpers.list_to_string,
            "math": math,
            "pdf_to_string": helpers.pdf_to_string,
            "results_pre_attrs": helpers.results_pre_attrs,
            "nelo_pentanomial_summary": helpers.nelo_pentanomial_summary,
            "run_tables_prefix": helpers.run_tables_prefix,
            "t_conf": helpers.t_conf,
            "tests_run_setup": helpers.tests_run_setup,
            "tests_repo": helpers.tests_repo,
            "urllib": urllib.parse,
            "worker_name": helpers.worker_name,
            "static_url": static_url,
            "poll": {
                "batch_homepage": POLL_BATCH_HOMEPAGE_S,
                "elo_detail": POLL_ELO_DETAIL_S,
                "tasks_detail": POLL_TASKS_DETAIL_S,
                "machines_homepage": POLL_MACHINES_HOMEPAGE_S,
                "live_elo": POLL_LIVE_ELO_S,
                "rate_limits_server": POLL_RATE_LIMITS_SERVER_S,
            },
        },
    )
    return env


def default_templates() -> Jinja2Templates:
    """Return a Starlette Jinja2Templates instance with the custom environment."""
    env = default_environment()
    return Jinja2Templates(env=env)


@dataclass(frozen=True)
class TemplateResponseOptions:
    """Options for building a Jinja2 template response."""

    status_code: int = 200
    headers: Mapping[str, str] | None = None
    media_type: str | None = None
    background: BackgroundTask | None = None


def render_template_response(
    *,
    templates: Jinja2Templates,
    request: Request,
    template_name: str,
    context: Mapping[str, object],
    options: TemplateResponseOptions | None = None,
) -> Response:
    """Render a template and return a Starlette TemplateResponse."""
    opts = options or TemplateResponseOptions()
    context_dict = dict(context)
    if "request" not in context_dict:
        raise ValueError(_MISSING_REQUEST_ERROR)
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context=context_dict,
        status_code=opts.status_code,
        headers=opts.headers,
        media_type=opts.media_type,
        background=opts.background,
    )
