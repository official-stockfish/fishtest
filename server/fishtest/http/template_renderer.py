"""Unified template renderer for Jinja2."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Protocol, cast

from fishtest.http import jinja as jinja_renderer

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.templating import Jinja2Templates


@cache
def _jinja_templates() -> Jinja2Templates:
    return jinja_renderer.default_templates()


class _TemplateDebugResponse(Protocol):
    template_name: str
    context_data: dict[str, object]


@dataclass(frozen=True)
class RenderedTemplate:
    """Represents a rendered HTML payload."""

    html: str


def render_template(
    *,
    template_name: str,
    context: Mapping[str, object],
) -> RenderedTemplate:
    """Render a template using the Jinja2 renderer.

    Note: the live UI pipeline uses `render_template_to_response()` instead.
    This helper is intended for tests or tools that only need HTML output.
    """
    rendered = jinja_renderer.render_template(
        templates=_jinja_templates(),
        template_name=template_name,
        context=context,
    )
    return RenderedTemplate(html=rendered.html)


def render_template_to_response(
    *,
    request: Request,
    template_name: str,
    context: Mapping[str, object],
    status_code: int = 200,
) -> Response:
    """Render a template and return a TemplateResponse with debug metadata."""
    response = jinja_renderer.render_template_response(
        templates=_jinja_templates(),
        request=request,
        template_name=template_name,
        context=context,
        options=jinja_renderer.TemplateResponseOptions(status_code=status_code),
    )
    # Attach debug-friendly attributes without clobbering Starlette's
    # native TemplateResponse fields (.template and .context).
    debug_response = cast("_TemplateDebugResponse", response)
    debug_response.template_name = template_name
    debug_response.context_data = dict(context)
    return response
