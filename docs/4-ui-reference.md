# UI Routes and View Dispatch

## Overview

All UI routes are defined in `views.py`. The server uses a **data-driven
registration model**: `_VIEW_ROUTES` is a list of route descriptors, and
`_dispatch_view()` is the centralized dispatch function that handles
cross-cutting concerns for every UI request.

## Route table

Routes are declared in `_VIEW_ROUTES` as tuples of:

```python
(handler_function, path, config_dict)
```

Config keys:

| Key | Type | Description |
|-----|------|-------------|
| `renderer` | string | Jinja2 template name (e.g., `"tests.html.j2"`) |
| `require_csrf` | bool | Enforce CSRF validation on POST |
| `require_primary` | bool | Reject POST on non-primary instance (503) |
| `request_method` | string or tuple | Allowed HTTP methods (default: GET + POST) |
| `http_cache` | int | `Cache-Control: max-age=` seconds |
| `direct` | bool | Bypass `_dispatch_view` (for pure redirects) |

At module load time, `_register_view_routes()` iterates over `_VIEW_ROUTES`,
wraps each handler with `_dispatch_view()` (unless `direct=True`), and
registers it on the FastAPI router.

## Registered routes

| Path | Method(s) | Handler | Template | Notes |
|------|-----------|---------|----------|-------|
| `/` | GET, POST | `home` | -- | Redirects to `/tests` (direct) |
| `/login` | GET, POST | `login` | `login.html.j2` | CSRF |
| `/logout` | POST | `logout` | -- | CSRF |
| `/signup` | GET, POST | `signup` | `signup.html.j2` | CSRF |
| `/tests` | GET, POST | `tests` | `tests.html.j2` | Main dashboard |
| `/tests/run` | GET, POST | `tests_run` | `tests_run.html.j2` | CSRF, primary |
| `/tests/modify` | POST | `tests_modify` | -- | CSRF, primary |
| `/tests/stop` | POST | `tests_stop` | -- | CSRF, primary |
| `/tests/approve` | POST | `tests_approve` | -- | CSRF, primary |
| `/tests/purge` | POST | `tests_purge` | -- | CSRF, primary |
| `/tests/delete` | POST | `tests_delete` | -- | CSRF, primary |
| `/tests/view/{id}` | GET, POST | `tests_view` | `tests_view.html.j2` | |
| `/tests/live_elo/{id}` | GET, POST | `tests_live_elo` | `tests_live_elo.html.j2` | |
| `/tests/stats/{id}` | GET, POST | `tests_stats` | `tests_stats.html.j2` | |
| `/tests/tasks/{id}` | GET, POST | `tests_tasks` | `tasks_fragment.html.j2` | |
| `/tests/machines` | GET, POST | `tests_machines` | `machines_fragment.html.j2` | 10s cache |
| `/tests/finished` | GET, POST | `tests_finished` | `tests_finished.html.j2` | |
| `/tests/user/{username}` | GET, POST | `tests_user` | `tests_user.html.j2` | |
| `/actions` | GET, POST | `actions` | `actions.html.j2` | |
| `/contributors` | GET, POST | `contributors` | `contributors.html.j2` | |
| `/contributors/monthly` | GET, POST | `contributors_monthly` | `contributors.html.j2` | |
| `/user/{username}` | GET, POST | `user` | `user.html.j2` | |
| `/user` | GET, POST | `user` | `user.html.j2` | |
| `/user_management` | GET, POST | `user_management` | `user_management.html.j2` | |
| `/workers/{worker_name}` | GET, POST | `workers` | `workers.html.j2` | CSRF |
| `/upload` | GET, POST | `upload` | `nn_upload.html.j2` | CSRF |
| `/nns` | GET, POST | `nns` | `nns.html.j2` | |
| `/sprt_calc` | GET, POST | `sprt_calc` | `sprt_calc.html.j2` | |
| `/rate_limits` | GET, POST | `rate_limits` | `rate_limits.html.j2` | `HX-Request` returns `rate_limits_server_fragment.html.j2` |

## `_dispatch_view()` pipeline

For every UI request (except `direct` routes), `_dispatch_view()` handles the
following steps in order:

1. **Request context assembly** -- calls `get_request_context(request)` to load
   the session and DB handles.
2. **POST body parsing** -- `await request.form()` with configured limits
   (`max_files=2`, `max_fields=200`, `max_part_size=200MB`).
3. **CSRF enforcement** -- if `require_csrf` is set, validates the token from
   the form field or `X-CSRF-Token` header against the session token.
4. **`_ViewContext` construction** -- bundles request, session, POST data,
   path params, and DB handles into a single object passed to the handler.
5. **Primary-instance guard** -- if `require_primary` is set and the instance
   is not primary, returns a 503 HTML response.
6. **Handler execution** -- `await run_in_threadpool(fn, shim)` runs the
   sync handler body in the threadpool.
7. **Redirect handling** -- if the handler returns a `RedirectResponse`, it is
   returned directly (with session commit).
8. **Template rendering** -- if `renderer` is set and the handler returns a
   dict, `render_template_to_response()` renders the Jinja2 template.
9. **Session commit** -- `commit_session_response()` applies remember/forget
   flags to the cookie.
10. **HTTP cache headers** -- `apply_http_cache()` sets `Cache-Control` if
    configured.
11. **Response headers** -- custom headers from the handler are propagated.

## Session handling

### Storage

`FishtestSessionMiddleware` (pure ASGI) manages session persistence. Session
data lives in `request.scope["session"]` as a plain dict, wrapped by
`CookieSession` for helper access.

### Cookie format

- Signed with `itsdangerous.TimestampSigner`.
- Cookie name: `fishtest_session`.
- Encoding: base64(JSON(session_data)), signed.
- Maximum cookie size: 3800 bytes (enforced; flash messages are trimmed if
  exceeded).
- SameSite: `lax`.

### Session keys

| Key | Type | Description |
|-----|------|-------------|
| `user` | string | Authenticated username |
| `csrf_token` | string | CSRF token (generated on first access) |
| `flashes` | dict | Flash message queues (`error`, `warning`, default) |
| `created_at` | string | ISO timestamp of session creation |

### Per-request overrides

- `scope["session_max_age"]` -- overrides cookie `Max-Age` (used by "remember
  me": 1 year).
- `scope["session_secure"]` -- overrides the `Secure` flag.
- `scope["session_force_clear"]` -- forces an expired cookie on the response
  (used by logout).

## CSRF protection

- A token is generated per session on first access (`CookieSession.get_csrf_token()`).
- Validated on every UI POST when `require_csrf` is set in the route config.
- The token can be submitted as:
  - A form field `csrf_token`.
  - An HTTP header `X-CSRF-Token`.
- Validation uses `secrets.compare_digest()` for timing-safe comparison.
- Failure raises HTTP 403.

## Authentication

### Login flow

1. User submits username/password to `POST /login`.
2. `UserDb.authenticate()` validates credentials.
3. On success, `remember(request, username)` sets `session["user"]`.
4. Optional "stay logged in" sets `session_max_age` to 1 year.
5. Redirect to the `next` URL or the referrer.

### Logout flow

1. `POST /logout` calls `forget(request)`.
2. Session dict is cleared and `session_force_clear` is set.
3. Redirect to `/tests`.

### Access control

- `ensure_logged_in(request)` checks `session["user"]`. If absent, redirects
  to `/login` with a flash message.
- Group-based authorization: `userdb.get_user_groups(username)` returns group
  memberships. The `has_permission("approve_run")` method checks for
  `"group:approvers"`.

## URL generation

- Templates use `url_for(route_name, **params)` (Starlette built-in).
- All routes have explicit `name=` for URL generation.
- `static_url(path)` maps to `/static/{path}` with a cache-busting query
  parameter (SHA-384 hash of file content).
- Navigation URLs are provided as a `urls` dict in the base template context.

## Adding a new UI route

1. Write a sync handler function that receives a `_ViewContext` and returns
   either a dict (for template rendering) or a `RedirectResponse`.

2. Add an entry to `_VIEW_ROUTES`:
   ```python
   (my_handler, "/my/path", {"renderer": "mypage.html.j2", "require_csrf": True})
   ```

3. Create the Jinja2 template in `templates/`.

4. Add a contract test in `tests/test_actions_view.py` or a new test file.
