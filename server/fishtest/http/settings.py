"""Runtime settings for the FastAPI server.

This module centralizes environment parsing and derived runtime flags.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Threadpool and scheduling-throttle constants
# ---------------------------------------------------------------------------
#
# THREADPOOL_TOKENS controls the AnyIO threadpool that runs ALL blocking
# work (MongoDB, file I/O, templates). Every in-flight request holds one
# token for its full duration.
#
# TASK_SEMAPHORE_SIZE caps how many of those tokens /api/request_task may
# occupy simultaneously.  request_task is serialised internally by a
# mutex (request_task_lock), so only 1 thread does useful work -- the
# rest block on the mutex, pinning tokens for zero throughput.
#
# Without the cap, a reconnection burst (eg 208 -> 9,423 workers in 20 min)
# would fill all 200 tokens with mutex-waiters, starving /api/beat
# (~83 req/s at 10k workers) and /api/update_task until the burst drains.
#
# See docs/2-threading-model.md "Task scheduling throttle" for the full
# derivation with Little's Law token-occupancy math and validation
# against production data with ~10k workers.
# ---------------------------------------------------------------------------

THREADPOOL_TOKENS: int = 200
"""AnyIO threadpool size set at lifespan startup.

Proven sufficient for 9,400+ workers on a single Uvicorn process.
Increasing beyond 200 risks overwhelming MongoDB with concurrent queries.
"""

TASK_SEMAPHORE_SIZE: int = 5
"""Max concurrent /api/request_task calls in the threadpool.

Derived from production data (128k reqs / 57 min at 9,423 workers):
- 1 slot active (inside request_task_lock), ~15 ms per call.
- 4 slots queue (absorb arrival jitter during reconnection bursts).
- 195 tokens (97.5%) remain for beat, update_task, UI, uploads.

A higher value pins more tokens on the mutex for zero throughput gain.
A lower value rejects too aggressively during bursty reconnections.
"""


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
