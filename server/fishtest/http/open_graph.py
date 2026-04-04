"""Build server-side Open Graph metadata for full-page UI responses."""

from __future__ import annotations

from typing import Any, TypedDict
from urllib.parse import urlsplit, urlunsplit

from fishtest.http.template_helpers import nelo_pentanomial_summary_text

_SITE_NAME = "Stockfish Testing Framework"
_DEFAULT_DESCRIPTION = "Distributed testing framework for the Stockfish chess engine."
_TITLE_SUFFIX = " | Stockfish Testing"
_YELLOW_THEME_COLOR = "#FFFF00"


class OpenGraphMetadata(TypedDict):
    """Structured page metadata rendered by the base template."""

    site_name: str
    type: str
    title: str
    description: str
    url: str


def canonical_page_url(url: str) -> str:
    """Drop query and fragment parts from a page URL."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def default_open_graph(page_url: str) -> OpenGraphMetadata:
    """Return default page metadata for full HTML responses."""
    return {
        "site_name": _SITE_NAME,
        "type": "website",
        "title": _SITE_NAME,
        "description": _DEFAULT_DESCRIPTION,
        "url": canonical_page_url(page_url),
    }


def _normalize_metadata_text(text: str) -> str:
    return " ".join(text.replace(" ± ", " +/- ").split())


def _tests_view_description_lines(
    run: dict[str, Any],
    results_info: dict[str, Any],
) -> list[str]:
    info = results_info.get("info", [])
    if not isinstance(info, list):
        return []

    description_parts: list[str] = []

    for value in info:
        line = str(value)
        normalized_line = _normalize_metadata_text(line)
        if normalized_line:
            description_parts.append(normalized_line)

    nelo_summary = nelo_pentanomial_summary_text(run)
    if nelo_summary:
        description_parts.append(_normalize_metadata_text(nelo_summary))

    return description_parts


def _tests_view_description(
    run: dict[str, Any],
    results_info: dict[str, Any],
) -> str:
    description_lines = _tests_view_description_lines(run, results_info)
    if not description_lines:
        return _DEFAULT_DESCRIPTION

    return "\n".join(description_lines)


def _theme_color_from_results(results_info: dict[str, Any]) -> str | None:
    style = results_info.get("style", "")
    if not isinstance(style, str):
        return None
    if style == "yellow":
        return _YELLOW_THEME_COLOR
    if style.startswith("#"):
        return style
    return None


def build_tests_view_open_graph(
    *,
    host_url: str,
    run: dict[str, Any],
    page_title: str,
    results_info: dict[str, Any],
) -> tuple[OpenGraphMetadata, str | None]:
    """Return Open Graph metadata and theme color for `/tests/view/{id}`."""
    open_graph = default_open_graph(f"{host_url.rstrip('/')}/tests/view/{run['_id']}")
    open_graph["title"] = f"{page_title}{_TITLE_SUFFIX}"
    open_graph["description"] = _tests_view_description(run, results_info)
    return (
        open_graph,
        _theme_color_from_results(results_info),
    )


__all__ = [
    "OpenGraphMetadata",
    "build_tests_view_open_graph",
    "canonical_page_url",
    "default_open_graph",
]
