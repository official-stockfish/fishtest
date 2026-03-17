"""Build the finished-runs query and pagination contract.

Prepare canonical query strings, pagination state, username matching, and the
``get_paginated_finished_runs`` entry point.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from starlette.responses import RedirectResponse

from fishtest.http.settings import (
    ACTIONS_PAGE_SIZE,
    FINISHED_FILTER_MAX_COUNT_ANON,
    FINISHED_FILTER_MAX_COUNT_AUTH,
)
from fishtest.views_helpers import (
    _DEFAULT_SORT_ORDER,
    _DEFAULT_TIME_SORT_FIELD,
    _MONGO_INT64_MAX,
    _build_query_string,
    _effective_result_limit,
    _host_url,
    _page_index_from_params,
    _path_url,
    _positive_int_param,
    _ranked_multi_username_merge,
    _sort_matched_usernames,
    _username_priority_map,
    pagination,
    sanitize_quotation_marks,
)

_FINISHED_MAX_COUNT_QUERY_PARAM = "max_count"
_FINISHED_SEARCH_MODE = "search"


def _matching_finished_usernames(
    userdb: Any,  # noqa: ANN401
    username_query: str,
) -> list[str] | None:
    normalized_query = username_query.strip().lower()
    if not normalized_query:
        return None

    get_usernames = getattr(userdb, "get_usernames", None)
    if not callable(get_usernames):
        return [username_query.strip()]

    def _matches_from_cached_usernames() -> list[str]:
        matches = [
            candidate
            for candidate in get_usernames()
            if normalized_query in candidate.lower()
        ]
        return _sort_matched_usernames(matches, username_query)

    matches = _matches_from_cached_usernames()
    if matches:
        return matches

    cache_clear = getattr(get_usernames, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()
        matches = _matches_from_cached_usernames()

    return matches


def _finished_filters_active(
    *,
    username_query: str,
    text: str,
) -> bool:
    return bool(username_query or text)


def _effective_finished_max_count(
    *,
    is_authenticated: bool,
    requested_max_count: int | None,
    filters_active: bool,
) -> int | None:
    if not filters_active:
        return requested_max_count
    return _effective_result_limit(
        is_authenticated=is_authenticated,
        requested_limit=requested_max_count,
        anonymous_hard_limit=FINISHED_FILTER_MAX_COUNT_ANON,
        authenticated_default_limit=FINISHED_FILTER_MAX_COUNT_AUTH,
    )


def _finished_search_mode_enabled(params: dict[str, Any]) -> bool:
    return str(params.get("mode", "")).strip().lower() == _FINISHED_SEARCH_MODE


def _finished_route_url(request: Any) -> str:  # noqa: ANN401
    return f"{_host_url(request)}/tests/finished"


def _requested_finished_max_count(
    params: dict[str, Any],
) -> int | None:
    return _positive_int_param(
        params.get(_FINISHED_MAX_COUNT_QUERY_PARAM),
        max_value=_MONGO_INT64_MAX,
    )


def _finished_canonical_query_string(  # noqa: PLR0913
    params: dict[str, Any],
    *,
    max_count: int | None = None,
    search_mode: bool = False,
    username_query: str | None = None,
    text: str | None = None,
    page: int | None = None,
) -> str:
    if search_mode:
        success_only = False
        yellow_only = False
        ltc_only = False
    else:
        success_only = bool(params.get("success_only", False))
        yellow_only = bool(params.get("yellow_only", False))
        ltc_only = bool(params.get("ltc_only", False))
    if username_query is None:
        username_query = str(params.get("user", "")).strip()
    if text is None:
        text = sanitize_quotation_marks(
            str(
                params.get(
                    "text",
                    params.get("info_regex", ""),
                ),
            ),
        ).strip()
    if page is None:
        page_param = str(params.get("page", "")).strip()
        page = int(page_param) if page_param.isdigit() else None

    return _build_query_string(
        _finished_query_pairs(
            success_only=success_only,
            yellow_only=yellow_only,
            ltc_only=ltc_only,
            search_mode=search_mode,
            username_query=username_query,
            text=text,
            max_count=max_count,
            sort_field=_DEFAULT_TIME_SORT_FIELD,
            sort_order=_DEFAULT_SORT_ORDER,
            page=page,
        ),
        leading="?",
    )


def _finished_query_pairs(  # noqa: PLR0913
    *,
    success_only: bool = False,
    yellow_only: bool = False,
    ltc_only: bool = False,
    search_mode: bool = False,
    username_query: str = "",
    text: str = "",
    max_count: int | None = None,
    sort_field: str = _DEFAULT_TIME_SORT_FIELD,
    sort_order: str = _DEFAULT_SORT_ORDER,
    page: int | None = None,
) -> list[tuple[str, str | int | None]]:
    return [
        ("mode", _FINISHED_SEARCH_MODE if search_mode else None),
        (
            _FINISHED_MAX_COUNT_QUERY_PARAM,
            max_count if max_count is not None else None,
        ),
        ("sort", sort_field),
        ("order", sort_order),
        ("success_only", "1" if success_only else None),
        ("yellow_only", "1" if yellow_only else None),
        ("ltc_only", "1" if ltc_only else None),
        ("user", username_query or None),
        ("text", text or None),
        ("page", page if page not in (None, "", 1) else None),
    ]


def _finished_query_suffix(  # noqa: PLR0913
    *,
    success_only: bool = False,
    yellow_only: bool = False,
    ltc_only: bool = False,
    search_mode: bool = False,
    username_query: str = "",
    text: str = "",
    max_count: int | None = None,
    sort_field: str = _DEFAULT_TIME_SORT_FIELD,
    sort_order: str = _DEFAULT_SORT_ORDER,
    page: int | None = None,
) -> str:
    return _build_query_string(
        _finished_query_pairs(
            success_only=success_only,
            yellow_only=yellow_only,
            ltc_only=ltc_only,
            search_mode=search_mode,
            username_query=username_query,
            text=text,
            max_count=max_count,
            sort_field=sort_field,
            sort_order=sort_order,
            page=page,
        ),
    )


def _finished_tab_query_string(  # noqa: PLR0913
    *,
    tab: str | None = None,
    search_mode: bool = False,
    username_query: str = "",
    text: str = "",
    max_count: int | None = None,
    sort_field: str = _DEFAULT_TIME_SORT_FIELD,
    sort_order: str = _DEFAULT_SORT_ORDER,
) -> str:
    return _build_query_string(
        _finished_query_pairs(
            success_only=tab == "success_only",
            yellow_only=tab == "yellow_only",
            ltc_only=tab == "ltc_only",
            search_mode=search_mode,
            username_query=username_query,
            text=text,
            max_count=max_count,
            sort_field=sort_field,
            sort_order=sort_order,
        ),
        leading="?",
    )


def get_paginated_finished_runs(  # noqa: C901, PLR0912, PLR0915
    request: Any,  # noqa: ANN401
    *,
    username: str | None = None,
    search_mode: bool = False,
) -> dict[str, Any] | RedirectResponse:
    """Build the paginated finished-runs context.

    Returns a RedirectResponse when query parameters need canonical
    normalization, or a dict of template context otherwise.
    """
    if username is None:
        username = request.matchdict.get("username", "")
    if not username:
        search_mode = search_mode or _finished_search_mode_enabled(request.params)
    is_authenticated = request.authenticated_userid is not None
    success_only = False if search_mode else request.params.get("success_only", False)
    yellow_only = False if search_mode else request.params.get("yellow_only", False)
    ltc_only = False if search_mode else request.params.get("ltc_only", False)
    username_query = "" if username else str(request.params.get("user", "")).strip()
    text = (
        ""
        if username
        else sanitize_quotation_marks(
            str(
                request.params.get(
                    "text",
                    request.params.get("info_regex", ""),
                ),
            ),
        ).strip()
    )
    requested_max_count = _requested_finished_max_count(request.params)

    page_param = request.params.get("page", "")
    page_idx = _page_index_from_params(request.params)
    page_size = ACTIONS_PAGE_SIZE
    sort_field = _DEFAULT_TIME_SORT_FIELD
    sort_order = _DEFAULT_SORT_ORDER

    if not username and not search_mode and (username_query or text):
        return RedirectResponse(
            url=_finished_route_url(request)
            + _finished_canonical_query_string(
                request.params,
                search_mode=True,
                username_query=username_query,
                text=text,
            ),
            status_code=302,
        )

    if search_mode and any(
        request.params.get(flag, False)
        for flag in ("success_only", "yellow_only", "ltc_only")
    ):
        return RedirectResponse(
            url=_finished_route_url(request)
            + _finished_canonical_query_string(
                request.params,
                search_mode=True,
                username_query=username_query,
                text=text,
            ),
            status_code=302,
        )

    matched_usernames = _matching_finished_usernames(request.userdb, username_query)
    filters_active = search_mode or _finished_filters_active(
        username_query=username_query,
        text=text,
    )

    if (
        not search_mode
        and not filters_active
        and _FINISHED_MAX_COUNT_QUERY_PARAM in request.params
    ):
        return RedirectResponse(
            url=_path_url(request)
            + _finished_canonical_query_string(
                request.params,
                max_count=None,
                search_mode=False,
            ),
            status_code=302,
        )

    max_count = _effective_finished_max_count(
        is_authenticated=is_authenticated,
        requested_max_count=requested_max_count,
        filters_active=filters_active,
    )
    exposed_max_count = max_count if search_mode else None

    if username_query and not matched_usernames:
        finished_runs = []
        num_finished_runs = 0
    elif username_query and matched_usernames and len(matched_usernames) > 1:
        ranked_finished_runs = _ranked_multi_username_merge(
            usernames=matched_usernames,
            fetch_fn=lambda u, window, cap: request.rundb.get_finished_runs(
                username=u,
                text=text,
                success_only=success_only,
                yellow_only=yellow_only,
                ltc_only=ltc_only,
                skip=0,
                limit=window,
                max_count=cap,
            ),
            username_field="args.username",
            time_field="last_updated",
            skip=page_idx * page_size,
            limit=page_size,
            max_count=max_count,
        )
        if ranked_finished_runs is None:
            finished_runs, _ = request.rundb.get_finished_runs(
                username=username,
                usernames=matched_usernames,
                text=text,
                success_only=success_only,
                yellow_only=yellow_only,
                ltc_only=ltc_only,
                skip=0,
                limit=max_count,
                max_count=max_count,
            )
            username_priority = _username_priority_map(matched_usernames)
            finished_runs.sort(
                key=lambda run: (
                    username_priority.get(
                        run.get("args", {}).get("username", ""),
                        len(username_priority),
                    ),
                    -(
                        run.get("last_updated") or datetime.min.replace(tzinfo=UTC)
                    ).timestamp(),
                    str(run.get("_id", "")),
                ),
            )
            num_finished_runs = len(finished_runs)
            start = page_idx * page_size
            finished_runs = finished_runs[start : start + page_size]
        else:
            finished_runs, num_finished_runs = ranked_finished_runs
    else:
        finished_runs, num_finished_runs = request.rundb.get_finished_runs(
            username=username,
            usernames=matched_usernames,
            text=text,
            success_only=success_only,
            yellow_only=yellow_only,
            ltc_only=ltc_only,
            skip=page_idx * page_size,
            limit=page_size,
            max_count=max_count,
        )

    query_params = _finished_query_suffix(
        search_mode=search_mode,
        success_only=success_only,
        yellow_only=yellow_only,
        ltc_only=ltc_only,
        username_query=username_query,
        text=text,
        max_count=exposed_max_count,
        sort_field=sort_field,
        sort_order=sort_order,
    )
    pages = pagination(page_idx, num_finished_runs, page_size, query_params)

    if num_finished_runs > 0:
        last_page = (num_finished_runs - 1) // page_size + 1
        if page_param.isdigit() and int(page_param) > last_page:
            redirect_query = dict(request.params)
            redirect_query["page"] = str(last_page)
            if exposed_max_count is not None:
                redirect_query[_FINISHED_MAX_COUNT_QUERY_PARAM] = str(max_count)
            else:
                redirect_query.pop(_FINISHED_MAX_COUNT_QUERY_PARAM, None)
            return RedirectResponse(
                url=_finished_route_url(request) + "?" + urlencode(redirect_query),
                status_code=302,
            )

    failed_runs = []
    if page_idx == 0:
        failed_runs = [run for run in finished_runs if run.get("failed")]

    filters = {
        "success_only": bool(success_only),
        "yellow_only": bool(yellow_only),
        "ltc_only": bool(ltc_only),
        "username_query": username_query,
        "text": text,
        "max_count": exposed_max_count,
        "mode": "search" if search_mode else "navigation",
        "all_query_string": _finished_tab_query_string(
            search_mode=search_mode,
            username_query=username_query,
            text=text,
            max_count=exposed_max_count,
            sort_field=sort_field,
            sort_order=sort_order,
        ),
        "green_query_string": _finished_tab_query_string(
            tab="success_only",
            search_mode=search_mode,
            username_query=username_query,
            text=text,
            max_count=exposed_max_count,
            sort_field=sort_field,
            sort_order=sort_order,
        ),
        "yellow_query_string": _finished_tab_query_string(
            tab="yellow_only",
            search_mode=search_mode,
            username_query=username_query,
            text=text,
            max_count=exposed_max_count,
            sort_field=sort_field,
            sort_order=sort_order,
        ),
        "ltc_query_string": _finished_tab_query_string(
            tab="ltc_only",
            search_mode=search_mode,
            username_query=username_query,
            text=text,
            max_count=exposed_max_count,
            sort_field=sort_field,
            sort_order=sort_order,
        ),
        "filtered_query_suffix": _finished_query_suffix(
            search_mode=search_mode,
            username_query=username_query,
            text=text,
            max_count=exposed_max_count,
            sort_field=sort_field,
            sort_order=sort_order,
        ),
    }
    title_suffix = ""
    if not search_mode and filters["success_only"]:
        title_suffix = " - Greens"
    elif not search_mode and filters["yellow_only"]:
        title_suffix = " - Yellows"
    elif not search_mode and filters["ltc_only"]:
        title_suffix = " - LTC"

    return {
        "finished_runs": finished_runs,
        "finished_runs_pages": pages,
        "num_finished_runs": num_finished_runs,
        "visible_finished_runs": len(finished_runs),
        "finished_page_size": page_size,
        "failed_runs": failed_runs,
        "page_idx": page_idx,
        "filters": filters,
        "title_suffix": title_suffix,
        "search_mode": search_mode,
    }
