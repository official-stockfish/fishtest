# Developer references

Curated web references and project-specific patterns for the four libraries
that form the fishtest server stack. For server architecture and request
flow, see [1-architecture.md](1-architecture.md). For the threading model
and async/sync boundaries, see [2-threading-model.md](2-threading-model.md).

## FastAPI

### Canonical references

| Topic | URL |
|-------|-----|
| Bigger applications (APIRouter) | https://fastapi.tiangolo.com/tutorial/bigger-applications/ |
| Dependencies overview | https://fastapi.tiangolo.com/tutorial/dependencies/ |
| Dependencies in decorators | https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/ |
| Handling errors | https://fastapi.tiangolo.com/tutorial/handling-errors/ |
| Middleware | https://fastapi.tiangolo.com/tutorial/middleware/ |
| Request forms | https://fastapi.tiangolo.com/tutorial/request-forms/ |
| Request files / UploadFile | https://fastapi.tiangolo.com/tutorial/request-files/ |
| Lifespan events | https://fastapi.tiangolo.com/advanced/events/ |
| Behind a proxy / root_path | https://fastapi.tiangolo.com/advanced/behind-a-proxy/ |
| Templates | https://fastapi.tiangolo.com/advanced/templates/ |
| Testing | https://fastapi.tiangolo.com/tutorial/testing/ |

### Project patterns

**Router structure**: `api.py` and `views.py` each define an `APIRouter`.
`app.py` assembles them with `app.include_router(...)`.

```python
from fastapi import FastAPI
from .api import router as api_router
from .views import router as views_router

# openapi_url is read from OPENAPI_URL env var; defaults to None (disabled
# in production, enables full interactive docs when set in development).
app = FastAPI(lifespan=lifespan, openapi_url=openapi_url)
app.include_router(api_router)
app.include_router(views_router)
```

**No dependency injection**: fishtest does not use FastAPI's `Depends()` /
`Annotated` dependency system. Authentication, CSRF, and session access are
enforced centrally -- in `_dispatch_view` for UI routes and per-handler in the
API router -- not through injected dependencies.

**Lifespan**: Manages MongoDB client, scheduler, and caches. One
`@asynccontextmanager` in `app.py`.

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown
```

**Error shaping**: UI errors return HTML via exception handlers. Worker API
errors return JSON with `{"error": "...", "duration": N}`.

**Sync handlers**: Sync view/API functions are automatically run via
`run_in_threadpool` by Starlette/FastAPI. Most fishtest handlers use
`async def` with explicit `run_in_threadpool` calls for blocking DB work.

**Testing**: tests build the real application with its full middleware stack
and exercise it against a dedicated `fishtest_tests` MongoDB. Because the app
uses no FastAPI dependencies, there are no `app.dependency_overrides`.

## Starlette

### Canonical references

| Topic | URL |
|-------|-----|
| Middleware | https://www.starlette.dev/middleware/ |
| Requests | https://www.starlette.dev/requests/ |
| Responses | https://www.starlette.dev/responses/ |
| Routing / url_for | https://www.starlette.dev/routing/ |
| StaticFiles | https://www.starlette.dev/staticfiles/ |
| Exceptions | https://www.starlette.dev/exceptions/ |
| Lifespan | https://www.starlette.dev/lifespan/ |
| TestClient | https://www.starlette.dev/testclient/ |
| Thread pool | https://www.starlette.dev/threadpool/ |

### Project patterns

**Session middleware**: `FishtestSessionMiddleware` is a pure ASGI middleware
class; it does not subclass Starlette's `SessionMiddleware`. It signs and
verifies the `fishtest_session` cookie directly with
`itsdangerous.TimestampSigner`. Per-request cookie lifetime, the `Secure` flag,
and forced expiry are driven through `scope["session_max_age"]`,
`scope["session_secure"]`, and `scope["session_force_clear"]`. It follows the
pure ASGI middleware shape shown below.

**Pure ASGI middleware** (preferred over `BaseHTTPMiddleware`):

```python
class MyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # pre-processing
        await self.app(scope, receive, send)
```

Current middleware stack (all are pure ASGI):
- Installation order in `app.add_middleware(...)`:
    `HeadMethodMiddleware` -> `ShutdownGuardMiddleware` ->
    `AttachRequestStateMiddleware` ->
    `RejectNonPrimaryWorkerApiMiddleware` -> `RedirectBlockedUiUsersMiddleware` ->
    `FishtestSessionMiddleware`
- Runtime order (outermost -> innermost):
    `FishtestSessionMiddleware` -> `RedirectBlockedUiUsersMiddleware` ->
    `RejectNonPrimaryWorkerApiMiddleware` -> `AttachRequestStateMiddleware` ->
    `ShutdownGuardMiddleware` -> `HeadMethodMiddleware`

**Request form limits** (DOS protection):

```python
post = await request.form(
    max_files=FORM_MAX_FILES,          # UI_FORM_MAX_FILES = 2
    max_fields=FORM_MAX_FIELDS,        # UI_FORM_MAX_FIELDS = 200
    max_part_size=FORM_MAX_PART_SIZE,  # UI_FORM_MAX_PART_SIZE_BYTES = 200 MB
)
```

**URL generation**: `request.url_for("route_name", **path_params)` -- all
routes used by templates must have explicit `name=` parameters.

**Response classes**:
- `HTMLResponse` for UI endpoints
- `JSONResponse` for API endpoints
- `RedirectResponse` for redirects
- `StreamingResponse` for PGN downloads

**Thread pool**: Sync functions and file I/O consume threadpool tokens. Keep
blocking DB and filesystem work off the event loop via `run_in_threadpool`.

## Jinja2

### Canonical references

| Topic | URL |
|-------|-----|
| Template designer docs | https://jinja.palletsprojects.com/en/latest/templates/ |
| API (Environment, autoescape) | https://jinja.palletsprojects.com/en/latest/api/ |
| Starlette templates integration | https://www.starlette.dev/templates/ |
| FastAPI templates integration | https://fastapi.tiangolo.com/advanced/templates/ |

### Project patterns

**Environment setup**: A single `jinja2.Environment` instance is created at
import time with `select_autoescape(["html", "xml", "j2"])`. Custom globals
and filters are registered before any template renders.

**Template rendering**: Synchronous, always off the event loop.

```python
from starlette.templating import Jinja2Templates

templates = Jinja2Templates(env=default_environment())  # custom Environment

@router.get("/page")
async def page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="page.html",
        context={"title": "Page"},
    )
```

**Key rules**:
- `Jinja2Templates.TemplateResponse()` injects `request` into the context if it
    is missing, but repository code still passes it explicitly and relies on it
    being present for `url_for` and shared context builders.
- `Jinja2Templates` accepts `directory=` or `env=`, not both.
- `TemplateResponse` exposes `.template` and `.context` for test assertions.
- Context processors must be sync functions.
- JS data is passed via `{{ value|tojson }}`.

**Registered globals** (repository-specific):

| Global | Source |
|--------|--------|
| `url_for` | Injected by Starlette |
| `static_url` | `server/fishtest/http/jinja.py` |
| `poll` | `server/fishtest/http/jinja.py` |
| `htmx.input_changed_delay_ms` | `server/fishtest/http/jinja.py` |
| Formatting helpers | `server/fishtest/http/template_helpers.py` |
| `gh`, `fishtest` | registered in `server/fishtest/http/jinja.py` |

**Autoescaping**: Enabled for `.html`, `.xml`, `.j2` extensions. Raw HTML
must use `{{ value|safe }}` or `{% autoescape false %}`.

## htmx

### Canonical references

| Topic | URL |
|-------|-----|
| Documentation | https://four.htmx.org/docs |
| Reference index | https://four.htmx.org/reference |
| Swap | https://four.htmx.org/reference/attributes/hx-swap |
| OOB swaps | https://four.htmx.org/reference/attributes/hx-swap-oob |
| Status-scoped behavior | https://four.htmx.org/reference/attributes/hx-status |
| Push URL | https://four.htmx.org/reference/attributes/hx-push-url |
| Indicator | https://four.htmx.org/reference/attributes/hx-indicator |
| Sync / request coordination | https://four.htmx.org/reference/attributes/hx-sync |
| Triggers | https://four.htmx.org/reference/attributes/hx-trigger |
| Swap event | https://four.htmx.org/reference/events/htmx-after-swap |
| Empty swap after OOB | https://four.htmx.org/reference/config/htmx-config-allowEmptySwapAfterOOB |
| What's new in htmx 4 | https://four.htmx.org/docs/whats-new-in-htmx-4 |
| Template fragments essay | https://htmx.org/essays/template-fragments/ |
| Hypermedia Systems (book) | https://hypermedia.systems/ |
| Web security with htmx | https://htmx.org/essays/web-security-basics-with-htmx/ |
| `Vary` (MDN) | https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Vary |
| Search inputs (MDN) | https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/search |
| Search clear pseudo-element (MDN) | https://developer.mozilla.org/en-US/docs/Web/CSS/::-webkit-search-cancel-button |
| Search event (MDN) | https://developer.mozilla.org/en-US/docs/Web/API/HTMLInputElement/search_event |
| `aria-sort` (MDN) | https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Attributes/aria-sort |
| `visibilitychange` (MDN) | https://developer.mozilla.org/en-US/docs/Web/API/Document/visibilitychange_event |

### Project patterns

**CDN loading**: htmx 4.0.0 is loaded from `cdn.jsdelivr.net` in
`base.html.j2` with an SRI integrity hash. No npm build step, and no htmx
extensions.

```html
<script src="https://cdn.jsdelivr.net/npm/htmx.org@4.0.0/dist/htmx.min.js"
    integrity="sha256-5ITZFxqdswo5yPFuPXCdQTfzIRxln45hJYFmNQM9WT8="
    crossorigin="anonymous"
    referrerpolicy="no-referrer"></script>
```

**Response swapping**: htmx swaps every response whose status is not listed in
`htmx.config.noSwap`, which holds `204` and `304`. This server answers errors
with whole pages rather than partials sized for a swap target, so the `<body>`
element in `base.html.j2` states the policy for the whole document:

```html
<body
  hx-status:4xx:inherited="swap:none push:false"
  hx-status:5xx:inherited="swap:none push:false"
>
```

`:inherited` carries the attribute to every descendant, so an element-level
request and an `htmx.ajax()` call from `<body>` are both covered. Declare the
policy in one of the two places, never both: htmx consults `hx-status` only
for a code that `noSwap` does not already claim, and a `noSwap` hit returns
before the attribute is read.

A suppressed status still runs the swap pipeline with swap `none`, so
`htmx:after:swap` fires for `4xx` and `5xx`. Handlers that record load state
must check the response status.

`swap:none push:false` reaches the main swap and the history entry. The title
is adopted after the swap and out-of-band elements in the response body are
applied regardless, neither of them gated on the status, so a whole error page
would still rename the tab and overwrite any element whose id it collides with.
`application.js` closes both with a document-level `htmx:before:swap` guard
that clears `detail.ctx.title` and empties `detail.tasks`, the array htmx
iterates to perform every swap in the response, main and out-of-band alike.

**Settle phase**: `htmx.config.defaultSettleDelay` is `0`, which skips settling
altogether. The phase exists to animate a swap through the `htmx-settling` and
`htmx-added` classes, and it reaches that by copying the attributes of each
replaced element onto its replacement and restoring the response's own
attributes one tick later. The restore writes the `value` property of an input
only when that input does not hold focus, and htmx restores focus before it
settles, so a field being typed in while its own subtree is swapped keeps the
`value` attribute copied off the element it replaced. No stylesheet here
targets either class.

**Swap events**: htmx fires one `htmx:before:swap` / `htmx:after:swap` pair per
response, both on the element that issued the request. Only `htmx:before:swap`
carries the swapped elements, in `detail.tasks`. `application.js` provides
`onHtmxSwap(matches, callback)` and `htmxSwapSucceeded(event)` for this;
listeners that skip the target filter fire on every request the page makes,
including the sidebar poll present on every page.

`swap()` awaits the swap tasks between the two events, so two responses in
flight interleave and the pair cannot be joined by arrival order.
`onHtmxSwap` keys pending targets on `detail.ctx`, the request context both
events carry.

`detail.tasks` names the element a swap targeted, which for `outerHTML` and
`delete` is detached by the time the pair closes. `onHtmxSwap` resolves each
target to what the swap left in the document -- the replacement carries the
same `id` -- and drops the ones that left nothing. Callers therefore never need
a document-wide fallback, which matters because `hx-swap-oob="true"` means
`outerHTML` and the hidden sort/order/page inputs carry it on nearly every poll
response the app sends.

**Source versus target**: htmx dispatches `htmx:before:swap` and
`htmx:after:swap` on the element that *issued* the request, not on the element
that was swapped. An element-level listener on a swap target therefore only
sees requests that element issued itself. Where a region is filled from more
than one place -- its own poll trigger and a filter form, say -- match on the
target with `onHtmxSwap` instead.

**Aborted requests**: htmx reports an aborted fetch through `htmx:error`, the
same event a network failure uses, and logs it at error level. Aborts are
routine here: `hx-sync` names a queue on the filter form, the form itself
carries no `hx-sync`, so a keystroke in the filter aborts an in-flight poll on
that queue, and htmx applies a 60s default timeout. `application.js` provides
`htmxRequestAborted(event)`; handlers that reset load state must call it, or a
cancelled tick is shown to the reader as a failure while its replacement is
already in flight.

**Detail-page diff renderer**: `/tests/view/{id}` loads jsdiff from
`cdn.jsdelivr.net` in `tests_view.html.j2` for the inline Diff panel. The
asset is pinned and protected with SRI.

```html
<script src="https://cdn.jsdelivr.net/npm/diff@9.0.0/dist/diff.min.js"
    integrity="sha256-tRqdKIXywJDcl7mBAnOV9+fmVYpGx1rjdH2yZ5E6ias="
    crossorigin="anonymous"
    referrerpolicy="no-referrer"></script>
```

**Fragment detection in Starlette/FastAPI**: htmx sends `HX-Request: true`
on every request it makes, and `HX-Request-Type` stating the scope of the
swap. `partial` targets a region of the current page; `full` replaces the
document, which is what a boosted navigation asks for. A back navigation names
itself with `HX-History-Restore-Request` and carries `HX-Request-Type: full`,
but no `HX-Request`: the restore passes its own request object, which replaces
the core headers, and only the request type is added back afterwards. The
server rejects each of those cases by name instead of requiring `partial`, so
a header rename degrades to treating every htmx request as a fragment request
rather than swapping whole pages into fragment targets:

```python
def _is_hx_request(request) -> bool:
    headers = getattr(request, "headers", None)
    if headers is None:
        return False
    if (headers.get("HX-Request") or "").lower() != "true":
        return False
    if (headers.get("HX-History-Restore-Request") or "").lower() == "true":
        return False
    if (headers.get("HX-Request-Type") or "").lower() == "full":
        return False
    return (headers.get("Sec-Fetch-Mode") or "").lower() != "navigate"
```

**Dual-mode rendering with Jinja2**: the view handler renders either a
fragment template or the full-page template from the same URL. The
`_render_hx_fragment()` helper encapsulates the check-and-render pattern:

```python
def _render_hx_fragment(request, template_name, context):
    if not _is_hx_request(request):
        return None
    return render_template_to_response(
        request=request.raw_request,
        template_name=template_name,
        context=build_template_context(
            request.raw_request, request.session, context
        ),
    )
```

Fragment templates are standalone `.html.j2` files that do not extend
`base.html.j2`. This avoids partial-block rendering complexity and keeps
fragments self-contained.

**Content fragments for stateful tables**: stateful list pages do not return only
row fragments. They return content fragments (`contributors_content_fragment`,
`user_management_content_fragment`, `workers_content_fragment`) so that view
toggles, truncation banners, pagination, and sort state remain synchronized
with the table body.

**Vary header for HTTP caching**: when the same URL can return either a
full page or a fragment, both request headers must appear in `Vary` so that
HTTP caches (nginx, CDNs) store separate representations:

```python
_append_vary_header(response, "HX-Request")
_append_vary_header(response, "HX-Request-Type")
```

Both tokens are needed: `HX-Request-Type` is what separates a fragment request
from a boosted navigation to the same URL, so keying on `HX-Request` alone lets
a cache return a stored fragment for one. Use the same `Vary` value on the
full-page response, the fragment response, and any `304 Not Modified` response
for that URL.

**OOB swaps with Jinja2**: out-of-band elements carry `hx-swap-oob`
attributes directly in the template markup, and one response can update many
elements. Rows need a `<template>` wrapper because a `<tr>` cannot stand on
its own in parsed HTML.

Put `id` and `hx-swap-oob` on the `<template>` element itself. htmx locates
out-of-band elements with `querySelectorAll`, which does not descend into
template content, so an `hx-swap-oob` on an element inside the wrapper is
silently ignored and the swap never happens. htmx strips the wrapper before
applying the swap.

```jinja
{# OOB element that can stand alone -- no wrapper #}
<span id="count" hx-swap-oob="innerHTML">{{ count }}</span>

{# OOB rows -- wrapper carries the id and the swap #}
<template id="my-table" hx-swap-oob="innerHTML">
  {% for row in rows %}
    <tr>...</tr>
  {% endfor %}
</template>
```

Only wrap what the parser requires. A `<div>` or `<span>` target needs no
`<template>`.

**Polling lifecycle**: htmx clears a poll interval only when the element
carrying `hx-trigger="every Ns"` leaves the document. Put the trigger on a
dedicated driver element that is never the swap target, and end the poll from
the response body:

- **200** -- swap the response content, continue polling.
- **204** -- no content change; htmx skips the swap, continues polling.
- **200 with a driver-removing element** -- terminal state:

```jinja
<div id="{{ poller_id }}" hx-swap-oob="delete"></div>
```

A status code cannot stop a poll.

**Request coordination**: `hx-sync` is used where user actions and polling can
target the same fragment. The main repo pattern is
`hx-sync="#machines-filters:abort"`, which puts the poll driver and the
sort/pagination links on the queue owned by the filter form. `abort` means
*drop this request while one is in flight on that queue*, so it is the poll
that yields: the filter form declares no `hx-sync` of its own, which leaves it
on the default `queue first` strategy, and htmx aborts an in-flight `abort`
request to run it. A sort or pagination click that lands inside a poll's
request window is dropped rather than queued.

**Attribute inheritance**: htmx applies an ancestor's attribute to a
descendant only where the ancestor marks it `:inherited`, for example
`hx-target:inherited="#output"`. Sort and pagination links inside a filter
form therefore inherit nothing and send only their own query string. A `GET`
collects the enclosing form only when the requesting element is the form
itself.

**Search portability**: `input changed delay:{{ htmx.input_changed_delay_ms }}ms`
is the portable search trigger baseline. Native `search` events and
`::-webkit-search-cancel-button` styling are browser-specific enhancements,
not the correctness contract. Search inputs keep visible labels or another
valid accessible name.

**Conditional polling with visibility**: polls are gated on tab visibility
to avoid unnecessary server load. The condition goes on the `every` token
itself, with the interval after it:

```html
<div hx-get="/endpoint"
     hx-trigger="every[document.visibilityState === 'visible'] 30s"
     hx-swap="none">
</div>
```

The token order matters and the failure is silent. htmx splits a trigger into
one leading token plus modifiers, and reads a `[condition]` filter off the
leading token only (`#parseTriggerSpecs` then `#extractFilter`). Written the
other way round, `every 30s [document.visibilityState === 'visible']` parses as
the bare event `every`: the interval is still read out of the modifier bag, so
the poll works, but the condition is swallowed as junk keys and never
evaluated. The poll then runs in hidden tabs and behind collapsed panels, with
nothing in the console to say so.
`test_poll_conditions_are_attached_to_the_every_token` in
`test_http_boundary.py` guards the whole template tree against that form.

Treat the transition to `hidden` as the point to stop background UI updates.

**Focus-return immediate refresh**: every visibility-gated poller also
triggers on `visibilitychange` so that returning to the tab produces an
immediate update instead of waiting for the next poll cycle. A named event
carries its own filter directly, with no space before the bracket:

```html
<div hx-get="/endpoint"
     hx-trigger="every[document.visibilityState === 'visible'] 30s,
                 visibilitychange[document.visibilityState === 'visible'] from:document"
     hx-swap="none">
</div>
```

Section-scoped pollers (machines, tasks) combine both the tab visibility and
section expanded state in a single filter expression:

```html
<div hx-get="/endpoint"
     hx-trigger="every[document.visibilityState === 'visible'
                 && document.getElementById('section').classList.contains('show')] 120s,
                 visibilitychange[document.visibilityState === 'visible'
                 && document.getElementById('section').classList.contains('show')] from:document"
     hx-swap="innerHTML">
</div>
```

**Error recovery in JavaScript**: retry buttons in htmx error handlers
must be constructed with DOM API (`createElement`, `textContent`,
`setAttribute`) rather than string concatenation with `innerHTML`, to
prevent XSS from error messages and to keep htmx attributes functional
(via `htmx.process()`).

## Python, MongoDB, and tooling

### Canonical references

| Topic | URL |
|------|-----|
| Python 3.14 docs | https://docs.python.org/3.14/ |
| MongoDB manual | https://www.mongodb.com/docs/manual/ |
| PyMongo | https://www.mongodb.com/docs/languages/python/pymongo-driver/current/ |
| Ruff | https://docs.astral.sh/ruff/ |
| ty | https://docs.astral.sh/ty/ |
| mypy | https://mypy.readthedocs.io/en/stable/ |
| nginx | https://nginx.org/en/docs/ |

Use [7-development.md](7-development.md) for local lint and test workflows.

## Tooling references

| Tool | Path | Purpose |
|------|------|---------|
| Repository dev tools | `pyproject.toml` | Shared repo tooling configuration |
| Server Python project | `server/pyproject.toml` | Server dependency and tool configuration |
| Worker Python project | `worker/pyproject.toml` | Worker dependency configuration |
| Server test package | `server/tests/` | Unit and HTTP contract tests |

## Testing patterns

### Test structure

Server tests live in `server/tests/`. All tests use `unittest.TestCase`.
MongoDB is required for most tests (the CI workflow starts `mongod` before
running the suite). User-facing HTTP route tests are split by route family or
one focused UI motif instead of accumulating in one omnibus module.

### Fixtures

Most test files import `test_support`, which provides:

- `get_rundb()`: returns a `RunDb` connected to the test MongoDB instance.
- `build_test_app(...)`: constructs a FastAPI `TestApplication` with selectable
  API and views routers.
- `make_test_client(...)`: wraps `build_test_app` in a Starlette `TestClient`.
- `cleanup_test_rundb(...)`: drops test collections after a test class runs.
- `find_run(...)`: retrieves a run from the database by field match.
- `extract_csrf_token(html)`: parses a CSRF token from rendered HTML.

User-facing UI route modules also reuse `ui_user_test_case.py` for shared
client setup, login helpers, run creation, and DB cleanup.

Worker-related fixtures must match the `short_worker_name` pattern
(`.*-[\d]+cores-[a-zA-Z0-9]{2,8}`) or `WorkerDb.update_worker()` schema
validation fails.

### Key test modules

| Module | Coverage |
|--------|----------|
| `test_app.py` | Application startup, middleware, lifespan |
| `test_api.py` | Worker API protocol (request_task, update_task, beat) |
| `test_users.py` | Login, signup, remember-me, userdb auth flags, basic UI smoke |
| `test_views_admin.py` | Workers, user-management, rate-limits, and shared admin UI contracts |
| `test_views_tests.py` | `/tests` and `/tests/user/{username}` filter state and live-table polling |
| `test_views_actions.py` | Actions search, pagination, sorting |
| `test_views_contributors.py` | Contributors search, rank jump, sorting, and HTMX state sync |
| `test_views_detail.py` | `/tests/view/{id}` detail polling, `/tests/tasks/{id}`, and task UI assets |
| `test_views_finished.py` | Finished-runs search and pagination |
| `test_views_helpers.py` | Shared pagination, parameter, and merge helpers |
| `test_views_machines.py` | Machines helper behavior plus `/tests/machines` HTTP contracts |
| `test_views_run.py` | Run-form validation, SPSA parsing, permissions, and run action routes |
| `test_spsa_workflow.py` | Shared classic SPSA form, worker update, and chart-payload helper contracts |
| `test_http_boundary.py` | HTTP boundary invariants and template contracts |
| `test_http_dependencies.py` | Request-state dependency wiring |
| `test_http_errors.py` | API vs UI error shaping |
| `test_http_helpers.py` | Jinja/static helpers and shared HTTP utilities |
| `test_http_middleware.py` | Middleware behavior and blocked-user flow |
| `test_http_settings.py` | Runtime settings and environment parsing |
| `test_http_ui_session_semantics.py` | Session commit and UI CSRF semantics |
| `test_nn.py` | Neural network upload and listing |
