# Threading Model

## Principle

The ASGI event loop is a thin HTTP dispatcher. All blocking work runs in
Starlette's default threadpool via `run_in_threadpool()`.

The async event loop holds all concurrent connections (thousands) while
only a fraction simultaneously occupy threadpool slots for blocking
MongoDB/lock work. Connection acceptance is decoupled from handler
execution -- Uvicorn can accept 10,000+ worker connections natively.

The threadpool size is configured by `THREADPOOL_TOKENS` in `app.py`
(currently 200). This is set during lifespan startup via
`current_default_thread_limiter().total_tokens`. The value must be large
enough to avoid queuing under sustained load (9,400+ concurrent workers
proven in production), but not so large that it overwhelms MongoDB or
CPU resources.

Application-level throttling (`task_semaphore(5)` + `request_task_lock` in
`rundb.py`) governs the scheduling critical path, not the HTTP layer.

Do **not** use Uvicorn's `--limit-concurrency` flag. It rejects excess
connections with HTTP 503 instead of queuing them. See
[8-deployment.md](8-deployment.md) for the correct Uvicorn flags.

Blocking work includes:

- **MongoDB queries** -- pymongo is synchronous.
- **File I/O** -- template rendering, PGN uploads, neural network files.
- **CPU-bound computation** -- ELO calculations, SPRT, SPSA.
- **Network calls** -- GitHub API via the `requests` library.

## Execution domains

### Event loop `[LOOP]`

Code that runs directly in the `async def` coroutine on the event loop. Must
complete quickly (microseconds to low milliseconds).

- All ASGI middleware `__call__` methods.
- FastAPI route dispatch (before entering the handler body).
- Lifespan startup/shutdown orchestration.
- Session cookie signing/unsigning (HMAC + base64 + JSON; small payloads).
- CSRF token generation (`secrets.token_hex`).

### Threadpool `[THREAD]`

Code offloaded to the default anyio threadpool via `run_in_threadpool()`.

- All API endpoint handler bodies (sync functions -> FastAPI auto-offloads).
- All UI endpoint handler bodies (via `_dispatch_view` -> `run_in_threadpool`).
- `RunDb` construction and shutdown (MongoDB connect/close).
- Scheduler start/stop.
- GitHub API initialization and calls.
- Jinja2 template rendering.
- Aggregated data updates.

### Streaming `[STREAM/THREAD]`

Async generators that yield chunks, with each chunk read in the threadpool.

- PGN file downloads (`download_pgn`, `download_run_pgns`): `StreamingResponse`
  wraps `iterate_in_threadpool(_iter_filelike(...))`.

## Component inventory

### Lifespan (`app.py`)

| Function | Domain | Notes |
|----------|--------|-------|
| `create_app()` / `lifespan()` | `[LOOP]` | Orchestrates startup/shutdown |
| `RunDb(...)` | `[THREAD]` | MongoDB connect via `run_in_threadpool` |
| `gh.init(...)` | `[THREAD]` | GitHub API setup |
| `rundb.schedule_tasks()` | `[THREAD]` | Starts periodic scheduler |
| `_shutdown_rundb(...)` | `[LOOP]` | Coordinates threadpool shutdown calls |
| `rundb.scheduler.stop()` | `[THREAD]` | Stops scheduler |
| `rundb.run_cache.flush_all()` | `[THREAD]` | Flushes dirty pages |
| `rundb.conn.close()` | `[THREAD]` | Closes MongoDB connection |

### Middleware (`http/middleware.py`, `http/session_middleware.py`)

| Class | Domain | Notes |
|-------|--------|-------|
| `FishtestSessionMiddleware` | `[LOOP]` | Signs/unsigns cookie, enforces size limits |
| `ShutdownGuardMiddleware` | `[LOOP]` | Checks `_shutdown` flag, returns 503 |
| `AttachRequestStateMiddleware` | `[LOOP]` | Copies state references, stamps start time |
| `RejectNonPrimaryWorkerApiMiddleware` | `[LOOP]` | Checks primary flag, returns 503 |
| `RedirectBlockedUiUsersMiddleware` | `[LOOP]` + `[THREAD]` | Session read on loop; blocked-user DB lookup offloaded |
| `HeadMethodMiddleware` | `[LOOP]` | Converts HEAD to GET, strips response body |

### API router (`api.py`)

| Component | Domain | Notes |
|-----------|--------|-------|
| Route wrappers (`async def`) | `[LOOP]` | Parse JSON body, construct shim |
| `WorkerApi` handler methods | `[THREAD]` | All 9 worker endpoints |
| `UserApi` handler methods | `[THREAD]` | All 11 user/read-only endpoints |
| PGN streaming | `[STREAM/THREAD]` | `iterate_in_threadpool` over file chunks |

### UI router (`views.py`)

| Component | Domain | Notes |
|-----------|--------|-------|
| `_dispatch_view()` | `[LOOP]` | Form parsing, CSRF check, then `run_in_threadpool` |
| All 29 view handler bodies | `[THREAD]` | Via `_dispatch_view` |
| Template rendering | `[THREAD]` | Inside handler body, `render_template_to_response` |

### Error handlers (`http/errors.py`)

| Component | Domain | Notes |
|-----------|--------|-------|
| `_http_exception_handler` | `[LOOP]` | Routes to JSON or HTML |
| `render_notfound_response` | `[THREAD]` | Template rendering for 404 page |
| `render_forbidden_response` | `[THREAD]` | Template rendering for 403 page |

## Event-loop CPU hotspots

These are the known points where CPU work runs on the event loop rather than
in the threadpool. They are acceptable because they process small payloads:

| Hotspot | Location | Payload size |
|---------|----------|-------------|
| JSON decode | `await request.json()` in API routes | Typically < 10 KB |
| Form parse | `await request.form()` in `_dispatch_view` | Typically < 200 MB max (PGN uploads are API, not UI) |
| Cookie decode | `itsdangerous.unsign()` in session middleware | < 4 KB (cookie size limit enforced) |

## Rules for adding new code

1. **New endpoints**: write handler functions as `def` (sync). FastAPI
   auto-offloads sync handlers to the threadpool. If you write an `async def`
   handler, you must explicitly offload blocking calls.

2. **New middleware**: write as pure ASGI (`__call__(self, scope, receive,
   send)`). Never use `BaseHTTPMiddleware` -- it buffers the entire response
   body and blocks streaming.

3. **Blocking code in async context**: wrap in
   `await run_in_threadpool(fn, *args)`. Import from `starlette.concurrency`.

4. **Never block the event loop**: do not call pymongo, `requests.get()`,
   file read/write, or CPU-intensive computation directly inside an
   `async def` function body.

5. **Streaming responses**: use `iterate_in_threadpool()` to wrap synchronous
   iterators for `StreamingResponse`.
