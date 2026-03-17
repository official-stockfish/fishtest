"""Provide stateless helper functions for the views layer.

Keep these utilities pure so the views layer can share pagination, parameter,
and merge helpers without requiring a running application or database.
"""

from __future__ import annotations

import heapq
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

if TYPE_CHECKING:
    from collections.abc import Callable

_TRUTHY_PARAM_VALUES = frozenset({"1", "true", "on", "yes"})
_SORT_ORDER_VALUES = frozenset({"asc", "desc"})
_PAGED_VIEW_VALUES = frozenset({"paged", "all"})

_ANONYMOUS_RESULT_LIMIT_HARD = 5000
_MONGO_INT64_MAX = 2**63 - 1
_DEFAULT_TIME_SORT_FIELD = "time"
_DEFAULT_SORT_ORDER = "desc"
_MERGE_WINDOW_MAX = 600

# Different LOCALES may have different quotation marks.
# See https://op.europa.eu/en/web/eu-vocabularies/formex/physical-specifications/character-encoding/quotation-marks
_QUOTATION_MARKS = (
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
_QUOTATION_MARKS_STR = "".join(chr(c) for c in _QUOTATION_MARKS)
_QUOTATION_MARKS_TRANSLATION = str.maketrans(
    _QUOTATION_MARKS_STR,
    len(_QUOTATION_MARKS_STR) * '"',
)


def sanitize_quotation_marks(text: str) -> str:
    """Replace typographic quotation marks with ASCII double quotes."""
    return text.translate(_QUOTATION_MARKS_TRANSLATION)


def _is_truthy_param(value: Any) -> bool:  # noqa: ANN401
    return str(value).strip().lower() in _TRUTHY_PARAM_VALUES


def _page_index_from_params(params: Any, *, key: str = "page") -> int:  # noqa: ANN401
    page_value = str(params.get(key, "")).strip()
    return max(0, int(page_value) - 1) if page_value.isdigit() else 0


def _normalize_sort_order(
    raw_value: Any,  # noqa: ANN401
    *,
    default_reverse: bool,
) -> tuple[str, bool]:
    order_param = str(raw_value).strip().lower()
    if order_param in _SORT_ORDER_VALUES:
        return order_param, order_param == "desc"
    return ("desc", True) if default_reverse else ("asc", False)


def _normalize_view_mode(raw_value: Any) -> str:  # noqa: ANN401
    view_param = str(raw_value).strip().lower()
    return view_param if view_param in _PAGED_VIEW_VALUES else "paged"


def _clamp_page_index(
    page_idx: int,
    *,
    total_count: int,
    page_size: int,
) -> int:
    if total_count <= 0:
        return 0
    return min(page_idx, (total_count - 1) // page_size)


def _build_query_string(
    pairs: list[tuple[str, Any]],
    *,
    leading: str = "&",
) -> str:
    filtered_pairs = [(key, str(value)) for key, value in pairs if value is not None]
    return f"{leading}{urlencode(filtered_pairs)}" if filtered_pairs else ""


def _positive_int_param(
    raw_value: Any,  # noqa: ANN401
    *,
    max_value: int | None = None,
) -> int | None:
    if raw_value in (None, ""):
        return None
    try:
        value = int(raw_value)
    except TypeError, ValueError:
        return None
    if value <= 0:
        return None
    if max_value is not None:
        return min(value, max_value)
    return value


def _float_param(raw_value: Any) -> float | None:  # noqa: ANN401
    if raw_value in (None, ""):
        return None
    try:
        return float(raw_value)
    except TypeError, ValueError:
        return None


def _effective_result_limit(
    *,
    is_authenticated: bool,
    requested_limit: int | None,
    anonymous_hard_limit: int,
    authenticated_default_limit: int | None = None,
) -> int | None:
    if not is_authenticated:
        if requested_limit is None:
            return anonymous_hard_limit
        return min(requested_limit, anonymous_hard_limit)

    if requested_limit is not None:
        return requested_limit
    return authenticated_default_limit


def pagination(
    page_idx: int,
    num: int,
    page_size: int,
    query_params: str,
) -> list[dict[str, Any]]:
    """Build a pagination control list for template rendering."""
    pages: list[dict[str, Any]] = [
        {
            "idx": "Prev",
            "url": f"?page={page_idx}" + query_params,
            "state": "disabled" if page_idx == 0 else "",
        },
    ]

    if num <= 0:
        pages.append(
            {
                "idx": 1,
                "url": "?page=1" + query_params,
                "state": "active" if page_idx == 0 else "",
            },
        )
        pages.append(
            {
                "idx": "Next",
                "url": f"?page={page_idx + 2}" + query_params,
                "state": "disabled",
            },
        )
        return pages

    last_idx = (num - 1) // page_size

    disable_next = page_idx >= last_idx

    def add_page(idx: int) -> None:
        pages.append(
            {
                "idx": idx + 1,
                "url": f"?page={idx + 1}" + query_params,
                "state": "active" if page_idx == idx else "",
            },
        )

    # Always show page 1.
    add_page(0)

    # Compact mobile-friendly layout:
    # Prev, 1, ..., (current-1,current,current+1), ..., last, Next  # noqa: ERA001
    if page_idx <= 2:  # noqa: PLR2004
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

    if last_idx >= 5 and page_idx < last_idx - 2:  # noqa: PLR2004
        pages.append({"idx": "...", "url": "", "state": "disabled"})

    if last_idx > 0:
        add_page(last_idx)

    pages.append(
        {
            "idx": "Next",
            "url": f"?page={page_idx + 2}" + query_params,
            "state": "disabled" if disable_next else "",
        },
    )
    return pages


def _host_url(request: Any) -> str:  # noqa: ANN401
    host_url = getattr(request, "host_url", None)
    if host_url:
        return host_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def _path_qs(request: Any) -> str:  # noqa: ANN401
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


def _path_url(request: Any) -> str:  # noqa: ANN401
    path_url = getattr(request, "path_url", None)
    if path_url:
        return path_url
    url = getattr(request, "url", None)
    if url is None:
        host_url = _host_url(request)
        path = getattr(request, "path", "")
        return f"{host_url}{path}"
    return str(url).split("?", 1)[0]


def _apply_response_headers(shim: Any, response: Any) -> Any:  # noqa: ANN401
    for key, value in getattr(shim, "response_headers", {}).items():
        response.headers[key] = value
    for key, value in getattr(shim, "response_headerlist", []):
        if key.lower() == "set-cookie":
            response.headers.append(key, value)
        else:
            response.headers[key] = value
    return response


def _append_vary_header(response: Any, token: str) -> None:  # noqa: ANN401
    existing = response.headers.get("Vary", "")
    parts = [p.strip() for p in existing.split(",") if p.strip()]
    lowered = {p.lower() for p in parts}
    if token.lower() not in lowered:
        parts.append(token)
        response.headers["Vary"] = ", ".join(parts)


def _append_no_store_headers(request: Any) -> None:  # noqa: ANN401
    request.response_headerlist.extend(
        (
            ("Cache-Control", "no-store"),
            ("Expires", "0"),
        ),
    )


def _is_hx_request(request: Any) -> bool:  # noqa: ANN401
    headers = getattr(request, "headers", None)
    if headers is None:
        return False
    if (headers.get("HX-Request") or "").lower() != "true":
        return False
    # Never treat top-level document navigations as fragment requests,
    # even if HX-Request appears in transit.
    return (headers.get("Sec-Fetch-Mode") or "").lower() != "navigate"


# === Username matching and sorting ===


def _username_match_sort_key(
    query: str,
    candidate: Any,  # noqa: ANN401
) -> tuple[int, int, str]:
    normalized_query = query.strip().lower()
    normalized_candidate = str(candidate).lower()
    match_idx = normalized_candidate.find(normalized_query)
    starts_with = 0 if match_idx == 0 else 1
    return (starts_with, match_idx, normalized_candidate)


def _sort_matched_usernames(
    usernames: list[str],
    query: str,
) -> list[str]:
    return sorted(
        usernames,
        key=lambda username: _username_match_sort_key(query, username),
    )


def _username_priority_map(usernames: list[str]) -> dict[str, int]:
    return {username: idx for idx, username in enumerate(usernames)}


# === Nested row access ===


def _nested_row_value(
    row: Any,  # noqa: ANN401
    field_name: str,
    default: Any = None,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    value = row
    for part in str(field_name).split("."):
        if not isinstance(value, dict):
            return default
        value = value.get(part)
        if value is None:
            return default
    return value


# === Heap-based merge ===


def _merge_rows_by_username_priority(  # noqa: PLR0913
    grouped_rows: list[list[dict[str, Any]]],
    *,
    username_priority: dict[str, int],
    username_field: str,
    time_field: str,
    id_field: str,
    skip: int,
    limit: int,
) -> list[dict[str, Any]]:
    heap = []
    merged_rows = []
    needed = skip + limit

    for list_idx, rows in enumerate(grouped_rows):
        if not rows:
            continue
        row = rows[0]
        priority = username_priority.get(
            _nested_row_value(row, username_field, ""),
            len(username_priority),
        )
        time_value = row.get(time_field)
        if isinstance(time_value, datetime):
            timestamp = time_value.timestamp()
        else:
            timestamp = float(time_value or 0)
        heapq.heappush(
            heap,
            (
                priority,
                -timestamp,
                str(row.get(id_field, "")),
                list_idx,
                0,
            ),
        )

    while heap and len(merged_rows) < needed:
        _, _, _, list_idx, row_idx = heapq.heappop(heap)
        row = grouped_rows[list_idx][row_idx]
        merged_rows.append(row)

        next_idx = row_idx + 1
        if next_idx < len(grouped_rows[list_idx]):
            next_row = grouped_rows[list_idx][next_idx]
            priority = username_priority.get(
                _nested_row_value(next_row, username_field, ""),
                len(username_priority),
            )
            time_value = next_row.get(time_field)
            if isinstance(time_value, datetime):
                timestamp = time_value.timestamp()
            else:
                timestamp = float(time_value or 0)
            heapq.heappush(
                heap,
                (
                    priority,
                    -timestamp,
                    str(next_row.get(id_field, "")),
                    list_idx,
                    next_idx,
                ),
            )

    return merged_rows[skip : skip + limit]


def _ranked_multi_username_merge(  # noqa: PLR0913
    *,
    usernames: list[str],
    fetch_fn: Callable[..., tuple[list[dict[str, Any]], int]],
    username_field: str,
    time_field: str,
    skip: int,
    limit: int,
    max_count: int | None,
) -> tuple[list[dict[str, Any]], int] | None:
    merge_window = max(skip + limit, 1)
    if len(usernames) * merge_window > _MERGE_WINDOW_MAX:
        return None

    total_count = 0
    grouped_rows = []
    username_priority = _username_priority_map(usernames)

    for matched_username in usernames:
        remaining_cap = None
        if max_count is not None:
            remaining_cap = max(max_count - total_count, 0)
            if remaining_cap == 0:
                break

        rows, count = fetch_fn(matched_username, merge_window, remaining_cap)
        total_count += count
        if max_count is not None:
            total_count = min(total_count, max_count)
        if rows:
            grouped_rows.append(rows)

    return (
        _merge_rows_by_username_priority(
            grouped_rows,
            username_priority=username_priority,
            username_field=username_field,
            time_field=time_field,
            id_field="_id",
            skip=skip,
            limit=limit,
        ),
        total_count,
    )
