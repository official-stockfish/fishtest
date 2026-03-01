# Developer references

Curated web references and project-specific patterns for the four libraries
that form the fishtest server stack.

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

**Dependency injection with `Annotated`**: Reusable typed aliases for
request-scoped dependencies (session data, DB handles, auth checks).

```python
from typing import Annotated
from fastapi import Depends

CurrentUser = Annotated[User, Depends(get_current_user)]

@router.post("/endpoint", dependencies=[Depends(check_csrf)])
async def handler(user: CurrentUser):
    ...
```

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

**Dependency overrides for testing**:

```python
app.dependency_overrides[get_db] = lambda: mock_db
```

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

**Session middleware**: `FishtestSessionMiddleware` (a thin subclass of
Starlette's `SessionMiddleware`) uses `itsdangerous.TimestampSigner` to sign
cookies. Per-request `max_age` is supported via `scope["session_max_age"]`.

```python
SessionMiddleware(
    app,
    secret_key="...",
    session_cookie="fishtest_session",
    max_age=None,            # session cookie by default
    same_site="lax",
    https_only=False,        # set per-request via X-Forwarded-Proto
)
```

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
form = await request.form(
    max_files=1,
    max_fields=20,
    max_part_size=200 * 1024 * 1024,
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

templates = Jinja2Templates(directory="templates")

@router.get("/page")
async def page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="page.html",
        context={"title": "Page"},
    )
```

**Key rules**:
- `request` must always be in the template context (required by `url_for`).
- `Jinja2Templates` accepts `directory=` or `env=`, not both.
- `TemplateResponse` exposes `.template` and `.context` for test assertions.
- Context processors must be sync functions.
- JS data is passed via `{{ value|tojson }}`.

**Registered globals** (available in all templates):

| Global | Source |
|--------|--------|
| `url_for` | Injected by Starlette |
| `active_runs` | View builder |
| `request` | Starlette context injection |
| `flash_messages` | Session middleware |
| Custom helpers | Registered in `app.py` at startup |

**Autoescaping**: Enabled for `.html`, `.xml`, `.j2` extensions. Raw HTML
must use `{{ value|safe }}` or `{% autoescape false %}`.

## htmx

### Canonical references

| Topic | URL |
|-------|-----|
| Documentation | https://htmx.org/docs/ |
| Attributes reference | https://htmx.org/reference/ |
| Events reference | https://htmx.org/events/ |
| Request/response headers | https://htmx.org/reference/#headers |
| Configuration | https://htmx.org/docs/#config |
| Polling | https://htmx.org/docs/#polling |
| OOB swaps | https://htmx.org/docs/#oob_swaps |
| OOB troublesome tables | https://htmx.org/attributes/hx-swap-oob/#troublesome-tables-and-lists |
| Push URL | https://htmx.org/attributes/hx-push-url/ |
| Indicator | https://htmx.org/attributes/hx-indicator/ |
| Multiple triggers | https://htmx.org/attributes/hx-trigger/ |
| Template fragments essay | https://htmx.org/essays/template-fragments/ |
| Web security with htmx | https://htmx.org/essays/web-security-basics-with-htmx/ |

### Project patterns

**CDN loading**: htmx 2.0.8 is loaded from `cdn.jsdelivr.net` in
`base.html.j2` with an SRI integrity hash. No npm build step.

```html
<script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.8/dist/htmx.min.js"
        integrity="sha384-..." crossorigin="anonymous"></script>
```

**Fragment detection in Starlette/FastAPI**: htmx sends `HX-Request: true`
on every AJAX request. The server detects this header to decide between
full-page and fragment rendering. A `Sec-Fetch-Mode` guard prevents
htmx-boosted full-page navigations from being treated as fragment requests:

```python
def _is_hx_request(request) -> bool:
    headers = getattr(request, "headers", None)
    if headers is None:
        return False
    if (headers.get("HX-Request") or "").lower() != "true":
        return False
    if (headers.get("Sec-Fetch-Mode") or "").lower() == "navigate":
        return False
    return True
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

**Vary header for HTTP caching**: when the same URL can return either a
full page or a fragment, `Vary: HX-Request` must be set on the response so
that HTTP caches (nginx, CDNs) store separate representations:

```python
_append_vary_header(response, "HX-Request")
```

**OOB swaps with Jinja2**: out-of-band elements carry `hx-swap-oob`
attributes directly in the template markup. Multiple elements can be updated
in a single response. For table rows, `<template>` wrappers are required
because the HTML parser rejects `<tbody>` inside `<div>`:

```jinja
{# OOB span -- works directly #}
<span id="count" hx-swap-oob="innerHTML">{{ count }}</span>

{# OOB table body -- requires template wrapper #}
<template>
  <tbody id="my-table" hx-swap-oob="innerHTML">
    {% for row in rows %}
      <tr>...</tr>
    {% endfor %}
  </tbody>
</template>
```

**Polling lifecycle codes**: polled endpoints use HTTP status codes to
control client behavior:
- **200** -- swap the response content, continue polling.
- **204** -- no content change; htmx skips the swap, continues polling.
- **286** -- swap the response and stop polling (terminal state).

**Conditional polling with visibility**: polls are gated on tab visibility
to avoid unnecessary server load:

```html
<div hx-get="/endpoint"
     hx-trigger="every 30s [document.visibilityState === 'visible']"
     hx-swap="none">
</div>
```

**Error recovery in JavaScript**: retry buttons in htmx error handlers
must be constructed with DOM API (`createElement`, `textContent`,
`setAttribute`) rather than string concatenation with `innerHTML`, to
prevent XSS from error messages and to keep htmx attributes functional
(via `htmx.process()`).

## Tooling references

| Tool | Command / Path | Purpose |
|------|----------------|---------|
| Lint script | `cd server && uv run ruff check .` | Ruff linting with `target-version = \"py314\"` |
| Type check | `cd server && uv run ty check fishtest/app.py fishtest/http/` | Type checking for ASGI entrypoint and HTTP modules |
| Local test runner | `cd server && uv run python -m unittest discover -s tests -q` | Run the full test suite |
