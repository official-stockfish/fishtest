"""Build and paginate data for the `/actions` route.

Prepare rows, sorting state, query strings, and username matching for the
actions page.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

if TYPE_CHECKING:
    from starlette.responses import RedirectResponse

from fishtest.views_helpers import (
    _ANONYMOUS_RESULT_LIMIT_HARD,
    _DEFAULT_SORT_ORDER,
    _DEFAULT_TIME_SORT_FIELD,
    _MONGO_INT64_MAX,
    _build_query_string,
    _effective_result_limit,
    _float_param,
    _page_index_from_params,
    _path_url,
    _positive_int_param,
    _ranked_multi_username_merge,
    _sort_matched_usernames,
    _username_priority_map,
    pagination,
    sanitize_quotation_marks,
)

_ACTIONS_DEFAULT_MAX_COUNT_AUTH = 50000
_ACTIONS_SORT_SCOPE_MAX_AUTH = _ACTIONS_DEFAULT_MAX_COUNT_AUTH
_ACTIONS_SORT_SCOPE_MAX_ANON = _ANONYMOUS_RESULT_LIMIT_HARD
_ACTIONS_SORT_LABELS = {
    "time": "Time",
    "event": "Event",
    "source": "Source",
    "target": "Target",
    "comment": "Comment",
}


def _effective_actions_max_count(
    *,
    is_authenticated: bool,
    requested_max_count: int | None,
) -> int | None:
    return _effective_result_limit(
        is_authenticated=is_authenticated,
        requested_limit=requested_max_count,
        anonymous_hard_limit=_ANONYMOUS_RESULT_LIMIT_HARD,
        authenticated_default_limit=_ACTIONS_DEFAULT_MAX_COUNT_AUTH,
    )


def _effective_actions_sort_state(
    params: dict[str, Any],
) -> tuple[str, str]:
    sort_param = (params.get("sort") or _DEFAULT_TIME_SORT_FIELD).strip().lower()
    if sort_param not in _ACTIONS_SORT_LABELS:
        sort_param = _DEFAULT_TIME_SORT_FIELD

    order_param = (params.get("order") or "").strip().lower()
    if order_param not in {"asc", "desc"}:
        order_param = (
            _DEFAULT_SORT_ORDER if sort_param == _DEFAULT_TIME_SORT_FIELD else "asc"
        )

    return sort_param, order_param


def _actions_sort_scope_max_count(
    *,
    is_authenticated: bool,
    max_count: int | None,
) -> int:
    scope_cap = (
        _ACTIONS_SORT_SCOPE_MAX_AUTH
        if is_authenticated
        else _ACTIONS_SORT_SCOPE_MAX_ANON
    )
    if max_count is None:
        return scope_cap
    return min(max_count, scope_cap)


def _build_actions_time_url(  # noqa: PLR0913
    *,
    search_action: str,
    username: str,
    text: str,
    before: float | None,
    run_id: str,
    sort_param: str,
    order_param: str,
) -> str:
    time_query = {
        "max_count": "1",
        "action": search_action,
        "user": username,
        "text": text,
        "before": before or "",
        "run_id": run_id,
        "sort": sort_param,
        "order": order_param,
    }
    return "/actions?" + urlencode(time_query)


def _build_action_row(  # noqa: PLR0913
    action: dict[str, Any],
    request: Any,  # noqa: ANN401
    *,
    search_action: str,
    username: str,
    text: str,
    run_id: str,
    sort_param: str,
    order_param: str,
) -> dict[str, Any]:
    action = dict(action)
    action.setdefault("action", "")
    action.setdefault("username", "")

    time_value = action.get("time")
    if time_value is None:
        time_label = ""
    else:
        time_label = datetime.fromtimestamp(float(time_value), UTC).strftime(
            "%y-%m-%d %H:%M:%S",
        )
        time_label = time_label.replace("-", "\u2011", 2)

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
            "time_url": _build_actions_time_url(
                search_action=search_action,
                username=username,
                text=text,
                before=time_value,
                run_id=run_id,
                sort_param=sort_param,
                order_param=order_param,
            ),
            "event": action.get("action", ""),
            "agent_name": agent_name,
            "agent_url": agent_url or None,
            "target_name": target_name,
            "target_url": target_url or None,
            "message": action.get("message", ""),
        },
    )
    return action


def _action_row_sort_value(
    action_row: dict[str, Any],
    sort_param: str,
) -> Any:  # noqa: ANN401
    if sort_param == "time":
        return float(action_row.get("time") or 0)
    if sort_param == "event":
        return str(action_row.get("event") or "").lower()
    if sort_param == "source":
        return str(action_row.get("agent_name") or "").lower()
    if sort_param == "target":
        return str(action_row.get("target_name") or "").lower()
    if sort_param == "comment":
        return str(action_row.get("message") or "").lower()
    return float(action_row.get("time") or 0)


def _sort_action_rows(
    action_rows: list[dict[str, Any]],
    *,
    sort_param: str,
    order_param: str,
    username_priority: dict[str, int] | None = None,
) -> None:
    # Keep a deterministic recent-first tie-break so equal values do not jump
    # between requests.
    action_rows.sort(
        key=lambda row: (float(row.get("time") or 0), str(row.get("_id") or "")),
        reverse=True,
    )
    action_rows.sort(
        key=lambda row: _action_row_sort_value(row, sort_param),
        reverse=(order_param == "desc"),
    )
    if username_priority:
        action_rows.sort(
            key=lambda row: (
                username_priority.get(row.get("username", ""), len(username_priority)),
                str(row.get("username", "")).lower(),
            ),
        )


def _actions_sort_summary(
    *,
    sort_param: str,
    order_param: str,
    sorted_count: int,
    scope_cap: int,
) -> str:
    if sort_param == _DEFAULT_TIME_SORT_FIELD and order_param == _DEFAULT_SORT_ORDER:
        return ""

    direction = "ascending" if order_param == "asc" else "descending"
    label = _ACTIONS_SORT_LABELS[sort_param]
    if sorted_count >= scope_cap:
        return (
            f"Sorted by {label} {direction}"
            f" across the first {scope_cap}"
            " matching actions."
        )
    return f"Sorted by {label} {direction} across {sorted_count} matching actions."


def _actions_query_suffix(  # noqa: PLR0913
    *,
    username: str = "",
    search_action: str = "",
    text: str = "",
    sort_param: str = _DEFAULT_TIME_SORT_FIELD,
    order_param: str = _DEFAULT_SORT_ORDER,
    max_count: int | None = None,
    before: float | None = None,
    run_id: str = "",
    page: int | None = None,
) -> str:
    return _build_query_string(
        [
            ("user", username or None),
            ("action", search_action or None),
            ("text", text or None),
            ("sort", sort_param if sort_param != _DEFAULT_TIME_SORT_FIELD else None),
            (
                "order",
                order_param
                if sort_param != _DEFAULT_TIME_SORT_FIELD
                or order_param != _DEFAULT_SORT_ORDER
                else None,
            ),
            ("max_count", max_count if max_count is not None else None),
            ("before", before if before is not None else None),
            ("run_id", run_id or None),
            ("page", page if page not in (None, "", 1) else None),
        ],
    )


def _matching_action_usernames(
    actiondb: Any,  # noqa: ANN401
    query: str,
) -> list[str]:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    get_action_usernames = getattr(actiondb, "get_action_usernames", None)
    if not callable(get_action_usernames):
        return [query.strip()]

    def _matches_from_cached_usernames() -> list[str]:
        matches = [
            username
            for username in get_action_usernames()
            if normalized_query in username.lower()
        ]
        return _sort_matched_usernames(matches, query)

    matches = _matches_from_cached_usernames()
    if matches:
        return matches

    cache_clear = getattr(get_action_usernames, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()
        matches = _matches_from_cached_usernames()

    return matches


def actions(  # noqa: PLR0915
    request: Any,  # noqa: ANN401
    *,
    page_size: int,
) -> dict[str, Any] | RedirectResponse:
    """Build the /actions page context.

    Returns a RedirectResponse for out-of-range pages, or a dict of
    template context for the actions content fragment.
    """
    from starlette.responses import RedirectResponse  # noqa: PLC0415

    is_authenticated = request.authenticated_userid is not None

    search_action = request.params.get("action", "")
    username = request.params.get("user", "")
    text = sanitize_quotation_marks(request.params.get("text", ""))
    before = _float_param(request.params.get("before", None))
    requested_max_count = _positive_int_param(
        request.params.get("max_count", None),
        max_value=_MONGO_INT64_MAX,
    )
    run_id = request.params.get("run_id", "")
    sort_param, order_param = _effective_actions_sort_state(request.params)

    max_count = _effective_actions_max_count(
        is_authenticated=is_authenticated,
        requested_max_count=requested_max_count,
    )

    page_param = request.params.get("page", "")
    page_idx = _page_index_from_params(request.params)

    use_capped_sort_scope = not (
        sort_param == _DEFAULT_TIME_SORT_FIELD and order_param == _DEFAULT_SORT_ORDER
    )
    sort_scope_max_count = _actions_sort_scope_max_count(
        is_authenticated=is_authenticated,
        max_count=max_count,
    )
    matched_usernames = _matching_action_usernames(request.actiondb, username)
    username_priority = (
        _username_priority_map(matched_usernames)
        if username and len(matched_usernames) > 1
        else None
    )

    if username and not matched_usernames:
        raw_actions = []
        num_actions = 0
        actions_rows = []
    elif (
        username_priority
        and sort_param == _DEFAULT_TIME_SORT_FIELD
        and order_param == _DEFAULT_SORT_ORDER
    ):
        ranked_actions = _ranked_multi_username_merge(
            usernames=matched_usernames,
            fetch_fn=lambda u, window, cap: request.actiondb.get_actions(
                username=u,
                text=text,
                skip=0,
                limit=window,
                utc_before=before,
                run_id=run_id,
                max_count=cap,
            ),
            username_field="username",
            time_field="time",
            skip=page_idx * page_size,
            limit=page_size,
            max_count=max_count,
        )
        if ranked_actions is None:
            raw_actions, num_actions = request.actiondb.get_actions(
                usernames=matched_usernames,
                action=search_action,
                text=text,
                skip=0,
                limit=sort_scope_max_count,
                utc_before=before,
                max_count=sort_scope_max_count,
                run_id=run_id,
            )
            actions_rows = [
                _build_action_row(
                    action,
                    request,
                    search_action=search_action,
                    username=username,
                    text=text,
                    run_id=run_id,
                    sort_param=sort_param,
                    order_param=order_param,
                )
                for action in raw_actions
            ]
            num_actions = len(actions_rows)
            _sort_action_rows(
                actions_rows,
                sort_param=sort_param,
                order_param=order_param,
                username_priority=username_priority,
            )
            start = page_idx * page_size
            actions_rows = actions_rows[start : start + page_size]
        else:
            raw_actions, num_actions = ranked_actions
            actions_rows = [
                _build_action_row(
                    action,
                    request,
                    search_action=search_action,
                    username=username,
                    text=text,
                    run_id=run_id,
                    sort_param=sort_param,
                    order_param=order_param,
                )
                for action in raw_actions
            ]
    elif use_capped_sort_scope:
        raw_actions, num_actions = request.actiondb.get_actions(
            usernames=matched_usernames if username else None,
            action=search_action,
            text=text,
            skip=0,
            limit=sort_scope_max_count,
            utc_before=before,
            max_count=sort_scope_max_count,
            run_id=run_id,
        )
        actions_rows = [
            _build_action_row(
                action,
                request,
                search_action=search_action,
                username=username,
                text=text,
                run_id=run_id,
                sort_param=sort_param,
                order_param=order_param,
            )
            for action in raw_actions
        ]
        _sort_action_rows(
            actions_rows,
            sort_param=sort_param,
            order_param=order_param,
            username_priority=username_priority,
        )
        num_actions = len(actions_rows)
        start = page_idx * page_size
        actions_rows = actions_rows[start : start + page_size]
    else:
        raw_actions, num_actions = request.actiondb.get_actions(
            usernames=matched_usernames if username else None,
            action=search_action,
            text=text,
            skip=page_idx * page_size,
            limit=page_size,
            utc_before=before,
            max_count=max_count,
            run_id=run_id,
        )
        actions_rows = [
            _build_action_row(
                action,
                request,
                search_action=search_action,
                username=username,
                text=text,
                run_id=run_id,
                sort_param=sort_param,
                order_param=order_param,
            )
            for action in raw_actions
        ]

    # If the requested page is out of range, redirect to the last page.
    if num_actions > 0:
        last_page = (num_actions - 1) // page_size + 1
        if page_param.isdigit() and int(page_param) > last_page:
            redirect_query = dict(request.params)
            redirect_query["page"] = str(last_page)
            if max_count is not None:
                redirect_query["max_count"] = str(max_count)
            redirect_query["sort"] = sort_param
            redirect_query["order"] = order_param
            return RedirectResponse(
                url=_path_url(request) + "?" + urlencode(redirect_query),
                status_code=302,
            )

    query_params = _actions_query_suffix(
        username=username,
        search_action=search_action,
        text=text,
        sort_param=sort_param,
        order_param=order_param,
        max_count=max_count,
        before=before,
        run_id=run_id,
    )

    pages = pagination(page_idx, num_actions, page_size, query_params)

    return {
        "actions": actions_rows,
        "visible_actions": len(actions_rows),
        "pages": pages,
        "num_actions": num_actions,
        "page_size": page_size,
        "current_page": page_idx + 1,
        "run_id_filter": run_id,
        "max_count": max_count,
        "sort": sort_param,
        "order": order_param,
        "sort_summary": _actions_sort_summary(
            sort_param=sort_param,
            order_param=order_param,
            sorted_count=num_actions,
            scope_cap=sort_scope_max_count,
        ),
        "filters": {
            "action": search_action,
            "username": username,
            "text": text,
            "run_id": run_id,
        },
    }
