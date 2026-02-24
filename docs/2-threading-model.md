# Threading Model

## Principle

The ASGI event loop is a thin HTTP dispatcher. All blocking work runs in
Starlette's default threadpool via `run_in_threadpool()`.

The async event loop holds all concurrent connections (thousands) while
only a fraction simultaneously occupy threadpool slots for blocking
MongoDB/lock work. Connection acceptance is decoupled from handler
execution -- Uvicorn can accept 10,000+ worker connections natively.

The threadpool size is configured by `THREADPOOL_TOKENS` in
`http/settings.py` (currently 200). This is set during lifespan startup via
`current_default_thread_limiter().total_tokens`. The value must be large
enough to avoid queuing under sustained load (9,400+ concurrent workers
proven in production), but not so large that it overwhelms MongoDB or
CPU resources.

Application-level throttling (`task_semaphore(TASK_SEMAPHORE_SIZE)` +
`request_task_lock` in `rundb.py`) governs the scheduling critical path,
not the HTTP layer. Both `THREADPOOL_TOKENS` and `TASK_SEMAPHORE_SIZE`
are defined in `http/settings.py`.

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

## Task scheduling throttle

`/api/request_task` is the highest-contention endpoint. It is serialised
internally by `request_task_lock` (a mutex), so only **1 thread** does
useful scheduling work at any time. Every thread that enters `request_task()`
holds one AnyIO threadpool token for its full duration -- **including**
while blocked on the mutex.

### Call chain (per request)

```
event loop  ->  run_in_threadpool(api.request_task)   [1 AnyIO token]
  threadpool  ->  task_semaphore.acquire(False)       [non-blocking gate]
    threadpool  ->  request_task_lock                 [blocking mutex]
      sync_request_task(...)                          [MongoDB + iteration]
```

### The problem: burst-driven token starvation

At steady state (~200 workers) `request_task` traffic is negligible.
But worker reconnection bursts change the picture dramatically.

Observed burst in tests:

| Time  | Workers | Delta workers | Delta time |
|-------|--------:|----------:|--------|
| 14:47 |     205 |      --   |     -- |
| 15:05 |   4,608 |  +4,403   | 18 min |
| 15:20 |   9,116 |  +4,508   | 15 min |
| 15:23 |   9,418 |    +302   |  3 min |

During these bursts hundreds of workers call `/api/request_task`
simultaneously. Without a cap **all 200 tokens** could fill with
mutex-waiters doing zero useful work -- and **starve** the endpoints
that *must* proceed promptly:

| Endpoint | Rate at 10k workers | Starvation impact |
|----------|--------------------:|-------------------|
| `/api/beat`        | ~83 req/s (10k x 1/120 s) | Missed beats -> server reclaims active tasks |
| `/api/update_task` | ~7.4 req/s (observed)     | Lost game results -> spurious dead-task scavenges |

The `task_semaphore` gates entry so that at most `TASK_SEMAPHORE_SIZE`
threads can hold tokens for `request_task` at any time. The next caller
gets an immediate "server busy" response (zero token impact) and retries
after a short backoff -- harmless because `task_duration` is 30 minutes.

### Why `TASK_SEMAPHORE_SIZE = 5` when `THREADPOOL_TOKENS = 200`

The value is grounded in production measurements from the 9,423-worker
run.

**Measured endpoint latencies**:

| Endpoint | Observed p50 | Tokens held (Little's Law: L = lambda * W) |
|----------|-------------:|----------------------------------------|
| `/api/beat`            | 6 ms  | 83 req/s * 0.006 s = **0.5** |
| `/api/update_task`     | 7 ms  | 7.4 req/s * 0.007 s = **0.05** |
| `/api/request_version` | 4 ms  | 18.1 req/s * 0.004 s = **0.07** |
| `/api/request_task`    | 15 ms | serialised -> **<= 1 active** |

Under steady state all endpoints together occupy < 1 token.
The risk is entirely in **bursts**.

**Token budget during a reconnection burst (worst case):**

```
  THREADPOOL_TOKENS                          200
- TASK_SEMAPHORE_SIZE (request_task cap)       5  (2.5 %)
-----------------------------------------------
Tokens available for everything else         195  (97.5 %)
```

Of those 5 tokens:
- **1** is inside the lock doing actual work (~15 ms per call).
- **4** are a standing queue absorbing arrival jitter.

**Why not fewer (e.g. 2)?**
During the observed Phase 3 burst, `request_task` arrival rate spiked to
~20 req/s. With a lock hold time of 15 ms, the probability of > 1
arrival during a single lock hold is ~26%. A queue depth of 4 absorbs
this jitter without rejecting the majority of callers.

**Why not more (e.g. 10)?**
The lock is the throughput bottleneck -- only 1 thread executes regardless
of queue depth. 10 slots would pin 10 tokens (5 %) on mutex-waiters
for zero throughput gain, and double the worst-case starvation exposure
for beat/update_task.

**Production validation** (9,423 workers, 63+ min stable):
- "Too busy" rejections:    **3** total (was 729 before THREADPOOL_TOKENS=200)
- HTTP 503s from Uvicorn:   **0**
- Process crashes:          **0**
- Dead tasks (server-side): **0**

### Where the constants live

Both `THREADPOOL_TOKENS` and `TASK_SEMAPHORE_SIZE` are defined in
`fishtest/http/settings.py` -- a dependency-free module that neither
`app.py` nor `rundb.py` imports from each other, avoiding circular
imports.
