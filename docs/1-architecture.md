# Server Architecture

## What fishtest does

Fishtest is a distributed chess engine testing infrastructure. The server:

1. Accepts test submissions from developers (new Stockfish patches).
2. Assigns work units (tasks) to volunteer worker machines.
3. Collects game results and computes statistical tests (SPRT, ELO).
4. Publishes results through a web dashboard and a JSON API.

A single MongoDB instance is the system of record. All run state, user
accounts, action logs, and neural network metadata are stored there.

## Repository layout

```
server/
|-- pyproject.toml           -- Package metadata, dependencies
|-- fishtest/
|   |-- app.py               -- ASGI application factory, lifespan, middleware, routers
|   |-- api.py               -- Worker API router (20 endpoints)
|   |-- views.py             -- UI router (29 endpoints, data-driven dispatch)
|   |-- rundb.py             -- RunDb: run lifecycle, task distribution, caching
|   |-- userdb.py            -- UserDb: authentication, groups, registration
|   |-- actiondb.py          -- ActionDb: audit log
|   |-- workerdb.py          -- WorkerDb: worker blocking
|   |-- kvstore.py           -- KVStore: key-value metadata (legacy usernames, flags)
|   |-- scheduler.py         -- Periodic task scheduler (primary instance only)
|   |-- schemas.py           -- vtjson validation schemas (19 schemas)
|   |-- run_cache.py         -- In-memory run cache with dirty-page flush
|   |-- lru_cache.py         -- Generic LRU cache
|   |-- spsa_handler.py      -- SPSA tuning parameter handler
|   |-- github_api.py        -- GitHub integration (commit metadata, branch resolution)
|   |-- util.py              -- Shared utilities (formatting, validation helpers)
|   |-- __init__.py          -- Minimal package init
|   |-- http/                -- HTTP support modules
|   |-- templates/           -- Jinja2 templates (26 files, .html.j2)
|   |-- static/              -- Static assets (JS, CSS, images)
|   `-- stats/               -- Statistical computation modules
`-- tests/                   -- Test suite
```

### HTTP support modules (`server/fishtest/http/`)

```
http/
|-- __init__.py              -- Package init
|-- boundary.py              -- API request adapter (ApiRequestShim), session commit,
|                               template context builder (build_template_context)
|-- cookie_session.py        -- CookieSession class, secret key management, session helpers
|-- csrf.py                  -- CSRF token generation and validation
|-- dependencies.py          -- FastAPI dependency functions (get_rundb, get_userdb, etc.)
|-- errors.py                -- Centralized error handler installation (API/UI routing)
|-- jinja.py                 -- Jinja2 Environment, Jinja2Templates instance, static_url
|-- middleware.py            -- Pure ASGI middleware (5 middleware classes)
|-- session_middleware.py    -- FishtestSessionMiddleware (itsdangerous cookie signing)
|-- settings.py              -- AppSettings (environment variable parsing)
|-- template_helpers.py      -- Jinja2 filters and global functions
|-- template_renderer.py     -- Template rendering helper (render_template_to_response)
|-- ui_errors.py             -- HTML error page rendering (404, 403)
`-- ui_pipeline.py           -- HTTP cache header application
```

### Statistical modules (`server/fishtest/stats/`)

```
stats/
|-- __init__.py
|-- LLRcalc.py               -- Log-likelihood ratio computation
|-- brownian.py              -- Brownian motion model for SPRT
|-- sprt.py                  -- Sequential probability ratio test
`-- stat_util.py             -- ELO calculation, SPRT_elo, get_elo
```

## Application startup

The entrypoint is `uvicorn fishtest.app:app`. The `create_app()` function in
`app.py` builds the FastAPI instance with a lifespan context manager that
handles startup and shutdown. OpenAPI docs (`/docs`, `/redoc`) are disabled
in production (`openapi_url` defaults to `None`). Set
`OPENAPI_URL=/openapi.json` to enable the full interactive API documentation
during development.

### Async concurrency model

The server uses Uvicorn (ASGI) with an async event loop. The event loop
accepts and dispatches HTTP connections; all blocking work runs in the
Starlette threadpool via `run_in_threadpool()`.

| Aspect | Description |
|--------|-------------|
| Concurrency model | Async event loop + threadpool (200 tokens, configurable) |
| Connection capacity | 9,400+ concurrent workers proven in production |
| Blocking I/O | Occupies a threadpool slot only during the blocking call |
| Memory per connection | Coroutine frame (~KBs), not a full thread stack |
| Overload behavior | Connections queue in the kernel backlog (`--backlog 8192`) |

All blocking work (MongoDB queries, file I/O, CPU-bound stats, GitHub API
calls) is offloaded to the threadpool. The event loop stays free to accept
new connections and dispatch lightweight work (session cookie signing, JSON
parsing, CSRF checks).

Application-level throttling (`task_semaphore(TASK_SEMAPHORE_SIZE)` +
`request_task_lock` in `rundb.py`) governs the scheduling critical path.
Both `THREADPOOL_TOKENS` and `TASK_SEMAPHORE_SIZE` are defined in
`http/settings.py`; see [2-threading-model.md](2-threading-model.md) for
the full analysis. Do **not** use Uvicorn's
`--limit-concurrency` flag -- it rejects excess connections with HTTP 503
instead of queuing them, which triggers exponential backoff in workers
(see [8-deployment.md](8-deployment.md) for details).

### Startup sequence

1. `AppSettings.from_env()` reads environment variables (`FISHTEST_PORT`,
   `FISHTEST_PRIMARY_PORT`).
2. On the primary instance, `_require_single_worker_on_primary()` enforces
   that `UVICORN_WORKERS` is 1 (prevents duplicated scheduler side effects).
3. `RunDb(port, is_primary_instance)` is constructed in the threadpool. This
   connects to MongoDB and initializes all domain adapters (UserDb, ActionDb,
   WorkerDb, KVStore).
4. Domain adapters are stored on `app.state` for request-scoped access:
   `app.state.rundb`, `app.state.userdb`, `app.state.actiondb`,
   `app.state.workerdb`.
5. `schemas.legacy_usernames` is populated from KVStore.
6. On the primary instance only:
   - `gh.init()` initializes the GitHub API client.
   - `rundb.update_aggregated_data()` refreshes cached statistics.
   - `rundb.schedule_tasks()` starts the periodic scheduler.

### Shutdown sequence

1. `rundb._shutdown = True` -- signals middleware to reject new requests.
2. `asyncio.sleep(0.5)` -- brief drain period.
3. Scheduler is stopped (`rundb.scheduler.stop()`).
4. On primary: run cache is flushed, persistent data is saved.
5. A `system_event` action is logged.
6. MongoDB connection is closed.

## Middleware stack

Middleware is installed in `create_app()` and executes in reverse installation
order (outermost first in the request path):

| Order | Middleware | Responsibility |
|-------|-----------|----------------|
| 1 | `FishtestSessionMiddleware` | Reads/writes signed session cookie (itsdangerous) |
| 2 | `RedirectBlockedUiUsersMiddleware` | Redirects blocked users to `/tests` (302) |
| 3 | `RejectNonPrimaryWorkerApiMiddleware` | Returns 503 for worker API on non-primary instances |
| 4 | `AttachRequestStateMiddleware` | Copies `app.state` handles to `request.state`; stamps `request_started_at` |
| 5 | `ShutdownGuardMiddleware` | Returns 503 for all requests during shutdown |
| 6 | `HeadMethodMiddleware` | Converts HEAD to GET and strips response body (RFC 9110 Section 9.3.2) |

All middleware classes are pure ASGI (`__call__(self, scope, receive, send)`).
None use Starlette's `BaseHTTPMiddleware`.

## Request flow

```
Client -> nginx -> Uvicorn -> ASGI middleware stack -> FastAPI router
```

- **Worker API**: `api_router` handles all `/api/*` endpoints. Worker
  endpoints require authentication via `username`/`password` in the POST body.
- **UI**: `views_router` handles all HTML-rendering endpoints. Routes are
  registered from the `_VIEW_ROUTES` table via `_register_view_routes()`.
- **Static assets**: `StaticFiles` mount serves `/static/*`.

### htmx integration

UI templates load htmx 2.0.8 from CDN in `base.html.j2`. The server remains
fully server-rendered (Jinja2 + HTML responses). htmx adds three capabilities
without client-side rendering or a JavaScript build step:

| Capability | Mechanism |
|------------|-----------|
| Fragment polling | `hx-get` + `hx-trigger="every Ns"` fetches a fragment endpoint; server returns partial HTML |
| In-place content swap | `hx-get` + `hx-target` + `hx-swap="innerHTML"` replaces a page section (filters, pagination) |
| Out-of-band updates | `hx-swap-oob="innerHTML"` attributes in the response update multiple DOM elements in one response |

**Dual-mode endpoints.** Several UI routes serve either a full page or an HTML
fragment from the same URL. The view handler calls `_is_hx_request(request)` to
detect the `HX-Request: true` header (with a `Sec-Fetch-Mode` guard against
full-page navigations), then returns the appropriate template via the
`_render_hx_fragment()` helper. `_dispatch_view()` appends `Vary: HX-Request`
to every GET response so that HTTP caches distinguish the two representations.

**Fragment templates.** Fragment responses use standalone `.html.j2` files
(named `*_fragment.html.j2`) that do not extend `base.html.j2`. This avoids
the need for block-level partial rendering and keeps fragments self-contained.
See [5-templates.md](5-templates.md) for the full catalog.

**OOB table rows.** HTML spec restrictions prevent `<tbody>` elements from
appearing inside `<div>`. Fragment templates that update table bodies wrap
`<tbody>` elements in `<template>` tags with `hx-swap-oob` attributes.
htmx processes the `<template>` content and discards the wrapper.

**Polling lifecycle.** Polled endpoints use HTTP status codes to control
the polling lifecycle:
- **200** -- swap the response content.
- **204** -- no content; htmx skips the swap but continues polling.
- **286** -- swap the response and stop polling (terminal state).

## Primary instance model

Multiple Uvicorn instances run behind nginx (ports 8000-8003). Exactly one is
designated the **primary** via the `FISHTEST_PRIMARY_PORT` environment variable.

### Primary responsibilities

- Periodic scheduler (run cleanup, ELO recalculation).
- Aggregated data updates.
- GitHub API integration.
- Run cache flush and persistent data save on shutdown.

### Secondary instances

- Serve UI traffic only.
- Worker API requests return 503 (via `RejectNonPrimaryWorkerApiMiddleware`).
- nginx routes worker API traffic to the primary; UI traffic is distributed
  across all instances.

## Signals

| Signal | Behavior |
|--------|----------|
| SIGINT / SIGTERM | Uvicorn initiates graceful shutdown -> lifespan cleanup runs |
| SIGUSR1 | Dumps all thread stacks to stderr via `faulthandler.register()` |

To trigger a thread dump on a systemd-managed instance, run `sudo systemctl kill -s SIGUSR1 fishtest@8000`.

During shutdown, `ShutdownGuardMiddleware` rejects new requests with HTTP 503.

## Core domain adapters

These are not HTTP modules. They encapsulate business logic and MongoDB access.

| Adapter | Module | Responsibility |
|---------|--------|----------------|
| `RunDb` | `rundb.py` | Run lifecycle, task assignment, result aggregation, run cache |
| `UserDb` | `userdb.py` | User CRUD, password hashing (zxcvbn strength), group membership |
| `ActionDb` | `actiondb.py` | Audit trail for user and system actions |
| `WorkerDb` | `workerdb.py` | Worker ban list management |
| `KVStore` | `kvstore.py` | Lightweight key-value pairs in MongoDB |
| `Scheduler` | `scheduler.py` | Periodic background tasks on primary instance |

A single `RunDb` instance is created per process at startup and stored on
`app.state.rundb`. It owns all other adapters (`rundb.userdb`, `rundb.actiondb`,
`rundb.workerdb`, `rundb.kvstore`).

## Validation

vtjson is the sole validation layer. The `schemas.py` module defines 19 schemas
that validate plain Python dicts. Schemas are used in:

- API endpoints (request body validation).
- Domain adapters (run, user, action document validation before MongoDB writes).
- Form input validation (username format, worker name format).

No Pydantic models are used anywhere in the codebase.

## Framework usage: FastAPI as a thin wrapper

This project uses FastAPI as a thin routing convenience layer on top of
Starlette. The three FastAPI-exclusive features in use are:

1. **`FastAPI()`** -- the application class (inherits `starlette.Starlette`).
2. **`APIRouter`** -- decorator-style route registration and data-driven
   `add_api_route()`.
3. **Exception handlers** -- two fallback handlers from
   `fastapi.exception_handlers`.

The following FastAPI features are **not used**:

- Pydantic request/response models (`BaseModel`, `response_model`).
- Dependency injection (`Depends()`) in route signatures.
- Parameter declarations (`Body`, `Query`, `Path`, `Header`, `Cookie`).
- Security schemes (`OAuth2`, `HTTPBasic`, `APIKey`).

All middleware is pure ASGI (Starlette pattern). Session handling, CSRF
protection, authentication, and request validation use custom
implementations -- not FastAPI's built-in machinery.

Contributors should not expect Pydantic, DI, or security scheme patterns
in this codebase. When importing classes that FastAPI re-exports from
Starlette (`Request`, `Response`, `JSONResponse`, `StaticFiles`, etc.),
prefer importing from `starlette` directly.

## Error handling

Error handlers are installed via `install_error_handlers(app)` in `app.py`.
They route errors differently based on the request path:

| Path prefix | HTTP 404 | HTTP 401/403 | Validation error | Unhandled exception |
|-------------|----------|--------------|------------------|---------------------|
| `/api/*` (worker) | JSON `{"error": "...", "duration": N}` | JSON | JSON `{"error": "...", "duration": N}` | JSON `{"error": "...", "duration": N}` |
| `/api/*` (other) | JSON `{"detail": "Not Found"}` | JSON | JSON | JSON |
| UI routes | HTML 404 page (Jinja2) | HTML 403 page (Jinja2) | Default | Plain text 500 |

Worker API errors always include a `duration` field to maintain protocol
compatibility.
