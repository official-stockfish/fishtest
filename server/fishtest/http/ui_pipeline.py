"""Apply shared HTTP view-response policies.

Attach cache headers to UI responses when a view config enables them.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.responses import Response


def apply_http_cache(response: Response, cfg: dict[str, object] | None) -> Response:
    """Apply `Cache-Control` from view config when missing."""
    http_cache = cfg.get("http_cache") if cfg else None
    if http_cache is not None and "Cache-Control" not in response.headers:
        with suppress(Exception):
            if isinstance(http_cache, (int, float, str)):
                response.headers["Cache-Control"] = f"max-age={int(http_cache)}"
    return response
