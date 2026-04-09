"""Build server-side Open Graph metadata for full-page UI responses."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, SupportsFloat, TypedDict
from urllib.parse import urlsplit, urlunsplit

from fishtest.http.template_helpers import nelo_pentanomial_summary_text

if TYPE_CHECKING:
    from collections.abc import Iterable

_SITE_NAME = "Stockfish Testing Framework"
_DEFAULT_DESCRIPTION = "Distributed testing framework for the Stockfish chess engine."
_TITLE_SUFFIX = " | Stockfish Testing"
_YELLOW_THEME_COLOR = "#FFFF00"

_TimestampInput = SupportsFloat | str | None


class OpenGraphMetadata(TypedDict):
    """Structured page metadata rendered by the base template."""

    site_name: str
    type: str
    title: str
    description: str
    url: str


def open_graph_page_url(url: str, *, keep_query: bool = False) -> str:
    """Return the URL rendered into `og:url` for a full page."""
    parts = urlsplit(url)
    query = parts.query if keep_query else ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def canonical_page_url(url: str) -> str:
    """Drop query and fragment parts from a page URL."""
    return open_graph_page_url(url)


def default_open_graph(
    page_url: str,
    *,
    keep_query: bool = False,
) -> OpenGraphMetadata:
    """Return default page metadata for full HTML responses."""
    return {
        "site_name": _SITE_NAME,
        "type": "website",
        "title": _SITE_NAME,
        "description": _DEFAULT_DESCRIPTION,
        "url": open_graph_page_url(page_url, keep_query=keep_query),
    }


def _normalize_metadata_text(text: str) -> str:
    return " ".join(text.replace(" ± ", " +/- ").replace("\u2011", "-").split())


def _metadata_lines(values: Iterable[object]) -> list[str]:
    description_lines: list[str] = []
    for value in values:
        normalized_value = _normalize_metadata_text(str(value))
        if normalized_value:
            description_lines.append(normalized_value)
    return description_lines


def _labeled_metadata_lines(values: Iterable[tuple[str, object]]) -> list[str]:
    description_lines: list[str] = []
    for label, value in values:
        normalized_value = _normalize_metadata_text(str(value or ""))
        if normalized_value:
            description_lines.append(f"{label}: {normalized_value}")
    return description_lines


def _truncate_metadata_text(text: str, *, max_length: int) -> str:
    if len(text) <= max_length:
        return text

    truncated = text[: max_length - 3].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return f"{truncated}..."


def _join_description_lines(description_lines: Iterable[str]) -> str:
    lines = [line for line in description_lines if line]
    if not lines:
        return _DEFAULT_DESCRIPTION
    return "\n".join(lines)


def _page_open_graph_title(page_title: str) -> str:
    normalized_title = _normalize_metadata_text(page_title)
    if not normalized_title:
        return _SITE_NAME
    return f"{normalized_title}{_TITLE_SUFFIX}"


def _build_page_open_graph(
    *,
    page_url: str,
    page_title: str,
    description: str,
    keep_query: bool = False,
) -> OpenGraphMetadata:
    open_graph = default_open_graph(page_url, keep_query=keep_query)
    open_graph["title"] = _page_open_graph_title(page_title)
    open_graph["description"] = description
    return open_graph


def _metadata_time_label(value: _TimestampInput) -> str:
    if value is None:
        return ""

    try:
        return datetime.fromtimestamp(float(value), UTC).strftime("%y-%m-%d %H:%M:%S")
    except OverflowError, OSError, TypeError, ValueError:
        return ""


def _tests_view_description_lines(
    run: dict[str, Any],
    results_info: dict[str, Any],
) -> list[str]:
    info = results_info.get("info", [])
    if not isinstance(info, list):
        return []

    description_parts = _metadata_lines(info)

    nelo_summary = nelo_pentanomial_summary_text(run)
    if nelo_summary:
        description_parts.extend(_metadata_lines([nelo_summary]))

    return description_parts


def _tests_view_description(
    run: dict[str, Any],
    results_info: dict[str, Any],
) -> str:
    return _join_description_lines(_tests_view_description_lines(run, results_info))


def _theme_color_from_results(results_info: dict[str, Any]) -> str | None:
    style = results_info.get("style", "")
    if not isinstance(style, str):
        return None
    if style == "yellow":
        return _YELLOW_THEME_COLOR
    if style.startswith("#"):
        return style
    return None


def _actions_open_graph_title(action_row: dict[str, Any]) -> str:
    event = _normalize_metadata_text(str(action_row.get("event") or "Events Log"))
    target = _normalize_metadata_text(str(action_row.get("target_name") or ""))
    agent = _normalize_metadata_text(str(action_row.get("agent_name") or ""))

    if target:
        return _truncate_metadata_text(f"{event} on {target}", max_length=90)
    if agent:
        return _truncate_metadata_text(f"{event} by {agent}", max_length=90)
    return _truncate_metadata_text(f"Events Log - {event}", max_length=90)


def _actions_open_graph_description(
    action_row: dict[str, Any],
    *,
    num_actions: int,
) -> str:
    description_lines: list[str] = []

    if num_actions > 1:
        description_lines.append(f"1 of {num_actions} matching actions.")

    time_label = _metadata_time_label(action_row.get("time"))
    if time_label:
        description_lines.append(f"Time: {time_label}")

    description_lines.extend(
        _labeled_metadata_lines(
            (
                ("Event", action_row.get("event")),
                ("Source", action_row.get("agent_name")),
                ("Target", action_row.get("target_name")),
            ),
        ),
    )

    message = _normalize_metadata_text(str(action_row.get("message") or ""))
    if message:
        description_lines.append(
            "Comment: "
            + _truncate_metadata_text(
                message,
                max_length=220,
            ),
        )

    return _join_description_lines(description_lines)


def _actions_no_results_description(
    *,
    filters: dict[str, str],
    run_id_filter: str,
) -> str:
    filter_parts = _metadata_lines(
        [
            f"event={filters.get('action', '')}" if filters.get("action") else "",
            f"user={filters.get('username', '')}" if filters.get("username") else "",
            f"text={filters.get('text', '')}" if filters.get("text") else "",
            f"run={run_id_filter}" if run_id_filter else "",
        ],
    )

    if not filter_parts:
        return "Events log results. No actions matched."

    filters_text = _truncate_metadata_text(
        ", ".join(filter_parts),
        max_length=180,
    )
    return f"No actions matched the current filters: {filters_text}"


def build_actions_open_graph(
    *,
    page_url: str,
    actions: list[dict[str, Any]],
    num_actions: int,
    filters: dict[str, str],
    run_id_filter: str,
) -> OpenGraphMetadata:
    """Return Open Graph metadata for `/actions` full-page responses."""
    if not actions:
        return _build_page_open_graph(
            page_url=page_url,
            page_title="Events Log",
            description=_actions_no_results_description(
                filters=filters,
                run_id_filter=run_id_filter,
            ),
            keep_query=True,
        )

    return _build_page_open_graph(
        page_url=page_url,
        page_title=_actions_open_graph_title(actions[0]),
        description=_actions_open_graph_description(
            actions[0],
            num_actions=num_actions,
        ),
        keep_query=True,
    )


def build_tests_view_open_graph(
    *,
    page_url: str,
    run: dict[str, Any],
    page_title: str,
    results_info: dict[str, Any],
) -> tuple[OpenGraphMetadata, str | None]:
    """Return Open Graph metadata and theme color for `/tests/view/{id}`."""
    open_graph = _build_page_open_graph(
        page_url=page_url,
        page_title=page_title,
        description=_tests_view_description(run, results_info),
    )
    return (
        open_graph,
        _theme_color_from_results(results_info),
    )


__all__ = [
    "OpenGraphMetadata",
    "build_actions_open_graph",
    "build_tests_view_open_graph",
    "canonical_page_url",
    "default_open_graph",
]
