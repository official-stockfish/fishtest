"""Runtime settings for the FastAPI server.

This module centralizes environment parsing and derived runtime flags.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def env_int(name: str, *, default: int) -> int:
    """Parse an environment variable as an integer, with a fallback default."""
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def default_static_dir() -> Path:
    """Return the default static directory path for `/static` mounting."""
    env_value = os.environ.get("FISHTEST_STATIC_DIR", "").strip()
    if env_value:
        return Path(env_value).expanduser()

    # Package-relative resolution works for both source checkouts and wheels.
    return Path(__file__).resolve().parents[1] / "static"


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Derived runtime settings for the FastAPI server process."""

    port: int
    primary_port: int
    is_primary_instance: bool
    openapi_url: str | None = None

    @classmethod
    def from_env(cls) -> AppSettings:
        """Build settings from environment variables."""
        port = env_int("FISHTEST_PORT", default=-1)
        primary_port = env_int("FISHTEST_PRIMARY_PORT", default=-1)

        # Legacy behavior: if the port number cannot be determined,
        # assume the instance is primary for backward compatibility.
        if port < 0 or primary_port < 0:
            is_primary_instance = True
        else:
            is_primary_instance = port == primary_port

        # OpenAPI docs are disabled in production by default.
        # Set OPENAPI_URL=/openapi.json in development to re-enable
        # /docs, /redoc, and /openapi.json.
        openapi_url_raw = os.environ.get("OPENAPI_URL", "").strip()
        openapi_url: str | None = openapi_url_raw or None

        return cls(
            port=port,
            primary_port=primary_port,
            is_primary_instance=is_primary_instance,
            openapi_url=openapi_url,
        )
