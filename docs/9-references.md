# Developer references

Curated web references and project-specific patterns for the three frameworks
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

## Tooling references

| Tool | Command / Path | Purpose |
|------|----------------|---------|
| Lint script | `cd server && uv run ruff check .` | Ruff linting with `target-version = \"py314\"` |
| Type check | `cd server && uv run ty check fishtest/app.py fishtest/http/` | Type checking for ASGI entrypoint and HTTP modules |
| Local test runner | `cd server && uv run python -m unittest discover -s tests -q` | Run the full test suite |
