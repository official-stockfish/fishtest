"""Build the `/tests/machines` filtering and pagination contract.

Normalize rows, apply filtering and sorting, manage UI-state cookies, and
support the ``tests_machines`` entry point.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote, unquote

from fishtest.http.settings import (
    MACHINES_PAGE_SIZE,
    UI_STATE_COOKIE_MAX_AGE_SECONDS,
)
from fishtest.util import format_time_ago, worker_name
from fishtest.views_helpers import (
    _build_query_string,
    _clamp_page_index,
    _is_truthy_param,
    _normalize_sort_order,
    _page_index_from_params,
    pagination,
)

_MACHINES_SORT_MAP = {
    "last_active": ("last_updated", True),
    "machine": ("username", False),
    "cores": ("concurrency", True),
    "uuid": ("unique_key", False),
    "mnps": ("nps", True),
    "ram": ("max_memory", True),
    "system": ("uname", False),
    "arch": ("worker_arch", False),
    "compiler": ("compiler", False),
    "python": ("python", False),
    "worker": ("version", True),
    "running_on": ("run_label", False),
}
_MACHINES_DEFAULT_SORT = "last_active"
_MACHINES_PAGE_SIZE = MACHINES_PAGE_SIZE
_MACHINES_FILTER_FIELDS = (
    "username",
    "concurrency",
    "unique_key",
    "nps_m",
    "max_memory",
    "system",
    "worker_arch",
    "compiler_label",
    "python_label",
    "version_label",
    "run_label",
    "last_active_label",
)

_MACHINES_CASEFOLD_SORT_KEYS = {
    "username",
    "uname",
    "worker_arch",
    "run_label",
}


def _clip_long(text: str, max_length: int = 20) -> str:
    return text if len(text) <= max_length else text[:max_length] + "..."


def _machines_version_parts(values: list[Any] | None) -> tuple[int, ...]:
    parts = []
    for value in values or []:
        try:
            parts.append(int(value))
        except TypeError, ValueError:
            break
    return tuple(parts)


def _normalize_machine_row(machine: dict[str, Any]) -> dict[str, Any]:
    gcc_values = machine.get("gcc_version", [])
    python_values = machine.get("python_version", [])
    compiler = machine.get("compiler", "g++")
    unique_key = machine.get("unique_key", "")

    gcc_version = ".".join(str(value) for value in gcc_values)
    python_version = ".".join(str(value) for value in python_values)

    worker_short = unique_key.split("-")[0]
    run_data = machine["run"]
    task_id = str(machine["task_id"])
    run_id = str(run_data["_id"])
    branch = run_data["args"]["new_tag"]
    last_updated = machine["last_updated"]

    return {
        "username": machine["username"],
        "country_code": machine.get("country_code", "").lower(),
        "concurrency": machine["concurrency"],
        "unique_key": unique_key,
        "worker_url": f"/workers/{worker_name(machine, short=True)}",
        "worker_short": worker_short,
        "nps": machine.get("nps", 0),
        "nps_m": f"{machine.get('nps', 0) / 1000000:.2f}",
        "max_memory": machine["max_memory"],
        "system": machine["uname"],
        "uname": machine["uname"],
        "worker_arch": machine["worker_arch"],
        "compiler": compiler,
        "compiler_version": _machines_version_parts(gcc_values),
        "compiler_label": f"{compiler} {gcc_version}",
        "python": python_version,
        "python_version": _machines_version_parts(python_values),
        "python_label": python_version,
        "version": machine.get("version", 0),
        "version_label": str(machine.get("version", ""))
        + "*" * machine.get("modified", False),
        "run_url": f"/tests/view/{run_id}?show_task={task_id}",
        "run_label": f"{_clip_long(branch)}/{task_id}",
        "last_active_label": format_time_ago(last_updated),
        "last_active_sort": -last_updated.timestamp(),
        "last_updated": last_updated,
    }


def _machine_filter_state(
    query_source: dict[str, Any],
    *,
    authenticated_username: str | None,
    use_cookies: bool = False,
    query_key: str = "q",
    my_workers_key: str = "my_workers",
) -> dict[str, Any]:
    query_filter = query_source.get(query_key, "")
    if use_cookies:
        query_filter = unquote(str(query_filter))
    query_filter = str(query_filter).strip()

    my_workers = _is_truthy_param(query_source.get(my_workers_key, ""))
    if not authenticated_username:
        my_workers = False

    return {
        "query_filter": query_filter,
        "my_workers": my_workers,
        "filters_active": bool(query_filter) or my_workers,
    }


def _filter_machine_rows(
    normalized_rows: list[dict[str, Any]],
    *,
    query_filter: str,
    my_workers: bool,
    authenticated_username: str | None,
) -> list[dict[str, Any]]:
    filtered_rows = list(normalized_rows)
    if my_workers and authenticated_username:
        filtered_rows = [
            machine
            for machine in filtered_rows
            if machine.get("username") == authenticated_username
        ]
    if query_filter:
        query_filter_lower = query_filter.lower()
        filtered_rows = [
            machine
            for machine in filtered_rows
            if any(
                query_filter_lower in str(machine.get(field, "")).lower()
                for field in _MACHINES_FILTER_FIELDS
            )
        ]
    return filtered_rows


def _normalized_machine_rows(request: Any) -> list[dict[str, Any]]:  # noqa: ANN401
    return [_normalize_machine_row(machine) for machine in request.rundb.get_machines()]


def _filtered_machine_count(
    request: Any,  # noqa: ANN401
    *,
    query_filter: str,
    my_workers: bool,
    authenticated_username: str | None,
) -> int:
    filtered_rows = _filter_machine_rows(
        _normalized_machine_rows(request),
        query_filter=query_filter,
        my_workers=my_workers,
        authenticated_username=authenticated_username,
    )
    return len(filtered_rows)


def _machines_sort_value(  # noqa: PLR0911
    machine_row: dict[str, Any],
    sort_key: str,
) -> Any:  # noqa: ANN401
    if sort_key == "compiler":
        return (
            str(machine_row.get("compiler", "")).lower(),
            machine_row.get("compiler_version", ()),
        )
    if sort_key == "python":
        return machine_row.get("python_version", ())
    if sort_key == "unique_key":
        return str(machine_row.get("worker_short", "")).lower()
    if sort_key in _MACHINES_CASEFOLD_SORT_KEYS:
        return str(machine_row.get(sort_key, "")).lower()
    if sort_key == "last_updated":
        value = machine_row.get("last_updated")
        return value.timestamp() if isinstance(value, datetime) else 0
    try:
        return int(machine_row.get(sort_key, 0))
    except TypeError, ValueError:
        return 0


def _build_machines_query_params(
    sort_param: str,
    order_param: str,
    default_reverse: bool,  # noqa: FBT001
    query_filter: str,
    my_workers: bool,  # noqa: FBT001
) -> str:
    default_order = "desc" if default_reverse else "asc"
    return _build_query_string(
        [
            ("sort", sort_param if sort_param != _MACHINES_DEFAULT_SORT else None),
            ("order", order_param if order_param != default_order else None),
            ("q", query_filter or None),
            ("my_workers", "1" if my_workers else None),
        ],
    )


def _set_machine_cookie(
    request: Any,  # noqa: ANN401
    name: str,
    value: str,
    max_age_seconds: int,
) -> None:
    encoded = quote(str(value), safe="")
    request.response_headerlist.append(
        (
            "Set-Cookie",
            f"{name}={encoded}; path=/; max-age={max_age_seconds}; SameSite=Lax",
        ),
    )


def _set_machine_cookies(  # noqa: PLR0913
    request: Any,  # noqa: ANN401
    *,
    sort_param: str,
    order_param: str,
    page: int,
    query_filter: str,
    my_workers: bool,
    filtered_count: int,
) -> None:
    cookie_max_age = UI_STATE_COOKIE_MAX_AGE_SECONDS
    _set_machine_cookie(request, "machines_sort", sort_param, cookie_max_age)
    _set_machine_cookie(request, "machines_order", order_param, cookie_max_age)
    _set_machine_cookie(request, "machines_page", str(page), cookie_max_age)
    _set_machine_cookie(request, "machines_q", query_filter, cookie_max_age)
    _set_machine_cookie(
        request,
        "machines_filtered_count",
        str(filtered_count),
        cookie_max_age,
    )
    _set_machine_cookie(
        request,
        "machines_my_workers",
        "1" if my_workers else "0",
        cookie_max_age,
    )


def _workers_count_label(
    total_count: int,
    *,
    query_filter: str = "",
    my_workers: bool = False,
    filtered_count: int | None = None,
) -> str:
    shown_count = filtered_count if filtered_count is not None else total_count
    if not (query_filter or my_workers):
        return f"Workers - {total_count}"
    return f"Workers - {total_count} ({shown_count})"


def tests_machines(request: Any) -> dict[str, Any]:  # noqa: ANN401
    """Build the /tests/machines page context.

    Returns a dict of template context with machine rows, pagination,
    filter state, and sort controls.
    """
    normalized_rows = _normalized_machine_rows(request)
    total_machines = len(normalized_rows)

    sort_param = request.params.get("sort", "").strip().lower()
    if sort_param not in _MACHINES_SORT_MAP:
        sort_param = _MACHINES_DEFAULT_SORT
    sort_key, default_reverse = _MACHINES_SORT_MAP[sort_param]

    order_param, reverse = _normalize_sort_order(
        request.params.get("order", ""),
        default_reverse=default_reverse,
    )

    username = request.authenticated_userid
    machine_filters = _machine_filter_state(
        request.params,
        authenticated_username=username,
    )
    query_filter = machine_filters["query_filter"]
    my_workers = machine_filters["my_workers"]

    filtered_rows = _filter_machine_rows(
        normalized_rows,
        query_filter=query_filter,
        my_workers=my_workers,
        authenticated_username=username,
    )

    filtered_rows.sort(key=lambda m: str(m.get("username", "")).lower())
    filtered_rows.sort(
        key=lambda m: _machines_sort_value(m, sort_key),
        reverse=reverse,
    )

    page_idx = _page_index_from_params(request.params)
    num_machines = len(filtered_rows)
    page_idx = _clamp_page_index(
        page_idx,
        total_count=num_machines,
        page_size=_MACHINES_PAGE_SIZE,
    )

    start = page_idx * _MACHINES_PAGE_SIZE
    end = (page_idx + 1) * _MACHINES_PAGE_SIZE
    machines = filtered_rows[start:end]

    query_params = _build_machines_query_params(
        sort_param,
        order_param,
        default_reverse,
        query_filter,
        my_workers,
    )

    pages = pagination(page_idx, num_machines, _MACHINES_PAGE_SIZE, query_params)
    for page in pages:
        page_url = page.get("url", "")
        if page_url.startswith("?"):
            page["url"] = f"/tests/machines{page_url}"

    _set_machine_cookies(
        request,
        sort_param=sort_param,
        order_param=order_param,
        page=page_idx + 1,
        query_filter=query_filter,
        my_workers=my_workers,
        filtered_count=num_machines,
    )

    workers_count = _workers_count_label(
        total_machines,
        query_filter=query_filter,
        my_workers=my_workers,
        filtered_count=num_machines,
    )

    return {
        "machines_list": filtered_rows,
        "machines": machines,
        "machines_count": num_machines,
        "machines_total_count": total_machines,
        "machines_filtered_count": num_machines,
        "machines_filters_active": machine_filters["filters_active"],
        "workers_count_text": workers_count,
        "machines_page_size": _MACHINES_PAGE_SIZE,
        "pages": pages,
        "sort": sort_param,
        "order": order_param,
        "q": query_filter,
        "current_page": page_idx + 1,
        "my_workers": my_workers,
        "has_authenticated_user": bool(username),
    }
