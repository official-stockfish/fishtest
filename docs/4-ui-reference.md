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
| `/tests/live_elo/{id}` | GET, POST | `tests_live_elo` | `tests_live_elo.html.j2` | Live Elo page + dual-scale gauge |
| `/tests/stats/{id}` | GET, POST | `tests_stats` | `tests_stats.html.j2` | |
| `/tests/tasks/{id}` | GET, POST | `tests_tasks` | `tasks_fragment.html.j2` | Fragment-only |
| `/tests/machines` | GET, POST | `tests_machines` | `machines_fragment.html.j2` | Fragment-only, 10s cache |
| `/tests/elo/{id}` | GET, POST | `tests_elo` | `elo_results_fragment.html.j2` | Fragment-only (OOB) |
| `/tests/elo_batch` | GET, POST | `tests_elo_batch` | `elo_batch_fragment.html.j2` | Fragment-only (OOB batch) |
| `/tests/live_elo_update/{id}` | GET, POST | `live_elo_update` | `live_elo_fragment.html.j2` | Fragment-only (OOB) |
| `/tests/finished` | GET, POST | `tests_finished` | `tests_finished.html.j2` | HX: `tests_finished_content_fragment` |
| `/tests/user/{username}` | GET, POST | `tests_user` | `tests_user.html.j2` | HX: `tests_user_content_fragment` |
| `/actions` | GET, POST | `actions` | `actions.html.j2` | HX: `actions_content_fragment` |
| `/contributors` | GET, POST | `contributors` | `contributors.html.j2` | HX: `contributors_content_fragment`; paginated (100/page) |
| `/contributors/monthly` | GET, POST | `contributors_monthly` | `contributors.html.j2` | HX: `contributors_content_fragment`; paginated (100/page) |
| `/user/{username}` | GET, POST | `user` | `user.html.j2` | |
| `/user` | GET, POST | `user` | `user.html.j2` | |
| `/user_management` | GET, POST | `user_management` | `user_management.html.j2` | HX: `user_management_content_fragment` |
| `/workers/{worker_name}` | GET, POST | `workers` | `workers.html.j2` | CSRF; HX: `workers_content_fragment` |
| `/upload` | GET, POST | `upload` | `nn_upload.html.j2` | CSRF |
| `/nns` | GET, POST | `nns` | `nns.html.j2` | HX: `nns_content_fragment` |
| `/sprt_calc` | GET, POST | `sprt_calc` | `sprt_calc.html.j2` | |
| `/rate_limits` | GET, POST | `rate_limits` | `rate_limits.html.j2` | |
| `/rate_limits/server` | GET, POST | `rate_limits_server` | `rate_limits_server_fragment.html.j2` | Fragment-only |

Route notes:
- **Fragment-only**: endpoint always returns a fragment template (no full page).
- **HX**: dual-mode endpoint; returns the named fragment when `HX-Request: true`
  is present, otherwise renders the full-page template.
- **OOB**: fragment contains `hx-swap-oob` attributes for multi-element updates.

## `/tests/elo/{id}` expected-state contract

The detail-page ELO poller sends an optional `expected` query parameter that
captures the state the page already shows (`active` or `paused`). The handler
compares that value to the current run state before responding:

- `204` when the current state still matches `expected`.
- `200` when the state changed and the page needs fresh OOB content.
- `286` when the run is terminal (`finished` or `failed`).

Without `expected`, the handler follows the older fragment-only contract:

- `200` for active runs.
- `204` for non-active non-terminal runs.
- `286` for terminal runs.

## `/tests/live_elo/{id}` gauge scale contract

The Live Elo page renders three Google gauges (LOS, LLR, Elo) and keeps the
details table in sync through `/tests/live_elo_update/{id}` OOB swaps.

The Elo gauge supports two display modes:

- Fixed mode (default): fixed gauge range `[-4, +4]` for visual consistency.
- Dynamic mode: auto range chosen from the smallest symmetric power-of-two
   interval that covers the current Elo value and confidence interval.

Switching modes:

- Clicking the Elo gauge toggles between fixed and dynamic mode.
- Keyboard activation on the Elo gauge (`Enter` or `Space`) also toggles modes.

Value display rule:

- The gauge reports the real uncapped Elo value from the server.
- In fixed mode, the gauge needle is visually limited by the selected range.

## htmx fragment dispatch

Dual-mode endpoints (marked **HX** in the route table) serve either a full
HTML page or a fragment, from the same URL, based on request headers.

### Detection: `_is_hx_request(request)`

Returns `True` when all of the following hold:

1. The request carries `HX-Request: true` (case-insensitive).
2. `Sec-Fetch-Mode` is not `navigate` (blocks full-page navigations that
   carry `HX-Request` due to htmx-boosted links or browser prefetch).

### Rendering: `_render_hx_fragment(request, template_name, context)`

Convenience wrapper that checks `_is_hx_request()` and, when true, renders
the fragment template via `render_template_to_response()`. Returns `None`
for non-htmx requests, allowing the caller to fall through to full-page
rendering. Typical usage:

```python
return (
    _render_hx_fragment(request, "my_fragment.html.j2", context)
    or context
)
```

Or, when the htmx context differs from the full-page context:

```python
hx = _render_hx_fragment(request, "my_fragment.html.j2", hx_context)
if hx:
    return hx
return full_page_context
```

### `Vary: HX-Request` header

`_dispatch_view()` appends `Vary: HX-Request` to every GET response
(both fragment and full-page). This tells HTTP caches (nginx, CDNs,
browsers) that the response body depends on the `HX-Request` header,
preventing a cached fragment from being served as a full page or vice versa.

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
11. **Vary header** -- `Vary: HX-Request` is appended to every GET response
    (see htmx fragment dispatch above).
12. **Response headers** -- custom headers from the handler are propagated.

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

Cookie ownership is split intentionally:

- `http/settings.py` owns cookie policy values such as size limits and
   persistence windows.
- `http/cookie_session.py` owns the session cookie transport contract such as
   the cookie name, SameSite default, secret resolution, and request-scope
   override helpers.

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

## Cookie workflow

The UI uses two cookie families with different ownership and lifecycles:

- **Session/auth cookie** -- `fishtest_session`, emitted by
   `FishtestSessionMiddleware`.
- **UI state cookies** -- lightweight browser-side preferences such as `theme`,
   `contributors_findme`, `machines_state`, and the homepage workers filters.

### Session cookie lifecycle

1. `FishtestSessionMiddleware` reads `fishtest_session` at request start and
    decodes the signed JSON payload into `scope["session"]`.
2. `load_session()` wraps that dict in `CookieSession`, which lazily creates
    `created_at` and the CSRF token on first access.
3. Rendering most full-page templates touches `session.get_csrf_token()`, so a
    previously empty session becomes dirty during the response.
4. On login, `remember()` writes `session["user"]` and optionally stores a
    persistent max-age marker for "remember me" behavior.
5. On logout, `forget()` clears the session and marks the response to emit an
    expired cookie.
6. `commit_session_response()` translates those flags into request-scope
    overrides, and `FishtestSessionMiddleware` finally appends the `Set-Cookie`
    header on the outbound response.

### UI state cookie lifecycle

UI state cookies are intentionally separate from the signed session payload.
They are written by page-specific JS or server helpers because they do not
carry authentication state:

- `theme` is written by `static/js/application.js` and controls light/dark
   presentation.
- `contributors_findme` is written by `static/js/contributors.js` and preserves
   rank-jump mode across contributors pages.
- `machines_state` is written by `static/js/tests_homepage.js` and preserves
   whether the homepage workers panel is expanded.
- `machines_sort`, `machines_order`, `machines_page`, `machines_q`,
   `machines_my_workers`, and `machines_filtered_count` are written server-side
   by `views.py` when `/tests/machines` normalizes the current filter state.

This split keeps auth/session semantics on the server-controlled signed cookie
while letting low-risk UI preferences remain simple, readable browser state.

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

## Homepage workers (`/tests/machines`) query parameters

The homepage workers fragment (`/tests/machines`) supports URL-driven state for
server sorting, paging, and lightweight filtering.

| Parameter | Values | Default |
|-----|-----|-----|
| `sort` | `last_active`, `machine`, `cores`, `uuid`, `mnps`, `ram`, `system`, `arch`, `compiler`, `python`, `worker`, `running_on` | `last_active` |
| `order` | `asc`, `desc` | column default |
| `page` | integer `>= 1` | `1` |
| `q` | free-text filter matched against any displayed machine column | empty |
| `my_workers` | `1`, `true`, `on`, `yes` | absent/false |

Behavior notes:

- Sorting is server-authoritative and stable with username asc tie-breaks.
- Pagination is enabled with page size `500`; links are omitted for one-page
   result sets.
- `my_workers` only applies for authenticated users; anonymous requests ignore
   this filter.
- `q` performs case-insensitive substring matching across all displayed table
   columns (machine, cores, UUID, MNps, RAM, system, arch, compiler, python,
   worker, running-on, and last-active text).
- Polling includes the current homepage filter-form state (`hx-include`), so
   sort/filter/page settings persist across periodic refreshes.
- Filter controls (`q`, `my_workers`) are rendered on `/tests` outside the
   swapped machines fragment to avoid input focus/caret glitches during table
   refresh swaps.
- `/tests/machines` responses persist the effective `sort`, `order`, `page`,
   `q`, and `my_workers` values in cookies, so returning to `/tests` restores
   the last machines filter state.
- Workers counter semantics are stable across both `/tests/machines` and
   `/tests/elo_batch` OOB updates:
  - no active filters: `Workers - <total> machines`
  - active `q` and/or `my_workers`: `Workers - <total> (<filtered>) machines`
- Machines sorting is fully server-authoritative; the old generic client-side
   header sorter has been retired.

## User management (`/user_management`) query parameters

The user-management page supports URL-driven server-authoritative table state.

| Parameter | Values | Default |
|-----|-----|-----|
| `group` | `all`, `pending`, `blocked`, `idle`, `approvers` | `pending` |
| `sort` | `username`, `registration`, `groups`, `email` | `registration` |
| `order` | `asc`, `desc` | column default |
| `page` | integer `>= 1` | `1` |
| `q` | free-text filter matched against username column | empty |
| `view` | `paged`, `all` | `paged` |

Behavior notes:

- Sorting is server-authoritative and stable with username tie-breaks.
- Pagination uses page size `25` in paged view.
- `view=all` returns all matching rows up to a hard cap (`5000`) and hides
   pagination controls.
- `q` performs case-insensitive substring matching on username only.
- User-management filtering stays on the userdb path: the base list comes from
   `request.userdb.get_users()`, while pending/blocked subsets come from the
   cached `get_pending()` / `get_blocked()` helpers.
- HTMX requests target `#user-management-content` and keep URL state via
   `hx-push-url="true"`.
- Table sorting is fully server-authoritative; the old generic client-side
   header sorter has been retired.

## Workers management (`/workers/show`) query parameters

The blocked-workers table supports URL-driven server-authoritative state.

| Parameter | Values | Default |
|-----|-----|-----|
| `filter` | `all-workers`, `le-5days`, `gt-5days` | `le-5days` |
| `sort` | `worker`, `last_changed`, `events`, `email` | `last_changed` |
| `order` | `asc`, `desc` | column default |
| `page` | integer `>= 1` | `1` |
| `q` | free-text filter matched against worker column | empty |
| `view` | `paged`, `all` | `paged` |

Behavior notes:

- `filter` keeps the server-side time-window behavior from H6.
- Sorting is server-authoritative and stable with worker-name tie-breaks.
- Pagination uses page size `25` in paged view.
- `view=all` returns all matching rows up to a hard cap (`5000`) and hides
   pagination controls.
- `q` performs case-insensitive substring matching on worker name only.
- Non-approver users cannot sort by `email`; unsupported values fall back to
   default server sort.
- HTMX requests target `#workers-content` and keep URL state via
   `hx-push-url="true"`.
- Sort-header links are dual-mode (`href` + `hx-get`): workers sorting swaps
   `#workers-content` with `hx-push-url="true"` when htmx is active, and still
   degrades to full-page navigation.
- Table sorting is fully server-authoritative; the old generic client-side
   header sorter has been retired.

## Contributors query parameters

The contributors pages (`/contributors` and `/contributors/monthly`) support
URL-driven state for server sorting, search, paging, full view, and rank jump.

| Parameter | Values | Default |
|-----|-----|-----|
| `search` | one-shot go-to query (exact username first, then first substring match) | empty |
| `sort` | `cpu_hours`, `username`, `last_updated`, `games_per_hour`, `games`, `tests` | `cpu_hours` |
| `order` | `asc`, `desc` | column default |
| `page` | integer `>= 1` | `1` |
| `view` | `paged`, `all` | `paged` |
| `findme` | any truthy value | absent |
| `highlight` | username | empty |

Behavior notes:

- Sorting is server-authoritative and stable with username asc tie-breaks.
- Rank is global for the filtered+sorted dataset (not page-local loop index).
- `findme=1` redirects authenticated users to the page containing their row and
   sets `highlight=<username>#me`.
- `view=all` returns all rows up to a hard cap (`5000`) and hides pagination.
- `search` is consumed as one-shot navigation intent and is not preserved in
   pagination/sort/view links, preventing repeated jumps during later browsing.
- `/contributors` and `/contributors/monthly` stay on the userdb fast path:
   the all-time page reads from `userdb.user_cache`, and the monthly page reads
   from `userdb.top_month`, so search and rank-jump never need an actions-log
   scan.
- Sort-header links are dual-mode (`href` + `hx-get`): contributors sorting
   swaps `#contributors-content` with `hx-push-url="true"` when htmx is active,
   and still works as normal navigation when JavaScript is unavailable.

## Neural networks (`/nns`) query parameters

The neural network repository page (`/nns`) supports URL-driven state for
search and paging.

| Parameter | Values | Default |
|-----|-----|-----|
| `network_name` | network name substring (case-insensitive) | empty |
| `user` | uploader username substring (case-insensitive) | empty |
| `master_only` | `1`, `true`, `on`, `yes` | absent/false |

Behavior notes:

- Sorting is server-authoritative and deterministic.
- Sort-header links are dual-mode (`href` + `hx-get`): sorting swaps
   `#nns-content` with `hx-push-url="true"` when htmx is active, with plain-link
   fallback preserved.
- Pagination links follow the same dual-mode contract.
| `page` | integer `>= 1` | `1` |

Behavior notes:

- Search inputs are HTMX-triggered (`input changed delay`) and also support
   explicit submit for keyboard and non-JS flows.
- HTMX updates target `#nns-content` and push updated query URLs for
   back/forward and shareable links.
- `master_only` checkbox preference is persisted in a cookie and reused when
   the query parameter is not present.
- Table sorting is fully server-authoritative; the old generic client-side
   header sorter has been retired.

## Actions (`/actions`) query parameters

The actions log supports URL-driven server-authoritative filtering, paging,
and sort state on the canonical `/actions` route.

| Parameter | Values | Default |
|-----|-----|-----|
| `action` | action name filter | empty |
| `user` | username substring | empty |
| `text` | Mongo text-search query | empty |
| `run_id` | run id | empty |
| `page` | integer `>= 1` | `1` |
| `max_actions` | positive integer, capped by auth state | route policy |
| `sort` | `time`, `event`, `source`, `target`, `comment` | `time` |
| `order` | `asc`, `desc` | `desc` for `time`, otherwise column default |
| `before` | action timestamp cursor for time-link deep links | absent |

Behavior notes:

- Sorting is server-authoritative. The default `time desc` path stays on the
   indexed fast query; explicit alternate sorts materialize and sort the
   capped working set server-side.
- Anonymous requests are capped at `5000` actions. Unfiltered authenticated
   requests default to `50000`; explicit `max_actions` values are preserved in
   the URL and hidden form state.
- HTMX requests target `#actions-content` and keep URL state via
   `hx-push-url="true"`.
- The visible filters auto-submit on select change and search/input events.
- The username field follows the same pattern as the other username filters in
   the UI: it is a plain `<input type="search">` in the main `/actions` GET
   form.
- `user` matches case-insensitive username substrings, not only exact names.
- Typing pauses trigger the existing debounced HTMX form request, so results
   refresh from `GET /actions?...` without a separate suggestions endpoint,
   popup, or second swap target.
- To keep that debounced path fast on large historical logs, `/actions` first
   resolves substring matches from a short-lived cached distinct username list
   built from the actions collection, refreshes that list once on a no-match
   lookup, then fetches the matching rows by exact username query. This differs
   from `/contributors` and `/user_management`, which can stay on userdb-backed
   sources because they only need current user records.
- The time link remains a normal anchor because it is a shareable deep link
   into the log timeline, not just a local fragment action.
